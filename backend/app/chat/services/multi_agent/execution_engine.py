import asyncio
import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable, Coroutine
from typing import Any

from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentFailureReason,
    AgentResult,
    AgentTask,
    AgentTaskStatus,
    AgentType,
    ExecutionOutcome,
    ExecutionPlan,
)
from app.chat.services.multi_agent.base import BaseSpecialistAgent

logger = logging.getLogger(__name__)

# Allowed specialist types for execution plan tasks
ALLOWED_SPECIALIST_TYPES = {
    AgentType.RESEARCH,
    AgentType.DOCUMENT,
    AgentType.ANALYSIS,
}


class AgentExecutionEngine:
    """
    Coordinates and executes an ExecutionPlan.
    Resolves dependency graphs (DAG), executes independent tasks concurrently via asyncio.gather,
    propagates upstream dependency results into downstream task contexts, enforces execution limits
    and timeouts, isolates failures, and returns a structured ExecutionOutcome.
    """

    def __init__(
        self,
        specialist_agents: list[BaseSpecialistAgent],
        max_specialist_tasks: int = 5,
        max_total_calls: int = 8,
        task_timeout: float = 20.0,
    ) -> None:
        self.specialists: dict[AgentType, BaseSpecialistAgent] = {
            agent.agent_type: agent for agent in specialist_agents
        }
        self.max_specialist_tasks = max_specialist_tasks
        self.max_total_calls = max_total_calls
        self.task_timeout = task_timeout

    def validate_plan(self, plan: ExecutionPlan) -> list[str]:
        """
        Validates an ExecutionPlan against topological consistency, cycle detection,
        unauthorized agent types, and execution limits.
        Returns a list of validation error strings. If empty, the plan is valid.
        """
        errors: list[str] = []

        if not plan.tasks:
            errors.append("Execution plan contains no tasks.")
            return errors

        if len(plan.tasks) > self.max_specialist_tasks:
            errors.append(
                f"Execution plan exceeds maximum specialist tasks limit "
                f"({len(plan.tasks)} > {self.max_specialist_tasks})."
            )

        task_ids = {t.task_id for t in plan.tasks}
        if len(task_ids) != len(plan.tasks):
            errors.append("Execution plan contains duplicate task IDs.")

        in_degree: dict[str, int] = {t.task_id: 0 for t in plan.tasks}
        graph: dict[str, list[str]] = defaultdict(list)

        for task in plan.tasks:
            # Check agent type allowed
            if task.agent_type not in ALLOWED_SPECIALIST_TYPES:
                errors.append(
                    f"Task {task.task_id} specifies unauthorized or unexecutable agent type: {task.agent_type}. "
                    f"Only {sorted(t.value for t in ALLOWED_SPECIALIST_TYPES)} are allowed."
                )

            # Check agent is registered if specialists are configured
            if (
                task.agent_type in ALLOWED_SPECIALIST_TYPES
                and self.specialists
                and task.agent_type not in self.specialists
            ):
                errors.append(
                    f"No registered specialist handler for agent type: {task.agent_type} (task {task.task_id})."
                )

            # Check self-dependency
            if task.task_id in task.dependencies:
                errors.append(f"Task {task.task_id} cannot depend on itself.")

            # Check dependency reference validity
            for dep in task.dependencies:
                if dep not in task_ids:
                    errors.append(
                        f"Task {task.task_id} references nonexistent dependency: {dep}."
                    )
                else:
                    graph[dep].append(task.task_id)
                    in_degree[task.task_id] += 1

        # Cycle detection via Kahn's algorithm
        queue = deque([t_id for t_id, deg in in_degree.items() if deg == 0])
        visited_count = 0

        while queue:
            node = queue.popleft()
            visited_count += 1
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(plan.tasks):
            errors.append("Circular dependency detected in execution plan.")

        return errors

    async def _execute_single_task(
        self,
        task: AgentTask,
        context: AgentExecutionContext,
        event_callback: Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]
        | None = None,
    ) -> AgentResult:
        """Executes a single specialist task with timeout enforcement and event emission."""
        specialist = self.specialists.get(task.agent_type)
        if not specialist:
            return AgentResult(
                task_id=task.task_id,
                agent_type=task.agent_type,
                status=AgentTaskStatus.FAILED,
                success=False,
                output="",
                error=f"Unregistered specialist for {task.agent_type}",
                failure_reason=AgentFailureReason.VALIDATION_ERROR,
            )

        if event_callback:
            await event_callback(
                "agent_started",
                {"task_id": task.task_id, "agent_type": task.agent_type.value},
            )

        start_time = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                specialist.execute_task(task, context),
                timeout=self.task_timeout,
            )
        except TimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            result = AgentResult(
                task_id=task.task_id,
                agent_type=task.agent_type,
                status=AgentTaskStatus.FAILED,
                success=False,
                output="",
                error=f"Task timed out after {self.task_timeout} seconds.",
                failure_reason=AgentFailureReason.TIMEOUT,
                execution_time_ms=elapsed_ms,
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.exception("Unexpected execution error in task %s", task.task_id)
            result = AgentResult(
                task_id=task.task_id,
                agent_type=task.agent_type,
                status=AgentTaskStatus.FAILED,
                success=False,
                output="",
                error=f"Execution error: {e}",
                failure_reason=AgentFailureReason.EXECUTION_ERROR,
                execution_time_ms=elapsed_ms,
            )

        if event_callback:
            if result.success:
                await event_callback(
                    "agent_completed",
                    {
                        "task_id": result.task_id,
                        "agent_type": result.agent_type.value,
                        "execution_time_ms": result.execution_time_ms,
                        "evidence_count": len(result.evidence),
                    },
                )
            else:
                await event_callback(
                    "agent_failed",
                    {
                        "task_id": result.task_id,
                        "agent_type": result.agent_type.value,
                        "reason": result.failure_reason.value
                        if result.failure_reason
                        else "UNKNOWN",
                        "error": result.error or "Unknown error",
                    },
                )

        return result

    async def execute(
        self,
        plan: ExecutionPlan,
        context: AgentExecutionContext,
        event_callback: Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]
        | None = None,
        cumulative_calls: int = 0,
    ) -> ExecutionOutcome:
        """
        Executes the provided ExecutionPlan using topological concurrency.
        Runs independent tasks concurrently and passes completed dependency results downstream.
        """
        start_time = time.perf_counter()
        validation_errors = self.validate_plan(plan)
        if validation_errors:
            failed_results = [
                AgentResult(
                    task_id=t.task_id,
                    agent_type=t.agent_type,
                    status=AgentTaskStatus.FAILED,
                    success=False,
                    output="",
                    error="; ".join(validation_errors),
                    failure_reason=AgentFailureReason.VALIDATION_ERROR,
                )
                for t in plan.tasks
            ]
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ExecutionOutcome(
                request_id=plan.request_id,
                failed_results=failed_results,
                total_calls=0,
                limits_reached=["PLAN_VALIDATION_FAILED"],
                execution_time_ms=elapsed_ms,
            )

        # Build task map and dependency tracking
        task_map: dict[str, AgentTask] = {t.task_id: t for t in plan.tasks}
        pending_dependencies: dict[str, set[str]] = {
            t.task_id: set(t.dependencies) for t in plan.tasks
        }
        all_results: dict[str, AgentResult] = {}
        total_calls = 0
        limits_reached: list[str] = []

        while len(all_results) < len(plan.tasks):
            # Check hard call limit
            if cumulative_calls + total_calls >= self.max_total_calls:
                limits_reached.append("MAX_TOTAL_AGENT_CALLS")
                # Mark remaining unexecuted tasks as SKIPPED
                for t_id, t in task_map.items():
                    if t_id not in all_results:
                        all_results[t_id] = AgentResult(
                            task_id=t_id,
                            agent_type=t.agent_type,
                            status=AgentTaskStatus.SKIPPED,
                            success=False,
                            output="",
                            error="Execution halted: MAX_TOTAL_AGENT_CALLS limit reached.",
                            failure_reason=AgentFailureReason.LIMIT_EXCEEDED,
                        )
                break

            # Find ready tasks (all dependencies resolved)
            ready_tasks = []
            for t_id, deps in list(pending_dependencies.items()):
                if t_id in all_results:
                    continue

                # Check if all dependencies have completed
                if not deps:
                    ready_tasks.append(task_map[t_id])
                else:
                    # Check if any dependency failed or was skipped
                    failed_dep = next(
                        (
                            d
                            for d in deps
                            if d in all_results and not all_results[d].success
                        ),
                        None,
                    )
                    if failed_dep:
                        # Skip this task due to dependency failure
                        all_results[t_id] = AgentResult(
                            task_id=t_id,
                            agent_type=task_map[t_id].agent_type,
                            status=AgentTaskStatus.SKIPPED,
                            success=False,
                            output="",
                            error=f"Dependency '{failed_dep}' failed or was skipped.",
                            failure_reason=AgentFailureReason.DEPENDENCY_FAILED,
                        )
                        if event_callback:
                            await event_callback(
                                "agent_failed",
                                {
                                    "task_id": t_id,
                                    "agent_type": task_map[t_id].agent_type.value,
                                    "reason": AgentFailureReason.DEPENDENCY_FAILED.value,
                                    "error": f"Dependency '{failed_dep}' failed.",
                                },
                            )

            if not ready_tasks:
                # If no tasks are ready and not all are processed, break to avoid infinite loop
                for t_id, t in task_map.items():
                    if t_id not in all_results:
                        all_results[t_id] = AgentResult(
                            task_id=t_id,
                            agent_type=t.agent_type,
                            status=AgentTaskStatus.SKIPPED,
                            success=False,
                            output="",
                            error="Task could not be scheduled due to unresolved dependencies.",
                            failure_reason=AgentFailureReason.DEPENDENCY_FAILED,
                        )
                break

            # Enforce remaining quota limit on batch execution
            remaining_quota = self.max_total_calls - (cumulative_calls + total_calls)
            if len(ready_tasks) > remaining_quota:
                limits_reached.append("MAX_TOTAL_AGENT_CALLS")
                skipped_tasks = ready_tasks[remaining_quota:]
                ready_tasks = ready_tasks[:remaining_quota]
                for sk_t in skipped_tasks:
                    all_results[sk_t.task_id] = AgentResult(
                        task_id=sk_t.task_id,
                        agent_type=sk_t.agent_type,
                        status=AgentTaskStatus.SKIPPED,
                        success=False,
                        output="",
                        error="Execution halted: MAX_TOTAL_AGENT_CALLS limit reached.",
                        failure_reason=AgentFailureReason.LIMIT_EXCEEDED,
                    )

            if not ready_tasks:
                break

            # Execute independent ready tasks concurrently via asyncio.gather
            async def _run_with_context(task: AgentTask) -> AgentResult:
                # Construct task-specific execution context with upstream dependency results
                task_dep_results = {
                    dep_id: all_results[dep_id]
                    for dep_id in task.dependencies
                    if dep_id in all_results
                }
                # Also pass all completed results so far in shared dependency results
                merged_deps = {**context.dependency_results, **task_dep_results}

                task_context = AgentExecutionContext(
                    request_id=context.request_id,
                    user_id=context.user_id,
                    conversation_id=context.conversation_id,
                    include_library_documents=context.include_library_documents,
                    include_conversation_documents=context.include_conversation_documents,
                    document_ids=context.document_ids,
                    dependency_results=merged_deps,
                    metadata=context.metadata,
                )
                return await self._execute_single_task(
                    task, task_context, event_callback
                )

            batch_results = await asyncio.gather(
                *[_run_with_context(t) for t in ready_tasks]
            )
            total_calls += len(ready_tasks)

            # Record batch results and remove resolved dependencies
            for res in batch_results:
                all_results[res.task_id] = res

            for t_id in pending_dependencies:
                pending_dependencies[t_id].difference_update(
                    {res.task_id for res in batch_results if res.success}
                )

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        completed = [
            r
            for r in all_results.values()
            if r.status == AgentTaskStatus.COMPLETED and r.success
        ]
        failed = [
            r
            for r in all_results.values()
            if r.status == AgentTaskStatus.FAILED
            or (not r.success and r.status != AgentTaskStatus.SKIPPED)
        ]
        skipped = [
            r for r in all_results.values() if r.status == AgentTaskStatus.SKIPPED
        ]

        return ExecutionOutcome(
            request_id=plan.request_id,
            completed_results=completed,
            failed_results=failed,
            skipped_results=skipped,
            total_calls=total_calls,
            limits_reached=limits_reached,
            execution_time_ms=elapsed_ms,
        )

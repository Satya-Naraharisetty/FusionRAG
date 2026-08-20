import json
import logging
import re
import time
from collections.abc import AsyncIterator
from typing import Any

from app.chat.domain.agent_observability import (
    AgentQualityMetrics,
)
from app.chat.domain.interfaces import LLMProvider
from app.chat.domain.models import ChatMessage, ChatRole
from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentResult,
    AgentTask,
    AgentType,
    EvaluationDecision,
    ExecutionPlan,
    MultiAgentDiagnostics,
    MultiAgentResponse,
    ResultEvaluation,
    SynthesisRequest,
)
from app.chat.services.multi_agent.execution_engine import (
    ALLOWED_SPECIALIST_TYPES,
    AgentExecutionEngine,
)
from app.chat.services.multi_agent.observability import AgentObservabilityService
from app.chat.services.multi_agent.result_evaluator import ResultEvaluator
from app.chat.services.multi_agent.synthesis_agent import SynthesisAgent

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are a master planning agent in a hierarchical multi-agent architecture.
Decompose the user's request into a structured execution plan containing specialist tasks with explicit dependencies.

Available Specialist Agents:
- RESEARCH: Performs Hybrid RAG search across knowledge base chunks. Use for questions about general facts, concepts, policies, or documentation.
- DOCUMENT: Inspects specific known documents/chunks by ID, or lists documents in conversation. Use when specific document UUIDs or document metadata are explicitly mentioned.
- ANALYSIS: Performs deterministic mathematical calculations, growth rates, sums, averages, or structured data comparisons via SafeCalculator.

Planning Rules:
1. Only create tasks for necessary specialists.
2. Max 5 tasks in a single plan.
3. Use 'dependencies' to sequence tasks (e.g. ANALYSIS depending on RESEARCH).
4. Independent tasks should have empty dependencies [] so they run concurrently.
5. Return strictly valid JSON conforming to the schema below.

JSON Schema:
{
  "reasoning_summary": "Brief explanation of plan",
  "tasks": [
    {
      "task_id": "task_1",
      "agent_type": "RESEARCH" | "DOCUMENT" | "ANALYSIS",
      "request": "Detailed task description",
      "dependencies": [],
      "parameters": {},
      "expected_outputs": ["Description of expected result"],
      "required_evidence": ["Expected evidence criteria"]
    }
  ]
}"""


class MasterAgent:
    """
    Master Planner and Router in the hierarchical multi-agent architecture.
    Analyzes user intent, creates and validates ExecutionPlans, dispatches them
    exclusively to AgentExecutionEngine, manages bounded adaptive replanning using ResultEvaluator,
    preserves results across iterations, reconstructs dependencies, and sends completed outcomes to SynthesisAgent.
    Does NOT directly execute or schedule specialist agent tasks.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        execution_engine: AgentExecutionEngine,
        synthesis_agent: SynthesisAgent,
        result_evaluator: ResultEvaluator | None = None,
        observability: AgentObservabilityService | None = None,
        max_plan_iterations: int = 2,
        max_total_calls: int = 8,
    ) -> None:
        self.llm_provider = llm_provider
        self.execution_engine = execution_engine
        self.synthesis_agent = synthesis_agent
        self.result_evaluator = result_evaluator or ResultEvaluator(
            llm_provider=llm_provider
        )
        self.observability = observability
        self.max_plan_iterations = max_plan_iterations
        self.max_total_calls = max_total_calls

    def _get_task_fingerprint(self, task: AgentTask) -> str:
        """Returns a normalized string hash identifying the task's functional operation."""
        params_str = json.dumps(task.parameters, sort_keys=True)
        return f"{task.agent_type.value}:{task.request.strip().lower()}:{params_str}"

    async def _plan_with_llm(
        self,
        request: str,
        context: AgentExecutionContext,
        iteration: int = 1,
        evaluation: ResultEvaluation | None = None,
    ) -> ExecutionPlan | None:
        """Attempts to generate a structured ExecutionPlan via LLM generation."""
        eval_context = ""
        if evaluation:
            eval_context = (
                f"\nPrevious Evaluation Decision: {evaluation.decision.value}\n"
                f"Missing Requirements: {[mr.model_dump() for mr in evaluation.missing_requirements]}\n"
                f"Contradictions: {evaluation.contradictions}\n"
            )

        user_msg = (
            f"User Request: {request}\n"
            f"Context: request_id={context.request_id}, conversation_id={context.conversation_id}, "
            f"has_doc_ids={bool(context.document_ids)}\n"
            f"Iteration: {iteration}\n"
            f"{eval_context}"
            f"Generate an optimal JSON execution plan:"
        )
        messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=PLANNER_SYSTEM_PROMPT),
            ChatMessage(role=ChatRole.USER, content=user_msg),
        ]

        try:
            response = await self.llm_provider.generate(
                messages=messages,
                model="gemini-2.5-flash-lite",
                temperature=0.0,
                max_tokens=600,
            )
            from app.chat.domain.interfaces import ProviderResponse

            if isinstance(response, tuple) and not hasattr(response, "content"):
                response = ProviderResponse(content=response[0], usage=response[1])

            content = (response.content or "").strip()

            # Extract JSON block if surrounded by markdown code fences
            json_match = re.search(
                r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL
            )
            if json_match:
                content = json_match.group(1)
            elif "{" in content and "}" in content:
                content = content[content.find("{") : content.rfind("}") + 1]

            plan_dict = json.loads(content)
            raw_tasks = plan_dict.get("tasks", [])
            tasks: list[AgentTask] = []

            for t in raw_tasks:
                agent_type_str = str(t.get("agent_type", "")).upper()
                if agent_type_str in ALLOWED_SPECIALIST_TYPES:
                    tasks.append(
                        AgentTask(
                            task_id=str(t.get("task_id", f"task_{len(tasks) + 1}")),
                            request=str(t.get("request", request)),
                            agent_type=AgentType(agent_type_str),
                            dependencies=list(t.get("dependencies", [])),
                            parameters=dict(t.get("parameters", {})),
                            priority=int(t.get("priority", 0)),
                            expected_outputs=list(t.get("expected_outputs", [])),
                            required_evidence=list(t.get("required_evidence", [])),
                        )
                    )

            if not tasks:
                return None

            return ExecutionPlan(
                request_id=context.request_id,
                tasks=tasks,
                reasoning_summary=plan_dict.get("reasoning_summary"),
                iteration=iteration,
            )
        except Exception as e:
            logger.warning("LLM planning failed or returned invalid JSON: %s", e)
            return None

    def _plan_heuristic(
        self,
        request: str,
        context: AgentExecutionContext,
        iteration: int = 1,
    ) -> ExecutionPlan:
        """Deterministic heuristic fallback planner for robust plan generation."""
        req_lower = request.lower()
        tasks: list[AgentTask] = []

        uuid_match = re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            req_lower,
        )
        has_math = any(
            op in req_lower
            for op in [
                "calculate",
                "compute",
                "growth rate",
                "percentage",
                "sum",
                "average",
                "+",
                "*",
                "/",
            ]
        ) and any(c.isdigit() for c in request)

        clean_math_str = re.sub(
            r"^(calculate|compute|eval|evaluate|what is|how much is)\s*", "", req_lower
        ).strip()
        is_pure_math = (
            has_math
            and not uuid_match
            and not any(
                kw in req_lower
                for kw in [
                    "find",
                    "search",
                    "revenue",
                    "sales",
                    "quarter",
                    "q1",
                    "q2",
                    "q3",
                    "q4",
                    "who",
                    "explain",
                    "describe",
                    "doc",
                    "pdf",
                ]
            )
            and bool(re.match(r"^[\d\s\+\-\*\/\(\)\.\,]+$", clean_math_str))
        )

        if uuid_match:
            doc_id_str = uuid_match.group(0)
            tasks.append(
                AgentTask(
                    task_id="doc_inspect_1",
                    request=f"Inspect document {doc_id_str}",
                    agent_type=AgentType.DOCUMENT,
                    dependencies=[],
                    parameters={"document_id": doc_id_str, "action": "inspect"},
                    expected_outputs=[f"Data from document {doc_id_str}"],
                )
            )
            if has_math:
                tasks.append(
                    AgentTask(
                        task_id="analysis_1",
                        request=f"Perform calculation on document data: {request}",
                        agent_type=AgentType.ANALYSIS,
                        dependencies=["doc_inspect_1"],
                        parameters={"action": "calculate"},
                    )
                )
        elif is_pure_math:
            tasks.append(
                AgentTask(
                    task_id="calc_1",
                    request=request,
                    agent_type=AgentType.ANALYSIS,
                    dependencies=[],
                    parameters={"expression": request},
                )
            )
        else:
            tasks.append(
                AgentTask(
                    task_id="research_1",
                    request=request,
                    agent_type=AgentType.RESEARCH,
                    dependencies=[],
                    parameters={"query": request, "top_k": 5},
                    expected_outputs=["Relevant evidence chunks for query"],
                )
            )
            if has_math:
                tasks.append(
                    AgentTask(
                        task_id="analysis_1",
                        request=f"Perform calculation on retrieved research: {request}",
                        agent_type=AgentType.ANALYSIS,
                        dependencies=["research_1"],
                        parameters={"action": "calculate"},
                    )
                )

        return ExecutionPlan(
            request_id=context.request_id,
            tasks=tasks,
            reasoning_summary="Heuristic fallback plan based on query intent classification.",
            iteration=iteration,
        )

    async def create_plan(
        self,
        request: str,
        context: AgentExecutionContext,
        iteration: int = 1,
    ) -> ExecutionPlan:
        """
        Creates and validates an initial ExecutionPlan.
        """
        plan = await self._plan_with_llm(request, context, iteration=iteration)
        if plan:
            validation_errors = self.execution_engine.validate_plan(plan)
            if not validation_errors:
                return plan
            logger.warning(
                "LLM plan failed validation (%s); falling back to heuristic plan.",
                validation_errors,
            )

        return self._plan_heuristic(request, context, iteration=iteration)

    async def create_refined_plan(
        self,
        request: str,
        previous_plan: ExecutionPlan,
        evaluation: ResultEvaluation,
        accumulated_results: dict[str, AgentResult],
        context: AgentExecutionContext,
        iteration: int,
    ) -> tuple[ExecutionPlan, int]:
        """
        Creates a refined ExecutionPlan based on ResultEvaluation and previous results.
        Preserves successful prior work without re-executing it, adds targeted tasks for missing requirements,
        reconstructs dependency relationships for downstream tasks, deduplicates failed task fingerprints,
        and enforces execution limits.
        Returns (refined_plan, avoided_duplicate_count).
        """
        avoided_dupes = 0
        refined_tasks: list[AgentTask] = []

        if self.llm_provider:
            try:
                prompt_msgs = [
                    ChatMessage(
                        role=ChatRole.SYSTEM,
                        content="You are a multi-agent master replanner. Output JSON with a 'tasks' list.",
                    ),
                    ChatMessage(
                        role=ChatRole.USER,
                        content=f"Original Request: {request}\nMissing: {[m.requirement for m in evaluation.missing_requirements]}\nIteration: {iteration}",
                    ),
                ]
                await self.llm_provider.generate(
                    messages=prompt_msgs,
                    model="gemini-2.5-flash-lite",
                    temperature=0.0,
                    max_tokens=1000,
                )
            except Exception as e:
                logger.warning(
                    "LLM replan prompt execution failed or returned invalid JSON: %s", e
                )

        # 1. Identify successful task IDs from accumulated_results to preserve
        successful_task_ids = {
            t_id for t_id, res in accumulated_results.items() if res.success
        }
        failed_fingerprints = {
            self._get_task_fingerprint(t)
            for t in previous_plan.tasks
            if t.task_id in accumulated_results
            and not accumulated_results[t.task_id].success
        }

        # 2. Add new targeted tasks for missing requirements
        new_retrieval_task_ids: list[str] = []
        for idx, missing in enumerate(evaluation.missing_requirements, start=1):
            agent_type = missing.suggested_agent_type or AgentType.RESEARCH
            new_task_id = f"refine_task_{iteration}_{idx}"
            new_task = AgentTask(
                task_id=new_task_id,
                request=f"Retrieve missing requirement: {missing.requirement}",
                agent_type=agent_type,
                dependencies=[],
                parameters={"query": missing.requirement},
                expected_outputs=[missing.requirement],
            )
            fp = self._get_task_fingerprint(new_task)
            if fp in failed_fingerprints:
                avoided_dupes += 1
                logger.info(
                    "Avoided duplicate execution of previously failed task fingerprint: %s",
                    fp,
                )
                continue

            refined_tasks.append(new_task)
            new_retrieval_task_ids.append(new_task_id)

        # 3. Preserve or update downstream tasks from previous plan (e.g. ANALYSIS)
        for prev_task in previous_plan.tasks:
            # If task succeeded, we do not re-execute it. It is already preserved in accumulated_results!
            if prev_task.task_id in successful_task_ids:
                continue

            # If task was a dependent task (e.g. ANALYSIS) that was skipped or failed due to missing inputs
            if prev_task.agent_type == AgentType.ANALYSIS or prev_task.dependencies:
                # Reconstruct dependency graph: include all successful prior retrieval tasks PLUS new retrieval tasks
                prior_dep_ids = [
                    dep for dep in prev_task.dependencies if dep in successful_task_ids
                ]
                updated_deps = list(
                    dict.fromkeys(prior_dep_ids + new_retrieval_task_ids)
                )

                refined_task = AgentTask(
                    task_id=prev_task.task_id,
                    request=prev_task.request,
                    agent_type=prev_task.agent_type,
                    dependencies=updated_deps,
                    parameters=prev_task.parameters,
                    priority=prev_task.priority,
                )
                refined_tasks.append(refined_task)

        if not refined_tasks:
            # Fallback if no tasks created
            refined_tasks.append(
                AgentTask(
                    task_id=f"fallback_research_{iteration}",
                    request=request,
                    agent_type=AgentType.RESEARCH,
                    dependencies=[],
                )
            )

        refined_plan = ExecutionPlan(
            request_id=context.request_id,
            tasks=refined_tasks[: self.execution_engine.max_specialist_tasks],
            reasoning_summary=f"Refined plan for iteration {iteration} targeting missing requirements.",
            iteration=iteration,
        )

        validation_errors = self.execution_engine.validate_plan(refined_plan)
        if validation_errors:
            logger.warning(
                "Refined plan validation failed (%s); building heuristic refinement.",
                validation_errors,
            )
            fallback_tasks = [
                AgentTask(
                    task_id=f"targeted_{iteration}",
                    request=request,
                    agent_type=AgentType.RESEARCH,
                )
            ]
            refined_plan = ExecutionPlan(
                request_id=context.request_id,
                tasks=fallback_tasks,
                reasoning_summary="Heuristic fallback refinement.",
                iteration=iteration,
            )

        return refined_plan, avoided_dupes

    async def execute_request(
        self,
        request: str,
        context: AgentExecutionContext,
        model: str = "gemini-2.5-flash-lite",
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> MultiAgentResponse:
        """
        Executes a complete multi-agent request with adaptive result evaluation, bounded replanning,
        and end-to-end production observability.
        """
        start_time = time.perf_counter()
        if self.observability:
            self.observability.start_trace(
                request_id=context.request_id,
                conversation_id=context.conversation_id,
                user_id=context.user_id,
                metadata=context.metadata,
            )

        total_calls = 0
        task_latencies: dict[str, float] = {}
        accumulated_results: dict[str, AgentResult] = {}
        limits_reached: list[str] = []

        current_plan: ExecutionPlan | None = None
        iteration = 0
        eval_count = 0
        replan_count = 0
        avoided_dupes = 0
        retry_count = 0
        planning_fallback_used = False

        eval_latency_ms = 0.0
        plan_latency_ms = 0.0
        exec_latency_ms = 0.0

        latest_evaluation: ResultEvaluation | None = None

        while iteration < self.max_plan_iterations:
            iteration += 1

            p_start = time.perf_counter()
            if iteration == 1:
                current_plan = await self.create_plan(
                    request, context, iteration=iteration
                )
                if (
                    current_plan.reasoning_summary
                    and "heuristic" in current_plan.reasoning_summary.lower()
                ):
                    planning_fallback_used = True
                if self.observability:
                    self.observability.record_event(
                        request_id=context.request_id,
                        event_type="plan_created",
                        duration_ms=(time.perf_counter() - p_start) * 1000,
                        metadata={
                            "task_count": len(current_plan.tasks),
                            "iteration": iteration,
                            "reasoning_summary": current_plan.reasoning_summary or "",
                        },
                    )
            else:
                replan_count += 1
                assert current_plan is not None
                assert latest_evaluation is not None
                if self.observability:
                    self.observability.record_event(
                        request_id=context.request_id,
                        event_type="replan_started",
                        metadata={
                            "iteration": iteration,
                            "reason": latest_evaluation.reason,
                        },
                    )
                prev_task_count = len(current_plan.tasks)
                current_plan, dupes = await self.create_refined_plan(
                    request=request,
                    previous_plan=current_plan,
                    evaluation=latest_evaluation,
                    accumulated_results=accumulated_results,
                    context=context,
                    iteration=iteration,
                )
                avoided_dupes += dupes
                replan_dur_ms = (time.perf_counter() - p_start) * 1000
                if self.observability:
                    self.observability.record_replan(
                        request_id=context.request_id,
                        iteration=iteration,
                        new_tasks_count=len(current_plan.tasks),
                        preserved_tasks_count=prev_task_count,
                        avoided_dupes=dupes,
                        duration_ms=replan_dur_ms,
                    )

            plan_latency_ms += (time.perf_counter() - p_start) * 1000

            # Pass preserved prior results into execution context
            merged_context = AgentExecutionContext(
                request_id=context.request_id,
                user_id=context.user_id,
                conversation_id=context.conversation_id,
                include_library_documents=context.include_library_documents,
                include_conversation_documents=context.include_conversation_documents,
                document_ids=context.document_ids,
                dependency_results={
                    **context.dependency_results,
                    **accumulated_results,
                },
                metadata=context.metadata,
            )

            x_start = time.perf_counter()
            outcome = await self.execution_engine.execute(
                plan=current_plan,
                context=merged_context,
                cumulative_calls=total_calls,
                cumulative_cost_units=sum(
                    r.metadata.get("estimated_cost_units", 0.0)
                    for r in accumulated_results.values()
                ),
                cumulative_latency_ms=sum(
                    r.metadata.get("estimated_latency_ms", 0.0)
                    for r in accumulated_results.values()
                ),
            )
            exec_latency_ms += (time.perf_counter() - x_start) * 1000

            total_calls += outcome.total_calls
            limits_reached.extend(outcome.limits_reached)

            for r in outcome.completed_results:
                accumulated_results[r.task_id] = r
                task_latencies[r.task_id] = r.execution_time_ms

            for f in outcome.failed_results:
                accumulated_results[f.task_id] = f
                task_latencies[f.task_id] = f.execution_time_ms

            for s in outcome.skipped_results:
                if s.task_id not in accumulated_results:
                    accumulated_results[s.task_id] = s

            # Evaluate execution outcome
            e_start = time.perf_counter()
            if self.observability:
                self.observability.record_event(
                    request_id=context.request_id,
                    event_type="evaluation_started",
                    metadata={"iteration": iteration},
                )
            latest_evaluation = await self.result_evaluator.evaluate(
                original_request=request,
                plan=current_plan,
                outcome=outcome,
                accumulated_results=accumulated_results,
            )
            eval_dur_ms = (time.perf_counter() - e_start) * 1000
            eval_latency_ms += eval_dur_ms
            eval_count += 1

            if self.observability:
                self.observability.record_evaluation(
                    request_id=context.request_id,
                    evaluation=latest_evaluation,
                    duration_ms=eval_dur_ms,
                )

            if latest_evaluation.decision == EvaluationDecision.RETRYABLE_FAILURE:
                retry_count += 1

            # Check loop termination conditions
            if (
                latest_evaluation.decision == EvaluationDecision.SUFFICIENT
                or latest_evaluation.decision == EvaluationDecision.TERMINAL_FAILURE
                or not latest_evaluation.should_replan
                or total_calls >= self.max_total_calls
            ):
                break

        # Pass all accumulated results to SynthesisAgent
        all_results_list = list(accumulated_results.values())
        synthesis_req = SynthesisRequest(
            request_id=context.request_id,
            original_request=request,
            specialist_results=all_results_list,
            context=context,
        )

        s_start = time.perf_counter()
        if self.observability:
            self.observability.record_event(
                request_id=context.request_id,
                event_type="synthesis_started",
                metadata={"specialist_results_count": len(all_results_list)},
            )
        answer_text, citations, usage = await self.synthesis_agent.synthesize(
            request=synthesis_req,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        synth_latency_ms = (time.perf_counter() - s_start) * 1000
        if self.observability:
            self.observability.record_event(
                request_id=context.request_id,
                event_type="synthesis_completed",
                duration_ms=synth_latency_ms,
                metadata={
                    "citations_count": len(citations),
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                },
            )

        total_time_ms = (time.perf_counter() - start_time) * 1000
        failed_tasks = [r.task_id for r in all_results_list if not r.success]

        research_results = [
            r
            for r in all_results_list
            if r.agent_type == AgentType.RESEARCH and r.metadata
        ]
        research_plans_created = len(research_results)
        research_subqueries_generated = sum(
            len(r.metadata.get("research_plan", {}).get("subqueries", []))
            for r in research_results
        )
        research_subqueries_executed = sum(
            r.metadata.get("queries_executed", 0) for r in research_results
        )
        research_empty_queries = sum(
            len(r.metadata.get("empty_queries", [])) for r in research_results
        )
        research_duplicate_evidence_removed = sum(
            r.metadata.get("duplicate_evidence_removed", 0) for r in research_results
        )
        research_evidence_count = sum(
            len(r.evidence) for r in research_results if r.success
        )
        research_planning_latency_ms = sum(
            r.metadata.get("research_planning_latency_ms", 0.0)
            for r in research_results
        )
        research_retrieval_latency_ms = sum(
            r.metadata.get("research_retrieval_latency_ms", 0.0)
            for r in research_results
        )
        research_total_latency_ms = sum(r.execution_time_ms for r in research_results)

        # Routing Diagnostics (Prompt 3.4)
        routing_decisions_count = len(all_results_list)
        capability_rejections_count = sum(
            1
            for r in all_results_list
            if r.metadata.get("routing_reason_code")
            in (
                "BUDGET_EXCEEDED",
                "CONTEXT_MISSING",
                "POLICY_REJECTED",
                "CAPABILITY_MISMATCH",
            )
        )
        fallback_routes_count = sum(
            1
            for r in all_results_list
            if r.metadata.get("routing_reason_code") == "FALLBACK_CAPABILITY"
        )
        unavailable_capabilities_count = sum(
            1
            for r in all_results_list
            if r.metadata.get("routing_reason_code")
            in ("NO_CAPABILITY_AVAILABLE", "CAPABILITY_DISABLED")
        )
        total_est_cost = sum(
            r.metadata.get("estimated_cost_units", 0.0) for r in all_results_list
        )
        total_est_latency = sum(
            r.metadata.get("estimated_latency_ms", 0.0) for r in all_results_list
        )

        diagnostics = MultiAgentDiagnostics(
            plan_iterations=iteration,
            total_specialist_calls=total_calls,
            task_latencies=task_latencies,
            failed_tasks=failed_tasks,
            limits_reached=list(set(limits_reached)),
            evaluation_count=eval_count,
            replans=replan_count,
            initial_task_count=len(current_plan.tasks) if current_plan else 0,
            final_task_count=len(all_results_list),
            avoided_duplicate_tasks=avoided_dupes,
            retry_count=retry_count,
            evaluation_latency_ms=round(eval_latency_ms, 2),
            planning_latency_ms=round(plan_latency_ms, 2),
            execution_latency_ms=round(exec_latency_ms, 2),
            synthesis_latency_ms=round(synth_latency_ms, 2),
            research_plans_created=research_plans_created,
            research_subqueries_generated=research_subqueries_generated,
            research_subqueries_executed=research_subqueries_executed,
            research_retrieval_calls=research_subqueries_executed,
            research_empty_queries=research_empty_queries,
            research_duplicate_evidence_removed=research_duplicate_evidence_removed,
            research_evidence_count=research_evidence_count,
            research_planning_latency_ms=round(research_planning_latency_ms, 2),
            research_retrieval_latency_ms=round(research_retrieval_latency_ms, 2),
            research_total_latency_ms=round(research_total_latency_ms, 2),
            routing_decisions=routing_decisions_count,
            capability_rejections=capability_rejections_count,
            fallback_routes=fallback_routes_count,
            unavailable_capabilities=unavailable_capabilities_count,
            routing_latency_ms=round(plan_latency_ms, 2),
            estimated_cost_units=round(total_est_cost, 4),
            estimated_latency_ms=round(total_est_latency, 2),
        )

        grounding_status = "grounded"
        total_ev_count = sum(len(r.evidence) for r in all_results_list)
        if total_ev_count == 0:
            grounding_status = "empty_evidence"
        elif len(citations) == 0 and total_ev_count > 0:
            grounding_status = "partial"

        if self.observability:
            self.observability.record_evidence_metrics(
                request_id=context.request_id,
                total_evidence=total_ev_count,
                unique_evidence=total_ev_count,
                duplicate_removed=research_duplicate_evidence_removed,
                citation_count=len(citations),
                conflicting_count=len(latest_evaluation.contradictions)
                if latest_evaluation
                else 0,
                empty_retrieval_count=research_empty_queries,
                research_subqueries=research_subqueries_generated,
                successful_research_subqueries=research_subqueries_executed,
                failed_research_subqueries=research_empty_queries,
                citations_received=total_ev_count,
                citations_returned=len(citations),
                grounding_status=grounding_status,
            )
            quality_metrics = AgentQualityMetrics(
                planning_success=True,
                planning_fallback_used=planning_fallback_used,
                number_of_specialists_used=len(
                    {r.agent_type for r in all_results_list if r.success}
                ),
                number_of_replans=replan_count,
                successful_task_count=len([r for r in all_results_list if r.success]),
                failed_task_count=len(failed_tasks),
                skipped_task_count=len(
                    [r for r in all_results_list if r.status == "SKIPPED"]
                ),
                capability_fallback_count=fallback_routes_count,
                evaluation_count=eval_count,
                synthesis_success=True,
                final_grounding_status=grounding_status,
            )
            self.observability.complete_trace(
                request_id=context.request_id,
                diagnostics=diagnostics,
                quality_metrics=quality_metrics,
            )

        return MultiAgentResponse(
            answer=answer_text,
            plan=current_plan
            or ExecutionPlan(
                request_id=context.request_id, tasks=[], iteration=iteration
            ),
            specialist_results=all_results_list,
            citations=citations,
            usage=usage,
            total_time_ms=total_time_ms,
            diagnostics=diagnostics,
        )

    async def execute_request_stream(
        self,
        request: str,
        context: AgentExecutionContext,
        model: str = "gemini-2.5-flash-lite",
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Streams multi-agent lifecycle events (including evaluation & replan events) and synthesized text chunks.
        """
        if self.observability:
            self.observability.start_trace(
                request_id=context.request_id,
                conversation_id=context.conversation_id,
                user_id=context.user_id,
                metadata=context.metadata,
            )

        event_queue: list[dict[str, Any]] = []

        async def _event_callback(event_name: str, event_data: dict[str, Any]) -> None:
            event_queue.append({"event": event_name, "data": event_data})

        total_calls = 0
        accumulated_results: dict[str, AgentResult] = {}
        current_plan: ExecutionPlan | None = None
        iteration = 0
        latest_evaluation: ResultEvaluation | None = None

        while iteration < self.max_plan_iterations:
            iteration += 1
            if iteration > 1:
                yield {
                    "event": "replan_started",
                    "data": {
                        "iteration": iteration,
                        "reason": latest_evaluation.reason
                        if latest_evaluation
                        else "Replanning",
                    },
                }

                assert current_plan is not None
                assert latest_evaluation is not None
                current_plan, _ = await self.create_refined_plan(
                    request=request,
                    previous_plan=current_plan,
                    evaluation=latest_evaluation,
                    accumulated_results=accumulated_results,
                    context=context,
                    iteration=iteration,
                )

                yield {
                    "event": "replan_completed",
                    "data": {
                        "iteration": iteration,
                        "task_count": len(current_plan.tasks),
                    },
                }
            else:
                current_plan = await self.create_plan(
                    request, context, iteration=iteration
                )

            yield {
                "event": "plan_created",
                "data": {
                    "iteration": iteration,
                    "task_count": len(current_plan.tasks),
                    "tasks": [
                        {"task_id": t.task_id, "agent_type": t.agent_type.value}
                        for t in current_plan.tasks
                    ],
                },
            }

            merged_context = AgentExecutionContext(
                request_id=context.request_id,
                user_id=context.user_id,
                conversation_id=context.conversation_id,
                include_library_documents=context.include_library_documents,
                include_conversation_documents=context.include_conversation_documents,
                document_ids=context.document_ids,
                dependency_results={
                    **context.dependency_results,
                    **accumulated_results,
                },
                metadata=context.metadata,
            )

            event_queue.clear()
            outcome = await self.execution_engine.execute(
                plan=current_plan,
                context=merged_context,
                event_callback=_event_callback,
                cumulative_calls=total_calls,
                cumulative_cost_units=sum(
                    r.metadata.get("estimated_cost_units", 0.0)
                    for r in accumulated_results.values()
                ),
                cumulative_latency_ms=sum(
                    r.metadata.get("estimated_latency_ms", 0.0)
                    for r in accumulated_results.values()
                ),
            )

            for ev in event_queue:
                yield ev

            total_calls += outcome.total_calls

            for r in (
                outcome.completed_results
                + outcome.failed_results
                + outcome.skipped_results
            ):
                accumulated_results[r.task_id] = r

            # Emit evaluation lifecycle events
            yield {
                "event": "evaluation_started",
                "data": {"iteration": iteration},
            }

            latest_evaluation = await self.result_evaluator.evaluate(
                original_request=request,
                plan=current_plan,
                outcome=outcome,
                accumulated_results=accumulated_results,
            )

            yield {
                "event": "evaluation_completed",
                "data": {
                    "decision": latest_evaluation.decision.value,
                    "confidence": latest_evaluation.confidence,
                    "missing_requirements": len(latest_evaluation.missing_requirements),
                    "should_replan": latest_evaluation.should_replan,
                },
            }

            if (
                latest_evaluation.decision == EvaluationDecision.SUFFICIENT
                or latest_evaluation.decision == EvaluationDecision.TERMINAL_FAILURE
                or not latest_evaluation.should_replan
                or total_calls >= self.max_total_calls
            ):
                break

        synthesis_req = SynthesisRequest(
            request_id=context.request_id,
            original_request=request,
            specialist_results=list(accumulated_results.values()),
            context=context,
        )

        async for synth_event in self.synthesis_agent.synthesize_stream(
            request=synthesis_req,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield synth_event

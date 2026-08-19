import json
import logging
import re
import time
from collections.abc import AsyncIterator
from typing import Any

from app.chat.domain.interfaces import LLMProvider
from app.chat.domain.models import ChatMessage, ChatRole
from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentFailureReason,
    AgentResult,
    AgentTask,
    AgentType,
    ExecutionOutcome,
    ExecutionPlan,
    MultiAgentDiagnostics,
    MultiAgentResponse,
    SynthesisRequest,
)
from app.chat.services.multi_agent.execution_engine import (
    ALLOWED_SPECIALIST_TYPES,
    AgentExecutionEngine,
)
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
      "parameters": {}
    }
  ]
}"""


class MasterAgent:
    """
    Master Planner and Router in the hierarchical multi-agent architecture.
    Analyzes user intent, creates and validates ExecutionPlans, dispatches them
    exclusively to AgentExecutionEngine, manages bounded replanning, and sends
    completed outcomes to SynthesisAgent.
    Does NOT directly execute or schedule specialist agent tasks.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        execution_engine: AgentExecutionEngine,
        synthesis_agent: SynthesisAgent,
        max_plan_iterations: int = 2,
        max_total_calls: int = 8,
    ) -> None:
        self.llm_provider = llm_provider
        self.execution_engine = execution_engine
        self.synthesis_agent = synthesis_agent
        self.max_plan_iterations = max_plan_iterations
        self.max_total_calls = max_total_calls

    async def _plan_with_llm(
        self,
        request: str,
        context: AgentExecutionContext,
        iteration: int = 1,
    ) -> ExecutionPlan | None:
        """Attempts to generate a structured ExecutionPlan via LLM generation."""
        user_msg = (
            f"User Request: {request}\n"
            f"Context: request_id={context.request_id}, conversation_id={context.conversation_id}, "
            f"has_doc_ids={bool(context.document_ids)}\n"
            f"Iteration: {iteration}\n"
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

        # Check for UUID document reference in request
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

        if uuid_match:
            doc_id_str = uuid_match.group(0)
            tasks.append(
                AgentTask(
                    task_id="doc_inspect_1",
                    request=f"Inspect document {doc_id_str}",
                    agent_type=AgentType.DOCUMENT,
                    dependencies=[],
                    parameters={"document_id": doc_id_str, "action": "inspect"},
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
        elif has_math and not any(
            kw in req_lower for kw in ["what", "who", "explain", "describe", "search"]
        ):
            # Pure arithmetic / calculation query
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
            # Standard knowledge / research query
            tasks.append(
                AgentTask(
                    task_id="research_1",
                    request=request,
                    agent_type=AgentType.RESEARCH,
                    dependencies=[],
                    parameters={"query": request, "top_k": 5},
                )
            )
            if has_math:
                tasks.append(
                    AgentTask(
                        task_id="analysis_1",
                        request=f"Perform calculation on retrieved research: {request}",
                        agent_type=AgentType.ANALYSIS,
                        dependencies=["research_1"],
                        parameters={},
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
        Creates and validates an ExecutionPlan.
        Attempts structured LLM planning first, validating against schema and DAG acyclicity;
        falls back to deterministic heuristic planning if LLM output is absent or invalid.
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

        fallback_plan = self._plan_heuristic(request, context, iteration=iteration)
        return fallback_plan

    def _should_replan(
        self,
        outcome: ExecutionOutcome,
        iteration: int,
    ) -> bool:
        """
        Determines whether replanning should be triggered based on structured ExecutionOutcome signals.
        Only triggers when iteration limit allows, specialist reported missing evidence, or retriable failure occurred.
        """
        if iteration >= self.max_plan_iterations:
            return False

        # 1. Check for retriable failures
        has_retriable = any(
            f.failure_reason
            in {AgentFailureReason.TIMEOUT, AgentFailureReason.EXECUTION_ERROR}
            for f in outcome.failed_results
        )
        # 2. Check for explicit insufficient evidence reported by ResearchAgent
        has_empty_evidence = any(
            r.metadata.get("insufficient_evidence") is True
            for r in outcome.completed_results
        )

        return has_retriable or has_empty_evidence

    async def execute_request(
        self,
        request: str,
        context: AgentExecutionContext,
        model: str = "gemini-2.5-flash-lite",
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> MultiAgentResponse:
        """
        Executes a complete multi-agent request from planning through synthesis.
        """
        start_time = time.perf_counter()
        total_calls = 0
        task_latencies: dict[str, float] = {}
        all_completed: list[AgentResult] = []
        all_failed: list[AgentResult] = []
        limits_reached: list[str] = []

        current_plan: ExecutionPlan | None = None
        iteration = 0

        while iteration < self.max_plan_iterations:
            iteration += 1
            current_plan = await self.create_plan(request, context, iteration=iteration)

            outcome = await self.execution_engine.execute(
                plan=current_plan,
                context=context,
                cumulative_calls=total_calls,
            )

            total_calls += outcome.total_calls
            limits_reached.extend(outcome.limits_reached)

            for r in outcome.completed_results:
                all_completed.append(r)
                task_latencies[r.task_id] = r.execution_time_ms

            for f in outcome.failed_results:
                all_failed.append(f)
                task_latencies[f.task_id] = f.execution_time_ms

            if not self._should_replan(outcome, iteration):
                break

        # Pass all completed and failed results to SynthesisAgent
        synthesis_req = SynthesisRequest(
            request_id=context.request_id,
            original_request=request,
            specialist_results=all_completed + all_failed,
            context=context,
        )

        answer_text, citations, usage = await self.synthesis_agent.synthesize(
            request=synthesis_req,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        total_time_ms = (time.perf_counter() - start_time) * 1000
        diagnostics = MultiAgentDiagnostics(
            plan_iterations=iteration,
            total_specialist_calls=total_calls,
            task_latencies=task_latencies,
            failed_tasks=[f.task_id for f in all_failed],
            limits_reached=list(set(limits_reached)),
        )

        return MultiAgentResponse(
            answer=answer_text,
            plan=current_plan
            or ExecutionPlan(
                request_id=context.request_id, tasks=[], iteration=iteration
            ),
            specialist_results=all_completed + all_failed,
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
        Streams multi-agent lifecycle events and synthesized text chunks.
        """
        event_queue: list[dict[str, Any]] = []

        async def _event_callback(event_name: str, event_data: dict[str, Any]) -> None:
            event_queue.append({"event": event_name, "data": event_data})

        total_calls = 0
        all_completed: list[AgentResult] = []
        all_failed: list[AgentResult] = []

        current_plan: ExecutionPlan | None = None
        iteration = 0

        while iteration < self.max_plan_iterations:
            iteration += 1
            if iteration > 1:
                yield {
                    "event": "replan_started",
                    "data": {
                        "iteration": iteration,
                        "reason": "Insufficient evidence or retriable error",
                    },
                }

            current_plan = await self.create_plan(request, context, iteration=iteration)

            # Emit plan_created event
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

            event_queue.clear()
            outcome = await self.execution_engine.execute(
                plan=current_plan,
                context=context,
                event_callback=_event_callback,
                cumulative_calls=total_calls,
            )

            # Flush queued execution engine events
            for ev in event_queue:
                yield ev

            total_calls += outcome.total_calls
            all_completed.extend(outcome.completed_results)
            all_failed.extend(outcome.failed_results)

            if not self._should_replan(outcome, iteration):
                break

        # Execute SynthesisAgent stream
        synthesis_req = SynthesisRequest(
            request_id=context.request_id,
            original_request=request,
            specialist_results=all_completed + all_failed,
            context=context,
        )

        async for synth_event in self.synthesis_agent.synthesize_stream(
            request=synthesis_req,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield synth_event

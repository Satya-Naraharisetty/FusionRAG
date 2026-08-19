import json
import logging
import re

from app.chat.domain.interfaces import LLMProvider
from app.chat.domain.models import ChatMessage, ChatRole
from app.chat.domain.multi_agent import (
    AgentFailureReason,
    AgentResult,
    AgentType,
    EvaluationDecision,
    ExecutionOutcome,
    ExecutionPlan,
    MissingRequirement,
    ResultEvaluation,
)

logger = logging.getLogger(__name__)

EVALUATOR_SYSTEM_PROMPT = """You are a result evaluation service in a hierarchical multi-agent system.
Analyze the user request, plan, executed specialist results, and gathered evidence to determine evidence sufficiency.

Evaluation Rules:
1. Evaluate requirement satisfaction independently for each sub-part of the original request.
2. Identify any missing required information or unfulfilled expected outputs.
3. Detect factual contradictions between different evidence items.
4. Output strictly valid JSON matching the schema below.
5. Do NOT generate free-form reasoning text outside JSON.

JSON Schema:
{
  "decision": "SUFFICIENT" | "INSUFFICIENT" | "PARTIAL" | "RETRYABLE_FAILURE" | "TERMINAL_FAILURE",
  "confidence": 0.0 to 1.0,
  "missing_requirements": [
    {
      "requirement": "Description of missing data",
      "reason": "Why it is missing",
      "suggested_agent_type": "RESEARCH" | "DOCUMENT" | "ANALYSIS" | null,
      "priority": 0
    }
  ],
  "contradictions": ["Description of conflicting evidence if any"],
  "recommendations": ["Refinement suggestion"],
  "should_replan": true | false,
  "reason": "Short summary explanation"
}"""


class ResultEvaluator:
    """
    Deterministic result evaluation service with optional structured LLM assistance.
    Evaluates ExecutionOutcome against user intent and task requirements,
    identifying missing requirements, failure classifications, and replanning needs.
    """

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider

    def evaluate_deterministic(
        self,
        original_request: str,
        plan: ExecutionPlan,
        outcome: ExecutionOutcome,
        accumulated_results: dict[str, AgentResult] | None = None,
    ) -> ResultEvaluation:
        """
        Layer 1: Purely deterministic evaluation based on task status, failure reasons,
        empty evidence, and declared task expectations.
        """
        all_results_map: dict[str, AgentResult] = dict(accumulated_results or {})
        for r in (
            outcome.completed_results + outcome.failed_results + outcome.skipped_results
        ):
            all_results_map[r.task_id] = r

        successful_tasks = [r.task_id for r in all_results_map.values() if r.success]
        failed_results = [r for r in all_results_map.values() if not r.success]
        failed_tasks = [r.task_id for r in failed_results]

        evidence_count = sum(
            len(r.evidence) for r in all_results_map.values() if r.success
        )

        # 1. Check for Terminal Failures (e.g. Unauthorized, Validation Errors)
        unauthorized_fails = [
            f
            for f in failed_results
            if f.failure_reason == AgentFailureReason.UNAUTHORIZED
        ]
        if unauthorized_fails:
            return ResultEvaluation(
                decision=EvaluationDecision.TERMINAL_FAILURE,
                confidence=1.0,
                evidence_count=evidence_count,
                successful_tasks=successful_tasks,
                failed_tasks=failed_tasks,
                missing_requirements=[
                    MissingRequirement(
                        requirement=f"Task {f.task_id} authorization",
                        reason=f.error or "Access denied to requested document",
                        suggested_agent_type=f.agent_type,
                    )
                    for f in unauthorized_fails
                ],
                should_replan=False,
                reason="Terminal failure due to unauthorized document access.",
            )

        # 2. Check for Retryable Failures (e.g. Timeout, Execution Error)
        retryable_fails = [
            f
            for f in failed_results
            if f.failure_reason
            in {AgentFailureReason.TIMEOUT, AgentFailureReason.EXECUTION_ERROR}
            and f.failure_reason != AgentFailureReason.UNAUTHORIZED
        ]

        if retryable_fails and evidence_count == 0:
            return ResultEvaluation(
                decision=EvaluationDecision.RETRYABLE_FAILURE,
                confidence=0.9,
                evidence_count=evidence_count,
                successful_tasks=successful_tasks,
                failed_tasks=failed_tasks,
                missing_requirements=[
                    MissingRequirement(
                        requirement=f"Completion of task {f.task_id}",
                        reason=f.error or "Transient execution failure",
                        suggested_agent_type=f.agent_type,
                    )
                    for f in retryable_fails
                ],
                contradictions=[],
                should_replan=True,
                reason="Retryable failure occurred during specialist execution.",
            )

        # 3. Inspect task-level contracts, empty evidence, and missing requirements
        missing_reqs: list[MissingRequirement] = []
        req_lower = original_request.lower()

        # Check explicit task expectations
        for task in plan.tasks:
            res = all_results_map.get(task.task_id)
            if res and res.success:
                # Check for explicit empty evidence metadata flag
                if res.metadata.get("insufficient_evidence") is True or (
                    task.agent_type in {AgentType.RESEARCH, AgentType.DOCUMENT}
                    and len(res.evidence) == 0
                ):
                    missing_reqs.append(
                        MissingRequirement(
                            requirement=f"Evidence for '{task.request}'",
                            reason="Specialist found no relevant chunks or documents.",
                            suggested_agent_type=task.agent_type,
                            priority=1,
                        )
                    )
            elif not res or not res.success:
                missing_reqs.append(
                    MissingRequirement(
                        requirement=f"Output for '{task.request}'",
                        reason=res.error if (res and res.error) else "Task was not executed",
                        suggested_agent_type=task.agent_type,
                        priority=2,
                    )
                )

        # Compound requirement detection (e.g. Q2 vs Q3, or multiple entities)
        # Check if query requests multi-period / multi-entity comparison
        periods = ["q1", "q2", "q3", "q4", "2022", "2023", "2024", "2025"]
        mentioned_periods = [p for p in periods if p in req_lower]
        if len(mentioned_periods) >= 2:
            # Check collected evidence text across all successful tasks
            combined_evidence_text = " ".join(
                ev.content.lower()
                for r in all_results_map.values()
                if r.success
                for ev in r.evidence
            )
            for p in mentioned_periods:
                if p not in combined_evidence_text:
                    # Check if already in missing_reqs
                    if not any(p in mr.requirement.lower() for mr in missing_reqs):
                        missing_reqs.append(
                            MissingRequirement(
                                requirement=f"{p.upper()} revenue/data",
                                reason=f"Evidence for {p.upper()} was requested but not found in retrieved chunks.",
                                suggested_agent_type=AgentType.DOCUMENT
                                if "doc" in req_lower or "pdf" in req_lower
                                else AgentType.RESEARCH,
                                priority=1,
                            )
                        )

        # Factual contradiction detection across evidence items
        contradictions: list[str] = []
        # Simple heuristic check for obvious numeric contradictions if 2 different values for same metric appear
        all_ev_texts = [
            ev.content
            for r in all_results_map.values()
            if r.success
            for ev in r.evidence
        ]
        if len(all_ev_texts) >= 2:
            # e.g., if one chunk says "revenue = $10M" and another says "revenue = $12M"
            match_10m = any(
                "10m" in t.lower() or "$10 million" in t.lower() for t in all_ev_texts
            )
            match_12m = any(
                "12m" in t.lower() or "$12 million" in t.lower() for t in all_ev_texts
            )
            if match_10m and match_12m:
                contradictions.append(
                    "Two authoritative documents report different Q3 revenue values (10M vs 12M)."
                )

        # Decide final evaluation classification
        if retryable_fails and evidence_count == 0 and not missing_reqs:
            return ResultEvaluation(
                decision=EvaluationDecision.RETRYABLE_FAILURE,
                confidence=0.9,
                evidence_count=evidence_count,
                successful_tasks=successful_tasks,
                failed_tasks=failed_tasks,
                missing_requirements=[
                    MissingRequirement(
                        requirement=f"Completion of task {f.task_id}",
                        reason=f.error or "Transient execution failure",
                        suggested_agent_type=f.agent_type,
                    )
                    for f in retryable_fails
                ],
                contradictions=contradictions,
                should_replan=True,
                reason="Retryable failure occurred during specialist execution.",
            )

        if missing_reqs:
            if evidence_count > 0:
                decision = EvaluationDecision.PARTIAL
                reason = f"Partial evidence retrieved ({evidence_count} items), but missing {len(missing_reqs)} requirement(s)."
                return ResultEvaluation(
                    decision=decision,
                    confidence=0.85,
                    evidence_count=evidence_count,
                    successful_tasks=successful_tasks,
                    failed_tasks=failed_tasks,
                    missing_requirements=missing_reqs,
                    contradictions=contradictions,
                    should_replan=True,
                    reason=reason,
                )
            else:
                return ResultEvaluation(
                    decision=EvaluationDecision.INSUFFICIENT,
                    confidence=0.95,
                    evidence_count=evidence_count,
                    successful_tasks=successful_tasks,
                    failed_tasks=failed_tasks,
                    missing_requirements=missing_reqs,
                    contradictions=contradictions,
                    should_replan=True,
                    reason="No evidence retrieved for required tasks.",
                )

        if evidence_count == 0 and any(
            t.agent_type in {AgentType.RESEARCH, AgentType.DOCUMENT} for t in plan.tasks
        ):
            return ResultEvaluation(
                decision=EvaluationDecision.INSUFFICIENT,
                confidence=0.9,
                evidence_count=0,
                successful_tasks=successful_tasks,
                failed_tasks=failed_tasks,
                missing_requirements=[
                    MissingRequirement(
                        requirement="General evidence for user request",
                        reason="No evidence chunks were returned by retrieval.",
                        suggested_agent_type=AgentType.RESEARCH,
                    )
                ],
                should_replan=True,
                reason="No evidence retrieved for research request.",
            )

        return ResultEvaluation(
            decision=EvaluationDecision.SUFFICIENT,
            confidence=0.95,
            evidence_count=evidence_count,
            successful_tasks=successful_tasks,
            failed_tasks=failed_tasks,
            missing_requirements=[],
            contradictions=contradictions,
            should_replan=False,
            reason="All plan tasks completed successfully with sufficient evidence.",
        )

    async def _evaluate_llm(
        self,
        original_request: str,
        plan: ExecutionPlan,
        outcome: ExecutionOutcome,
        deterministic_res: ResultEvaluation,
    ) -> ResultEvaluation | None:
        """Layer 2: Optional structured LLM evaluation call."""
        if not self.llm_provider:
            return None

        # Format input evidence for LLM evaluation
        evidence_summary = []
        for r in outcome.completed_results:
            for ev in r.evidence:
                evidence_summary.append(
                    f"Task {r.task_id} ({r.agent_type.value}) - Doc: {ev.document_name}\nContent: {ev.content}"
                )

        user_msg = (
            f"User Request: {original_request}\n"
            f"Executed Plan Tasks: {[t.model_dump() for t in plan.tasks]}\n"
            f"Retrieved Evidence:\n"
            + ("\n---\n".join(evidence_summary) or "None")
            + "\n\n"
            f"Deterministic evaluation suggestion: decision={deterministic_res.decision.value}, "
            f"evidence_count={deterministic_res.evidence_count}.\n"
            f"Evaluate evidence sufficiency and return strictly valid JSON matching the schema:"
        )

        messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=EVALUATOR_SYSTEM_PROMPT),
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

            json_match = re.search(
                r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL
            )
            if json_match:
                content = json_match.group(1)
            elif "{" in content and "}" in content:
                content = content[content.find("{") : content.rfind("}") + 1]

            eval_dict = json.loads(content)
            raw_decision = str(eval_dict.get("decision", "INSUFFICIENT")).upper()
            if raw_decision not in EvaluationDecision.__members__:
                return None

            decision = EvaluationDecision(raw_decision)
            confidence = float(eval_dict.get("confidence", 0.8))
            confidence = max(0.0, min(1.0, confidence))

            missing_reqs = []
            for mr in eval_dict.get("missing_requirements", []):
                agent_type_val = mr.get("suggested_agent_type")
                sug_agent = (
                    AgentType(str(agent_type_val).upper())
                    if agent_type_val
                    and str(agent_type_val).upper() in AgentType.__members__
                    else None
                )
                missing_reqs.append(
                    MissingRequirement(
                        requirement=str(mr.get("requirement", "Missing data")),
                        reason=str(mr.get("reason", "Unfulfilled")),
                        suggested_agent_type=sug_agent,
                        priority=int(mr.get("priority", 0)),
                    )
                )

            contradictions = [str(c) for c in eval_dict.get("contradictions", [])]
            recommendations = [str(r) for r in eval_dict.get("recommendations", [])]
            should_replan = bool(
                eval_dict.get(
                    "should_replan", decision != EvaluationDecision.SUFFICIENT
                )
            )
            reason = str(eval_dict.get("reason", "LLM evaluation completed."))

            return ResultEvaluation(
                decision=decision,
                confidence=confidence,
                evidence_count=deterministic_res.evidence_count,
                successful_tasks=deterministic_res.successful_tasks,
                failed_tasks=deterministic_res.failed_tasks,
                missing_requirements=missing_reqs,
                contradictions=contradictions,
                recommendations=recommendations,
                should_replan=should_replan,
                reason=reason,
            )
        except Exception as e:
            logger.warning(
                "LLM evaluation failed or returned invalid schema (%s); using deterministic evaluation.",
                e,
            )
            return None

    async def evaluate(
        self,
        original_request: str,
        plan: ExecutionPlan,
        outcome: ExecutionOutcome,
        accumulated_results: dict[str, AgentResult] | None = None,
    ) -> ResultEvaluation:
        """
        Main entry point for result evaluation. Performs deterministic Layer 1 evaluation first,
        and conditionally invokes optional Layer 2 LLM evaluation if semantic check or contradiction check is needed.
        """
        deterministic_res = self.evaluate_deterministic(
            original_request=original_request,
            plan=plan,
            outcome=outcome,
            accumulated_results=accumulated_results,
        )

        # Policy Check: If terminal failure occurred (e.g. Unauthorized), deterministic decision is final
        if deterministic_res.decision == EvaluationDecision.TERMINAL_FAILURE:
            return deterministic_res

        # If deterministic evaluation clearly classified SUFFICIENT or clear missing requirements with no provider
        if not self.llm_provider:
            return deterministic_res

        # LLM evaluation is invoked only when deterministic evaluation requires semantic check or contradiction comparison with confidence < 0.9
        needs_llm_check = deterministic_res.confidence < 0.9 and (
            deterministic_res.decision
            in {EvaluationDecision.PARTIAL, EvaluationDecision.INSUFFICIENT}
            or bool(deterministic_res.contradictions)
        )

        if not needs_llm_check:
            return deterministic_res

        llm_res = await self._evaluate_llm(
            original_request=original_request,
            plan=plan,
            outcome=outcome,
            deterministic_res=deterministic_res,
        )

        if not llm_res:
            return deterministic_res

        # Pass LLM output through deterministic policy override checks:
        # 1. LLM cannot override a terminal failure
        if deterministic_res.decision == EvaluationDecision.TERMINAL_FAILURE:
            return deterministic_res

        # 2. LLM cannot declare SUFFICIENT if evidence_count == 0 and research task was executed
        if (
            llm_res.decision == EvaluationDecision.SUFFICIENT
            and deterministic_res.evidence_count == 0
        ):
            if any(
                t.agent_type in {AgentType.RESEARCH, AgentType.DOCUMENT}
                for t in plan.tasks
            ):
                llm_res.decision = EvaluationDecision.INSUFFICIENT
                llm_res.should_replan = True
                llm_res.reason = "Override: Cannot mark SUFFICIENT when zero evidence chunks were retrieved."

        return llm_res

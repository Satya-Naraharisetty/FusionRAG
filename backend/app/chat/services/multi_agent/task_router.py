import asyncio
import json
import logging
import re

from app.chat.domain.interfaces import LLMProvider
from app.chat.domain.models import ChatMessage, ChatRole
from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentTask,
    AgentType,
    CapabilityDescriptor,
    CapabilityType,
    RoutingDecision,
)
from app.chat.services.multi_agent.capability_registry import CapabilityRegistry
from app.chat.services.multi_agent.observability import AgentObservabilityService

logger = logging.getLogger(__name__)

# Authoritative mapping from executable AgentType to CapabilityType
AGENT_TYPE_TO_CAPABILITY_TYPE: dict[AgentType, CapabilityType] = {
    AgentType.RESEARCH: CapabilityType.RESEARCH,
    AgentType.DOCUMENT: CapabilityType.DOCUMENT_INSPECTION,
    AgentType.ANALYSIS: CapabilityType.ANALYSIS,
    AgentType.WEB_SEARCH: CapabilityType.WEB_SEARCH,
}

# Non-executable agent types
NON_EXECUTABLE_AGENT_TYPES = {
    AgentType.MASTER,
    AgentType.SYNTHESIS,
}


class TaskRouter:
    """
    Deterministic routing service that inspects an AgentTask, evaluates capability requirements,
    enforces authorization and budget constraints, and returns a structured RoutingDecision.

    Not an agent. Does not execute specialists directly.
    LLM recommendations are optional, advisory only, and strictly validated against policy.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        llm_provider: LLMProvider | None = None,
        enable_llm_router: bool = False,
        observability: AgentObservabilityService | None = None,
        max_cost_units: float = 100.0,
        max_latency_ms: float = 30000.0,
        llm_timeout: float = 5.0,
    ) -> None:
        self.registry = registry
        self.llm_provider = llm_provider
        self.enable_llm_router = enable_llm_router
        self.observability = observability
        self.max_cost_units = max_cost_units
        self.max_latency_ms = max_latency_ms
        self.llm_timeout = llm_timeout

    def _check_context_availability(
        self, required_context: list[str], context: AgentExecutionContext
    ) -> bool:
        """Verifies that all required context keys are present and non-empty in context."""
        for req in required_context:
            if req == "user_id":
                if not context.user_id:
                    return False
            elif req == "conversation_id":
                if not context.conversation_id:
                    return False
            elif req == "document_ids":
                if not context.document_ids:
                    return False
            else:
                # Check metadata or attribute
                if not getattr(context, req, None) and req not in context.metadata:
                    return False
        return True

    def _extract_task_operation(self, task: AgentTask) -> str:
        """Extracts the intended operation name from task requirements or parameters."""
        if task.capability_requirements:
            for req in task.capability_requirements:
                if req.operation:
                    return req.operation.strip().lower()
        if "action" in task.parameters:
            return str(task.parameters["action"]).strip().lower()
        if "operation" in task.parameters:
            return str(task.parameters["operation"]).strip().lower()
        return ""

    async def _get_llm_advisory(
        self,
        task: AgentTask,
        eligible_descriptors: list[CapabilityDescriptor],
    ) -> str | None:
        """
        Queries the LLM for an advisory capability recommendation.
        Returns recommended capability_id if valid, or None.
        """
        if not self.enable_llm_router or not self.llm_provider:
            return None

        prompt = (
            f"Task: {task.request}\n"
            f"Agent Type: {task.agent_type.value}\n"
            f"Eligible Capabilities: {[d.capability_id for d in eligible_descriptors]}\n"
            f'Recommend the single best capability_id as JSON: {{"capability_id": "..."}}'
        )
        messages = [
            ChatMessage(
                role=ChatRole.SYSTEM,
                content="You are a routing advisory module. Output strictly JSON.",
            ),
            ChatMessage(role=ChatRole.USER, content=prompt),
        ]

        try:
            response = await asyncio.wait_for(
                self.llm_provider.generate(
                    messages=messages,
                    model="gemini-3.5-flash-lite",
                    temperature=0.0,
                    max_tokens=150,
                ),
                timeout=self.llm_timeout,
            )
            content = (
                response[0] if isinstance(response, tuple) else response.content or ""
            ).strip()
            json_match = re.search(r"\{.*?\}", content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                rec_id = data.get("capability_id")
                # Strict validation: recommended ID must be in eligible descriptors
                if any(d.capability_id == rec_id for d in eligible_descriptors):
                    return str(rec_id)
        except Exception as e:
            logger.warning("LLM capability advisory failed or timed out: %s", e)

        return None

    async def route(
        self,
        task: AgentTask,
        context: AgentExecutionContext,
        remaining_latency_ms: float | None = None,
        remaining_cost_units: float | None = None,
    ) -> RoutingDecision:
        """
        Determines the appropriate capability for executing the given AgentTask.
        Enforces authoritative agent-type consistency, budget ceilings, context requirements,
        and security boundaries.
        """
        rejected: dict[str, str] = {}

        # 1. Check for non-executable or disallowed AgentType
        if task.agent_type in NON_EXECUTABLE_AGENT_TYPES:
            if self.observability:
                self.observability.record_security_event(
                    request_id=context.request_id,
                    event_type="unauthorized_agent_type_routing",
                    reason="POLICY_REJECTED",
                    task_id=task.task_id,
                    agent_type=task.agent_type.value,
                    user_id=context.user_id,
                    details={"attempted_agent_type": task.agent_type.value},
                )
            return RoutingDecision(
                task_id=task.task_id,
                selected_capability_id=None,
                capability_type=None,
                eligible_capabilities=[],
                rejected_capabilities={"agent_type": "POLICY_REJECTED"},
                reason_code="POLICY_REJECTED",
                confidence=0.0,
            )

        target_cap_type = AGENT_TYPE_TO_CAPABILITY_TYPE.get(task.agent_type)
        if not target_cap_type:
            if self.observability:
                self.observability.record_security_event(
                    request_id=context.request_id,
                    event_type="unmapped_agent_type_routing",
                    reason="POLICY_REJECTED",
                    task_id=task.task_id,
                    agent_type=task.agent_type.value,
                    user_id=context.user_id,
                )
            return RoutingDecision(
                task_id=task.task_id,
                selected_capability_id=None,
                capability_type=None,
                eligible_capabilities=[],
                rejected_capabilities={"agent_type": "POLICY_REJECTED"},
                reason_code="POLICY_REJECTED",
                confidence=0.0,
            )

        # 2. Check capability requirements for cross-class contradictions
        if task.capability_requirements:
            for req in task.capability_requirements:
                if req.capability_type and req.capability_type != target_cap_type:
                    if self.observability:
                        self.observability.record_security_event(
                            request_id=context.request_id,
                            event_type="capability_mismatch",
                            reason="CAPABILITY_MISMATCH",
                            task_id=task.task_id,
                            agent_type=task.agent_type.value,
                            user_id=context.user_id,
                            details={
                                "expected_capability_type": target_cap_type.value,
                                "requested_capability_type": req.capability_type.value,
                            },
                        )
                    return RoutingDecision(
                        task_id=task.task_id,
                        selected_capability_id=None,
                        capability_type=target_cap_type,
                        eligible_capabilities=[],
                        rejected_capabilities={
                            "capability_requirements": "CAPABILITY_MISMATCH"
                        },
                        reason_code="CAPABILITY_MISMATCH",
                        confidence=0.0,
                    )

        # 3. Check preferred capability consistency if specified
        if task.preferred_capability:
            registered_pref = self.registry.get(task.preferred_capability)
            if not registered_pref:
                rejected[task.preferred_capability] = "UNKNOWN_CAPABILITY"
            elif registered_pref.capability_type != target_cap_type:
                rejected[task.preferred_capability] = "CAPABILITY_MISMATCH"
                if self.observability:
                    self.observability.record_security_event(
                        request_id=context.request_id,
                        event_type="preferred_capability_mismatch",
                        reason="CAPABILITY_MISMATCH",
                        task_id=task.task_id,
                        agent_type=task.agent_type.value,
                        user_id=context.user_id,
                        details={"preferred_capability": task.preferred_capability},
                    )

        # 4. Fetch all descriptors for this capability type
        candidates = self.registry.list_by_type(target_cap_type)
        if not candidates:
            # Check if capabilities exist but are disabled
            all_for_type = [
                c
                for c in self.registry.list_all()
                if c.capability_type == target_cap_type
            ]
            for c in all_for_type:
                if not c.enabled:
                    rejected[c.capability_id] = "CAPABILITY_DISABLED"

            reason = "CAPABILITY_DISABLED" if rejected else "NO_CAPABILITY_AVAILABLE"
            return RoutingDecision(
                task_id=task.task_id,
                selected_capability_id=None,
                capability_type=target_cap_type,
                eligible_capabilities=[],
                rejected_capabilities=rejected,
                reason_code=reason,
                confidence=0.0,
            )

        # 5. Evaluate candidate eligibility against constraints
        eligible: list[CapabilityDescriptor] = []
        op_name = self._extract_task_operation(task)

        for desc in candidates:
            # Check executable_worker metadata
            if not desc.metadata.get("executable_worker", True):
                rejected[desc.capability_id] = "POLICY_REJECTED"
                continue

            # Check enabled
            if not desc.enabled:
                rejected[desc.capability_id] = "CAPABILITY_DISABLED"
                continue

            # Check context requirements
            if not self._check_context_availability(desc.required_context, context):
                rejected[desc.capability_id] = "CONTEXT_MISSING"
                continue

            # Check task-level latency limit
            if (
                task.max_latency_ms is not None
                and desc.estimated_latency_ms > task.max_latency_ms
            ):
                rejected[desc.capability_id] = "BUDGET_EXCEEDED"
                continue

            # Check task-level cost limit
            if (
                task.max_cost_units is not None
                and desc.estimated_cost_units > task.max_cost_units
            ):
                rejected[desc.capability_id] = "BUDGET_EXCEEDED"
                continue

            # Check remaining request latency budget
            if (
                remaining_latency_ms is not None
                and desc.estimated_latency_ms > remaining_latency_ms
            ):
                rejected[desc.capability_id] = "BUDGET_EXCEEDED"
                continue

            # Check remaining request cost budget
            if (
                remaining_cost_units is not None
                and desc.estimated_cost_units > remaining_cost_units
            ):
                rejected[desc.capability_id] = "BUDGET_EXCEEDED"
                continue

            eligible.append(desc)

        if not eligible:
            # Determine reason code from rejections
            if any(v == "BUDGET_EXCEEDED" for v in rejected.values()):
                reason_code = "BUDGET_EXCEEDED"
            elif any(v == "CONTEXT_MISSING" for v in rejected.values()):
                reason_code = "CONTEXT_MISSING"
            elif any(v == "CAPABILITY_DISABLED" for v in rejected.values()):
                reason_code = "CAPABILITY_DISABLED"
            else:
                reason_code = "NO_CAPABILITY_AVAILABLE"

            return RoutingDecision(
                task_id=task.task_id,
                selected_capability_id=None,
                capability_type=target_cap_type,
                eligible_capabilities=[],
                rejected_capabilities=rejected,
                reason_code=reason_code,
                confidence=0.0,
            )

        # 6. Check advisory LLM router recommendation
        advisory_selected_id: str | None = None
        if self.enable_llm_router:
            advisory_selected_id = await self._get_llm_advisory(task, eligible)

        # 7. Deterministic ranking
        def _rank_key(
            desc: CapabilityDescriptor,
        ) -> tuple[int, int, int, float, float, str]:
            # Priority 0: LLM advisory match if present
            is_llm_match = (
                0
                if (advisory_selected_id and desc.capability_id == advisory_selected_id)
                else 1
            )
            # Priority 1: Preferred capability match
            is_pref_match = (
                0
                if (
                    task.preferred_capability
                    and desc.capability_id == task.preferred_capability
                )
                else 1
            )
            # Priority 2: Exact operation match
            is_op_match = (
                0
                if (
                    op_name
                    and op_name in [op.lower() for op in desc.supported_operations]
                )
                else 1
            )
            # Priority 3: Estimated latency (lower is better)
            # Priority 4: Estimated cost (lower is better)
            # Priority 5: Deterministic tie-breaker on ID
            return (
                is_llm_match,
                is_pref_match,
                is_op_match,
                desc.estimated_latency_ms,
                desc.estimated_cost_units,
                desc.capability_id,
            )

        sorted_eligible = sorted(eligible, key=_rank_key)
        selected = sorted_eligible[0]

        # 8. Determine reason code
        if (
            task.preferred_capability
            and selected.capability_id == task.preferred_capability
        ):
            reason_code = "EXACT_CAPABILITY_MATCH"
        elif op_name and op_name in [
            op.lower() for op in selected.supported_operations
        ]:
            reason_code = "EXACT_CAPABILITY_MATCH"
        elif len(sorted_eligible) == 1:
            reason_code = "EXACT_CAPABILITY_MATCH"
        else:
            reason_code = "BEST_AVAILABLE_CAPABILITY"

        return RoutingDecision(
            task_id=task.task_id,
            selected_capability_id=selected.capability_id,
            capability_type=selected.capability_type,
            eligible_capabilities=[d.capability_id for d in sorted_eligible],
            rejected_capabilities=rejected,
            reason_code=reason_code,
            confidence=1.0,
            estimated_latency_ms=selected.estimated_latency_ms,
            estimated_cost_units=selected.estimated_cost_units,
        )

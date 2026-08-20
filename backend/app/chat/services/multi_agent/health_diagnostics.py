from typing import Any

from app.chat.domain.multi_agent import AgentType
from app.chat.services.multi_agent.base import BaseSpecialistAgent
from app.chat.services.multi_agent.capability_registry import CapabilityRegistry
from app.chat.services.multi_agent.task_router import TaskRouter
from app.core.config import settings

REQUIRED_SPECIALIST_TYPES = {
    AgentType.RESEARCH,
    AgentType.DOCUMENT,
    AgentType.ANALYSIS,
}


def get_agent_readiness_report(
    capability_registry: CapabilityRegistry | None = None,
    specialists: list[BaseSpecialistAgent] | None = None,
    task_router: TaskRouter | None = None,
    has_llm_provider: bool = True,
    has_retrieval_service: bool = True,
) -> dict[str, Any]:
    """
    Generates a sanitized readiness and health report for the multi-agent subsystem.
    Contains strictly operational state, counts, and capability IDs.
    Never exposes API keys, credentials, database connection strings, or user information.
    """
    specialist_map = {s.agent_type for s in (specialists or [])}
    registered_specialists_ok = REQUIRED_SPECIALIST_TYPES.issubset(specialist_map)

    caps = capability_registry.list_all() if capability_registry else []
    registry_ok = len(caps) > 0

    routing_ok = task_router is not None or settings.CAPABILITY_ROUTING_ENABLED

    is_ready = (
        settings.ENABLE_MULTI_AGENT
        and registry_ok
        and registered_specialists_ok
        and routing_ok
        and has_llm_provider
        and has_retrieval_service
    )

    return {
        "status": "ready"
        if is_ready
        else ("degraded" if settings.ENABLE_MULTI_AGENT else "disabled"),
        "multi_agent_enabled": settings.ENABLE_MULTI_AGENT,
        "capability_registry_initialized": registry_ok,
        "registered_capabilities_count": len(caps),
        "registered_capabilities": [c.capability_id for c in caps],
        "required_specialists_registered": registered_specialists_ok,
        "registered_specialists": [s.value for s in specialist_map],
        "routing_enabled": routing_ok,
        "llm_planner_available": has_llm_provider,
        "retrieval_subsystem_available": has_retrieval_service,
        "observability_enabled": settings.AGENT_OBSERVABILITY_ENABLED,
    }

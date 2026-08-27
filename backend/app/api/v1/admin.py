import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

# Lazily import DI dependency providers
from app.api.dependencies import (
    check_rate_limit,
    get_current_user_context,
    get_llm_provider,
)
from app.chat.infrastructure.router import LLMProviderRouter
from app.core.cache.interfaces import BaseCache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin Operations"])


def check_admin_user(
    user_context: dict[str, Any] = Depends(get_current_user_context),
) -> dict[str, Any]:
    """Dependency to restrict admin endpoints to users with the 'admin' role."""
    if user_context.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permissions required to perform this action.",
        )
    return user_context


# Resolve Cache in route dependency injection dynamically
def get_cache_provider() -> BaseCache:
    # Resolve get_cache dynamically from dependencies to avoid circular imports
    from app.api.dependencies import get_cache

    return get_cache()


@router.post(
    "/cache/clear",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(check_rate_limit)],
)
async def clear_cache(
    namespace: str | None = None,
    cache: BaseCache = Depends(get_cache_provider),
    _admin: dict[str, Any] = Depends(check_admin_user),
) -> dict[str, str]:
    """Clear specific cache namespace or all namespaces if empty."""
    try:
        if namespace:
            await cache.invalidate_namespace(namespace)
            return {"message": f"Successfully invalidated cache namespace: {namespace}"}
        else:
            # List of all namespaces we use
            for ns in [
                "prompt_rewrite",
                "embeddings",
                "conversation_memory",
                "retrieval_results",
                "evaluation_benchmarks",
                "tool_executions",
            ]:
                await cache.invalidate_namespace(ns)
            return {"message": "Successfully invalidated all cache namespaces."}
    except Exception:
        logger.exception("Failed to clear cache due to an internal error.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear cache due to an internal error.",
        )


@router.get("/operational-status", status_code=status.HTTP_200_OK)
async def get_operational_status(
    llm_provider: Any = Depends(get_llm_provider),
    _admin: dict[str, Any] = Depends(check_admin_user),
) -> dict[str, Any]:
    """Retrieve operational metrics including circuit breaker states and system health."""
    status_report: dict[str, Any] = {
        "status": "operational",
        "circuit_breakers": {},
    }

    # Inspect circuit breakers if LLMProvider is wrapped in router
    if isinstance(llm_provider, LLMProviderRouter):
        for provider_key in getattr(llm_provider, "_breakers", {}).keys():
            breaker = llm_provider.get_circuit_breaker(provider_key)

            if breaker:
                status_report["circuit_breakers"][provider_key] = {
                    "state": breaker.state,
                    "failure_count": breaker.failure_count,
                    "failure_threshold": breaker.failure_threshold,
                }
    else:
        status_report["circuit_breakers"]["general"] = (
            "Not configured (fallback active)"
        )

    return status_report

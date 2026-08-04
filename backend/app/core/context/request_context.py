from contextvars import ContextVar

from pydantic import BaseModel, Field


class RequestContext(BaseModel):
    user_id: str | None = None
    role: str | None = None
    tenant_id: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    client_ip: str | None = None
    permissions: list[str] = Field(default_factory=list)


# Async-safe context variable to store the RequestContext
current_request_context: ContextVar[RequestContext] = ContextVar(
    "request_context", default=RequestContext()
)

from contextvars import ContextVar
from typing import List, Optional

from pydantic import BaseModel, Field


class RequestContext(BaseModel):
    user_id: Optional[str] = None
    role: Optional[str] = None
    tenant_id: Optional[str] = None
    request_id: Optional[str] = None
    trace_id: Optional[str] = None
    client_ip: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)


# Async-safe context variable to store the RequestContext
current_request_context: ContextVar[RequestContext] = ContextVar(
    "request_context", default=RequestContext()
)

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ToolCategory(str, Enum):
    RETRIEVAL = "RETRIEVAL"
    UTILITY = "UTILITY"
    SYSTEM = "SYSTEM"
    KNOWLEDGE = "KNOWLEDGE"
    BUSINESS = "BUSINESS"


class ToolPermission(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    ADMIN = "ADMIN"


class AgentState(str, Enum):
    THINKING = "THINKING"
    CALLING_TOOL = "CALLING_TOOL"
    WAITING_TOOL = "WAITING_TOOL"
    OBSERVING_RESULT = "OBSERVING_RESULT"
    FINISHED = "FINISHED"


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema parameter mapping


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class ToolResult(BaseModel):
    tool_call_id: str
    name: str
    content: str
    structured_output: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_error: bool = False
    execution_time_ms: float = 0.0


class ToolContext(BaseModel):
    user_id: UUID
    conversation_id: UUID
    db_session: Any

    model_config = ConfigDict(arbitrary_types_allowed=True)


class AgentIteration(BaseModel):
    step: int
    state: AgentState
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    assistant_response: str | None = None
    thought_tokens: int = 0
    tool_latency: float = 0.0
    provider_latency: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentResponse(BaseModel):
    answer: str
    iterations: list[AgentIteration]
    total_prompt_tokens: int
    total_completion_tokens: int
    total_time_ms: float
    model: str

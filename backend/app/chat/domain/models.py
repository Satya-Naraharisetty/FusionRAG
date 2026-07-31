from enum import Enum
from uuid import UUID
from pydantic import BaseModel, Field
from app.documents.domain.models import RetrievedChunk


class ChatRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    role: ChatRole
    content: str


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class Citation(BaseModel):
    document_id: UUID
    document_name: str
    chunk_id: UUID
    chunk_index: int


class GroundedContext(BaseModel):
    concatenated_context: str
    chunk_references: list[RetrievedChunk]
    token_estimate: int


class AnswerResponse(BaseModel):
    answer: str
    citations: list[Citation]
    retrieval_time_ms: float
    generation_time_ms: float
    total_time_ms: float
    model: str
    usage: Usage

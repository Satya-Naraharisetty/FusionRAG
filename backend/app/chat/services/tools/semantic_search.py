import json
import uuid
from typing import Any

from app.chat.domain.agents import (
    ToolCategory,
    ToolContext,
    ToolDefinition,
    ToolPermission,
    ToolResult,
)
from app.chat.services.tools.base import BuiltinTool
from app.documents.services.retrieval_service import RetrievalService


class SearchKnowledgeTool(BuiltinTool):
    def __init__(self, retrieval_service: RetrievalService) -> None:
        self.retrieval_service = retrieval_service

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_knowledge",
            description=(
                "Search for semantically relevant chunks of text within uploaded "
                "documents using natural language queries."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to match against document content.",
                    },
                    "document_ids": {
                        "type": "array",
                        "items": {"type": "string", "format": "uuid"},
                        "description": "Optional list of document UUIDs to restrict the search.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Optional maximum number of results to return (default is 5).",
                    },
                },
                "required": ["query"],
            },
        )

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.KNOWLEDGE

    @property
    def required_permission(self) -> ToolPermission:
        return ToolPermission.READ

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
        cancellation_token: Any | None = None,
    ) -> ToolResult:
        query = arguments["query"]
        doc_ids = arguments.get("document_ids")
        top_k = arguments.get("top_k") or 5

        parsed_doc_ids = None
        if doc_ids:
            parsed_doc_ids = [uuid.UUID(d) for d in doc_ids]

        # Conversation scope enforcement: the orchestrator pins the documents
        # this conversation may search (chat-scoped attachments always, global
        # docs only after an @documents mention). Any model-supplied ids are
        # intersected with that set; with no ids supplied the search is
        # restricted to it outright. With no pinned scope (None) the pre-
        # mention behaviour of a user-wide search is preserved.
        allowed = context.allowed_document_ids
        if allowed:
            allowed_set = set(allowed)
            if parsed_doc_ids is not None:
                parsed_doc_ids = [
                    doc_id
                    for doc_id in parsed_doc_ids
                    if doc_id in allowed_set
                ]
            else:
                parsed_doc_ids = list(allowed)

        search_result = await self.retrieval_service.retrieve(
            query=query,
            user_id=context.user_id,
            top_k=top_k,
            document_ids=parsed_doc_ids,
        )

        serialized_chunks = []
        for chunk in search_result.retrieved_chunks:
            serialized_chunks.append(
                {
                    "chunk_id": str(chunk.chunk_id),
                    "document_id": str(chunk.document_id),
                    "document_name": chunk.document_name,
                    "text": chunk.text,
                    "similarity_score": chunk.similarity_score,
                    "chunk_index": chunk.chunk_index,
                }
            )

        return ToolResult(
            tool_call_id="",
            name=self.definition.name,
            content=json.dumps(serialized_chunks),
            structured_output=serialized_chunks,
            metadata={"count": len(serialized_chunks)},
            is_error=False,
        )

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.chat.domain.agents import (
    ToolCategory,
    ToolContext,
    ToolDefinition,
    ToolPermission,
    ToolResult,
)
from app.chat.services.tools.base import BuiltinTool
from app.documents.infrastructure.persistence.models import SQLAlchemyChunk


class CitationLookupTool(BuiltinTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="citation_lookup",
            description=(
                "Verify the citation details for a given chunk ID, returning the "
                "document name, chunk index, and document UUID."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "chunk_id": {
                        "type": "string",
                        "format": "uuid",
                        "description": "The unique UUID of the chunk to verify.",
                    }
                },
                "required": ["chunk_id"],
            },
        )

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.RETRIEVAL

    @property
    def required_permission(self) -> ToolPermission:
        return ToolPermission.READ

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
        cancellation_token: Any | None = None,
    ) -> ToolResult:
        try:
            chunk_id = uuid.UUID(arguments["chunk_id"])
        except ValueError:
            return ToolResult(
                tool_call_id="",
                name=self.definition.name,
                content=f"Invalid UUID format: {arguments['chunk_id']}",
                is_error=True,
            )

        db = context.db_session
        if hasattr(db, "execute"):
            stmt = (
                select(SQLAlchemyChunk)
                .options(selectinload(SQLAlchemyChunk.document))
                .where(SQLAlchemyChunk.id == chunk_id)
            )
            import inspect

            if inspect.iscoroutinefunction(db.execute) or inspect.isawaitable(
                db.execute(stmt)
            ):
                res = await db.execute(stmt)
            else:
                res = db.execute(stmt)
            chunk = res.scalar_one_or_none()
        elif hasattr(db, "query"):
            chunk = (
                db.query(SQLAlchemyChunk).filter(SQLAlchemyChunk.id == chunk_id).first()
            )
        else:
            chunk = None

        if not chunk:
            return ToolResult(
                tool_call_id="",
                name=self.definition.name,
                content=f"Chunk with ID {chunk_id} not found for citation check.",
                is_error=True,
            )

        if chunk.document.user_id != context.user_id:
            return ToolResult(
                tool_call_id="",
                name=self.definition.name,
                content="Access Denied: You do not own this citation's parent document.",
                is_error=True,
            )

        # Enforce scope: CONVERSATION docs must belong to this conversation;
        # LIBRARY docs are only accessible if the user mentioned @documents.
        doc_scope = getattr(chunk.document, "scope", None)
        if doc_scope == "CONVERSATION":
            if str(chunk.document.conversation_id) != str(context.conversation_id):
                return ToolResult(
                    tool_call_id="",
                    name=self.definition.name,
                    content="Access Denied: This citation belongs to a different conversation.",
                    is_error=True,
                )
        elif doc_scope == "LIBRARY":
            if not context.include_library_documents:
                return ToolResult(
                    tool_call_id="",
                    name=self.definition.name,
                    content="Access Denied: Library documents are not in scope for this chat turn.",
                    is_error=True,
                )

        data = {
            "chunk_id": str(chunk.id),
            "document_id": str(chunk.document_id),
            "document_name": chunk.document.original_filename,
            "chunk_index": chunk.chunk_index,
        }

        return ToolResult(
            tool_call_id="",
            name=self.definition.name,
            content=json.dumps(data),
            structured_output=data,
            is_error=False,
        )

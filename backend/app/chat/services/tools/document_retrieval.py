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
from app.documents.infrastructure.persistence.models import SQLAlchemyDocument


class RetrieveDocumentTool(BuiltinTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="retrieve_document",
            description="Retrieve metadata for a specific document by its UUID.",
            parameters={
                "type": "object",
                "properties": {
                    "document_id": {
                        "type": "string",
                        "format": "uuid",
                        "description": "The unique UUID of the document.",
                    }
                },
                "required": ["document_id"],
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
            doc_id = uuid.UUID(arguments["document_id"])
        except ValueError:
            return ToolResult(
                tool_call_id="",
                name=self.definition.name,
                content=f"Invalid UUID format: {arguments['document_id']}",
                is_error=True,
            )

        db = context.db_session
        doc = db.query(SQLAlchemyDocument).filter(SQLAlchemyDocument.id == doc_id).first()

        if not doc:
            return ToolResult(
                tool_call_id="",
                name=self.definition.name,
                content=f"Document with ID {doc_id} not found.",
                is_error=True,
            )

        if doc.user_id != context.user_id:
            return ToolResult(
                tool_call_id="",
                name=self.definition.name,
                content="Access Denied: You do not own this document.",
                is_error=True,
            )

        metadata = {
            "document_id": str(doc.id),
            "filename": doc.filename,
            "original_filename": doc.original_filename,
            "content_type": doc.content_type,
            "file_size": doc.file_size,
            "status": doc.status,
            "page_count": doc.page_count,
            "word_count": doc.word_count,
            "language": doc.language,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }

        return ToolResult(
            tool_call_id="",
            name=self.definition.name,
            content=json.dumps(metadata),
            structured_output=metadata,
            is_error=False,
        )

import logging
import time
from uuid import UUID

from app.chat.domain.models import Citation
from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentFailureReason,
    AgentResult,
    AgentTask,
    AgentTaskStatus,
    AgentType,
    EvidenceItem,
)
from app.chat.services.multi_agent.base import BaseSpecialistAgent
from app.documents.domain.interfaces import ChunkRepository, DocumentRepository
from app.documents.domain.models import DocumentScope

logger = logging.getLogger(__name__)


class DocumentAgent(BaseSpecialistAgent):
    """
    Document specialist agent.
    Inspects KNOWN or explicitly identified documents and chunks.
    Retrieves document metadata, chunk contents, and structural data with strict
    user and conversation authorization checks.
    """

    def __init__(
        self,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository | None = None,
    ) -> None:
        self.document_repo = document_repo
        self.chunk_repo = chunk_repo

    @property
    def agent_type(self) -> AgentType:
        return AgentType.DOCUMENT

    async def execute_task(
        self,
        task: AgentTask,
        context: AgentExecutionContext,
    ) -> AgentResult:
        start_time = time.perf_counter()
        doc_id_raw = task.parameters.get("document_id")
        chunk_id_raw = task.parameters.get("chunk_id")
        action = task.parameters.get("action", "inspect")

        try:
            # 1. Action: List documents in scope
            if action == "list_documents" or (not doc_id_raw and not chunk_id_raw):
                if context.conversation_id:
                    docs = await self.document_repo.list_by_conversation(
                        context.conversation_id, context.user_id
                    )
                else:
                    docs = await self.document_repo.list_by_user(context.user_id)

                doc_summaries = [
                    f"- {d.original_filename or d.filename} (ID: {d.id}, Size: {d.file_size}B, Pages: {d.page_count})"
                    for d in docs
                ]
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                return AgentResult(
                    task_id=task.task_id,
                    agent_type=self.agent_type,
                    status=AgentTaskStatus.COMPLETED,
                    success=True,
                    output="\n".join(doc_summaries)
                    if doc_summaries
                    else "No documents found.",
                    evidence=[],
                    citations=[],
                    metadata={"document_count": len(docs)},
                    execution_time_ms=elapsed_ms,
                )

            # 2. Parse Document ID
            doc_id: UUID | None = None
            if doc_id_raw:
                try:
                    doc_id = UUID(str(doc_id_raw))
                except (ValueError, TypeError):
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    return AgentResult(
                        task_id=task.task_id,
                        agent_type=self.agent_type,
                        status=AgentTaskStatus.FAILED,
                        success=False,
                        output="",
                        error=f"Invalid UUID for document_id: {doc_id_raw}",
                        failure_reason=AgentFailureReason.VALIDATION_ERROR,
                        execution_time_ms=elapsed_ms,
                    )

            if doc_id is None:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                return AgentResult(
                    task_id=task.task_id,
                    agent_type=self.agent_type,
                    status=AgentTaskStatus.FAILED,
                    success=False,
                    output="",
                    error="document_id parameter is required for document inspection",
                    failure_reason=AgentFailureReason.VALIDATION_ERROR,
                    execution_time_ms=elapsed_ms,
                )

            # 3. Retrieve document and verify authorization
            doc = await self.document_repo.get_by_id(doc_id)
            if not doc:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                return AgentResult(
                    task_id=task.task_id,
                    agent_type=self.agent_type,
                    status=AgentTaskStatus.FAILED,
                    success=False,
                    output="",
                    error=f"Document with ID {doc_id} not found.",
                    failure_reason=AgentFailureReason.EXECUTION_ERROR,
                    execution_time_ms=elapsed_ms,
                )

            # Ownership security check
            if doc.user_id != context.user_id:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                return AgentResult(
                    task_id=task.task_id,
                    agent_type=self.agent_type,
                    status=AgentTaskStatus.FAILED,
                    success=False,
                    output="",
                    error="Access Denied: You do not own this document.",
                    failure_reason=AgentFailureReason.UNAUTHORIZED,
                    execution_time_ms=elapsed_ms,
                )

            # Scope check: CONVERSATION scope must match this conversation
            if doc.scope == DocumentScope.CONVERSATION and context.conversation_id:
                if doc.conversation_id != context.conversation_id:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    return AgentResult(
                        task_id=task.task_id,
                        agent_type=self.agent_type,
                        status=AgentTaskStatus.FAILED,
                        success=False,
                        output="",
                        error="Access Denied: Document belongs to a different conversation.",
                        failure_reason=AgentFailureReason.UNAUTHORIZED,
                        execution_time_ms=elapsed_ms,
                    )

            # 4. Fetch chunks if chunk_repo is available
            evidence_items: list[EvidenceItem] = []
            citations: list[Citation] = []
            chunk_texts: list[str] = []

            if self.chunk_repo:
                chunks = await self.chunk_repo.list_by_document(doc_id)
                # Filter by chunk_id if specified
                if chunk_id_raw:
                    try:
                        target_chunk_id = UUID(str(chunk_id_raw))
                        chunks = [c for c in chunks if c.id == target_chunk_id]
                    except (ValueError, TypeError):
                        pass

                for c in chunks:
                    evidence_items.append(
                        EvidenceItem(
                            chunk_id=c.id,
                            document_id=doc.id,
                            document_name=doc.original_filename or doc.filename,
                            content=c.text,
                            metadata={"chunk_index": c.chunk_index},
                        )
                    )
                    citations.append(
                        Citation(
                            document_id=doc.id,
                            document_name=doc.original_filename or doc.filename,
                            chunk_id=c.id,
                            chunk_index=c.chunk_index,
                        )
                    )
                    chunk_texts.append(f"[Chunk {c.chunk_index}]: {c.text}")

            output_summary = (
                f"Document: {doc.original_filename or doc.filename} (ID: {doc.id})\n"
                f"Status: {doc.status.value if hasattr(doc.status, 'value') else doc.status}\n"
                f"Page count: {doc.page_count}, Word count: {doc.word_count}, Size: {doc.file_size} bytes\n"
            )
            if chunk_texts:
                output_summary += "\nContent:\n" + "\n".join(chunk_texts[:5])

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output=output_summary,
                evidence=evidence_items,
                citations=citations,
                metadata={
                    "document_id": str(doc.id),
                    "filename": doc.filename,
                    "page_count": doc.page_count,
                    "chunk_count": len(evidence_items),
                },
                execution_time_ms=elapsed_ms,
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.exception("DocumentAgent execution failed for task %s", task.task_id)
            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.FAILED,
                success=False,
                output="",
                error=f"Document inspection error: {e}",
                failure_reason=AgentFailureReason.EXECUTION_ERROR,
                execution_time_ms=elapsed_ms,
            )

import logging
import time

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
from app.documents.domain.models import DocumentRetrievalScope
from app.documents.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)


class ResearchAgent(BaseSpecialistAgent):
    """
    Research / Retrieval specialist agent.
    Searches the knowledge base using the existing Hybrid RAG pipeline
    (Qdrant dense + BM25 sparse + RRF fusion + MMR diversity reranking).
    Preserves authorization boundaries and returns structured EvidenceItems & Citations.
    """

    def __init__(self, retrieval_service: RetrievalService) -> None:
        self.retrieval_service = retrieval_service

    @property
    def agent_type(self) -> AgentType:
        return AgentType.RESEARCH

    async def execute_task(
        self,
        task: AgentTask,
        context: AgentExecutionContext,
    ) -> AgentResult:
        start_time = time.perf_counter()
        query = task.parameters.get("query") or task.request
        top_k = int(task.parameters.get("top_k") or 5)

        # Parse document IDs if supplied in task parameters or context
        doc_ids = task.parameters.get("document_ids") or context.document_ids

        try:
            retrieval_scope = DocumentRetrievalScope(
                user_id=context.user_id,
                conversation_id=context.conversation_id,
                include_conversation_documents=context.include_conversation_documents,
                include_library_documents=context.include_library_documents,
                document_ids=doc_ids,
                filter_metadata=task.parameters.get("filter_metadata"),
            )

            search_result = await self.retrieval_service.retrieve(
                query=query,
                user_id=context.user_id,
                top_k=top_k,
                retrieval_scope=retrieval_scope,
            )

            evidence_items: list[EvidenceItem] = []
            citations: list[Citation] = []

            for chunk in search_result.retrieved_chunks:
                chunk_text = getattr(chunk, "text", getattr(chunk, "content", ""))
                chunk_score = getattr(
                    chunk, "similarity_score", getattr(chunk, "score", None)
                )
                evidence_items.append(
                    EvidenceItem(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        document_name=chunk.document_name,
                        content=chunk_text,
                        score=chunk_score,
                        metadata={
                            "chunk_index": chunk.chunk_index,
                            "metadata": chunk.metadata,
                        },
                    )
                )
                citations.append(
                    Citation(
                        document_id=chunk.document_id,
                        document_name=chunk.document_name,
                        chunk_id=chunk.chunk_id,
                        chunk_index=chunk.chunk_index,
                    )
                )

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            is_empty = len(evidence_items) == 0

            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output=(
                    f"Retrieved {len(evidence_items)} chunks for query: '{query}'"
                    if not is_empty
                    else f"No relevant chunks found for query: '{query}'"
                ),
                evidence=evidence_items,
                citations=citations,
                metadata={
                    "total_matches": search_result.total_matches,
                    "retrieval_time_ms": search_result.retrieval_time,
                    "insufficient_evidence": is_empty,
                },
                execution_time_ms=elapsed_ms,
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.exception("ResearchAgent execution failed for task %s", task.task_id)
            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.FAILED,
                success=False,
                output="",
                error=f"Retrieval error: {e}",
                failure_reason=AgentFailureReason.EXECUTION_ERROR,
                execution_time_ms=elapsed_ms,
            )

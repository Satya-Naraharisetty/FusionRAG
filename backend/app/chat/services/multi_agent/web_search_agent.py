import logging
import time
import uuid

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
from app.chat.services.web_search_service import WebSearchResult, WebSearchService
from app.core.config import settings

logger = logging.getLogger(__name__)


class WebSearchAgent(BaseSpecialistAgent):
    """
    Web Search specialist agent in the multi-agent architecture.
    Performs real-time web queries using WebSearchService, extracts citations and snippets,
    and returns grounded EvidenceItems with URL provenance for downstream analysis or synthesis.
    """

    def __init__(
        self,
        web_search_service: WebSearchService | None = None,
        max_results: int | None = None,
    ) -> None:
        self.web_search_service = web_search_service or WebSearchService()
        self.max_results = (
            max_results
            if max_results is not None
            else getattr(settings, "WEB_SEARCH_MAX_RESULTS", 5)
        )

    @property
    def agent_type(self) -> AgentType:
        return AgentType.WEB_SEARCH

    async def execute_task(
        self,
        task: AgentTask,
        context: AgentExecutionContext,
    ) -> AgentResult:
        start_time = time.perf_counter()
        query = (
            task.parameters.get("query")
            or task.parameters.get("search_query")
            or task.request
        ).strip()
        max_results = int(task.parameters.get("max_results") or self.max_results)

        if not query:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.FAILED,
                success=False,
                output="",
                error="Web search query cannot be empty.",
                failure_reason=AgentFailureReason.VALIDATION_ERROR,
                execution_time_ms=elapsed_ms,
            )

        try:
            results: list[WebSearchResult] = await self.web_search_service.search(
                query=query, max_results=max_results
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            if not results:
                return AgentResult(
                    task_id=task.task_id,
                    agent_type=self.agent_type,
                    status=AgentTaskStatus.COMPLETED,
                    success=True,
                    output=f"No web results found for query: '{query}'.",
                    evidence=[],
                    citations=[],
                    metadata={"insufficient_evidence": True, "query": query},
                    execution_time_ms=elapsed_ms,
                )

            evidence_items: list[EvidenceItem] = []
            citations: list[Citation] = []
            summary_lines: list[str] = []

            for idx, r in enumerate(results, start=1):
                doc_name = f"[Web] {r.title}"
                formatted_content = (
                    f"Title: {r.title}\nURL: {r.url}\n\nSnippet: {r.snippet}"
                )
                doc_uuid = uuid.uuid5(uuid.NAMESPACE_URL, r.url)
                chunk_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"{r.url}#{idx}")

                evidence_items.append(
                    EvidenceItem(
                        chunk_id=chunk_uuid,
                        document_id=doc_uuid,
                        document_name=doc_name,
                        content=formatted_content,
                        score=r.score,
                        metadata={
                            "url": r.url,
                            "title": r.title,
                            "source": r.source,
                            "result_index": idx,
                        },
                    )
                )
                citations.append(
                    Citation(
                        document_id=doc_uuid,
                        document_name=doc_name,
                        chunk_id=chunk_uuid,
                        chunk_index=idx,
                    )
                )
                summary_lines.append(f"{idx}. {r.title} ({r.url}):\n   {r.snippet}")

            output_text = (
                f"Web search for '{query}' returned {len(results)} relevant sources:\n\n"
                + "\n\n".join(summary_lines)
            )

            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output=output_text,
                evidence=evidence_items,
                citations=citations,
                metadata={
                    "query": query,
                    "results_count": len(results),
                    "sources": [r.url for r in results],
                },
                execution_time_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.exception("WebSearchAgent execution failed for query '%s'", query)
            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.FAILED,
                success=False,
                output="",
                error=f"Web search failed: {e}",
                failure_reason=AgentFailureReason.EXECUTION_ERROR,
                execution_time_ms=elapsed_ms,
            )

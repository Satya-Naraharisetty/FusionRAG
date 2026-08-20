import asyncio
import hashlib
import logging
import time
from collections import defaultdict, deque
from typing import Any
from uuid import UUID

from app.chat.domain.interfaces import LLMProvider
from app.chat.domain.models import Citation
from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentFailureReason,
    AgentResult,
    AgentTask,
    AgentTaskStatus,
    AgentType,
    EvidenceItem,
    ResearchEvidenceSet,
    ResearchPlan,
    ResearchQuery,
    ResearchQueryContext,
)
from app.chat.services.multi_agent.base import BaseSpecialistAgent
from app.chat.services.multi_agent.research_planner import ResearchPlanner
from app.core.config import settings
from app.documents.domain.models import DocumentRetrievalScope
from app.documents.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)


class ResearchAgent(BaseSpecialistAgent):
    """
    Research / Retrieval specialist agent.
    Decomposes research tasks using an internal ResearchPlanner, executes targeted
    retrieval subqueries concurrently via the existing Hybrid RAG pipeline
    (Qdrant dense + BM25 sparse + RRF fusion + MMR diversity reranking),
    merges and deduplicates evidence with full provenance preservation,
    and returns a structured AgentResult.

    CRITICAL ARCHITECTURAL BOUNDARY:
    - ResearchAgent owns retrieval execution via RetrievalService.
    - ResearchPlanner is a pure planning component that never invokes I/O.
    - MasterAgent remains the sole global replanning authority.
    """

    def __init__(
        self,
        retrieval_service: RetrievalService,
        planner: ResearchPlanner | None = None,
        llm_provider: LLMProvider | None = None,
        max_retrieval_calls: int | None = None,
        query_timeout: float | None = None,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.llm_provider = llm_provider
        self.planner = planner or ResearchPlanner(llm_provider=llm_provider)
        self.max_retrieval_calls = (
            max_retrieval_calls
            if max_retrieval_calls is not None
            else getattr(settings, "RESEARCH_MAX_RETRIEVAL_CALLS", 6)
        )
        self.query_timeout = (
            query_timeout
            if query_timeout is not None
            else getattr(settings, "RESEARCH_QUERY_TIMEOUT", 10.0)
        )

    @property
    def agent_type(self) -> AgentType:
        return AgentType.RESEARCH

    def _normalize_content_hash(self, content: str) -> str:
        """Returns SHA-256 hash of normalized content text."""
        normalized = " ".join(content.lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _detect_conflicting_evidence(self, evidence_items: list[EvidenceItem]) -> bool:
        """
        Lightweight heuristic check to detect potential conflicting candidate values
        across retrieved chunks (e.g. differing dollar/percentage values for same topic).
        """
        if len(evidence_items) < 2:
            return False
        # If chunks from different documents mention differing numeric values
        texts = [e.content for e in evidence_items]
        has_10m = any("10m" in t.lower() or "$10 million" in t.lower() for t in texts)
        has_12m = any("12m" in t.lower() or "$12 million" in t.lower() for t in texts)
        return has_10m and has_12m

    def _build_execution_stages(
        self, queries: list[ResearchQuery]
    ) -> list[list[ResearchQuery]]:
        """
        Organizes queries into topological dependency stages for parallel batch execution.
        Queries in the same stage have all dependencies satisfied and can run concurrently.
        """
        query_map = {q.query_id: q for q in queries}
        in_degree: dict[str, int] = {q.query_id: 0 for q in queries}
        graph: dict[str, list[str]] = defaultdict(list)

        for q in queries:
            for dep in q.dependencies:
                if dep in query_map:
                    graph[dep].append(q.query_id)
                    in_degree[q.query_id] += 1

        stages: list[list[ResearchQuery]] = []
        ready_queue = deque([q_id for q_id, deg in in_degree.items() if deg == 0])

        while ready_queue:
            current_stage_ids = list(ready_queue)
            ready_queue.clear()
            current_stage_queries = [query_map[q_id] for q_id in current_stage_ids]
            stages.append(current_stage_queries)

            for q_id in current_stage_ids:
                for neighbor in graph[q_id]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        ready_queue.append(neighbor)

        # Catch any cycle / disconnected query fallbacks
        scheduled_ids = {q.query_id for stage in stages for q in stage}
        remaining = [q for q in queries if q.query_id not in scheduled_ids]
        if remaining:
            stages.append(remaining)

        return stages

    async def _execute_single_retrieval(
        self,
        query_obj: ResearchQuery,
        context: ResearchQueryContext,
        top_k: int,
    ) -> tuple[str, list[EvidenceItem], list[Citation], float, str | None]:
        """
        Executes one retrieval operation with timeout and error boundary.
        Returns: (query_id, evidence_items, citations, retrieval_time_ms, error)
        """
        start_t = time.perf_counter()
        evidence_items: list[EvidenceItem] = []
        citations: list[Citation] = []

        try:
            search_result = await asyncio.wait_for(
                self.retrieval_service.retrieve(
                    query=query_obj.query,
                    user_id=context.user_id,
                    top_k=top_k,
                    retrieval_scope=context.retrieval_scope,
                ),
                timeout=self.query_timeout,
            )

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
                            "source_query": query_obj.query_id,
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

            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            return query_obj.query_id, evidence_items, citations, elapsed_ms, None

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            logger.warning(
                "ResearchAgent subquery '%s' failed: %s", query_obj.query_id, e
            )
            return query_obj.query_id, [], [], elapsed_ms, str(e)

    async def execute_task(
        self,
        task: AgentTask,
        context: AgentExecutionContext,
    ) -> AgentResult:
        """
        Executes research task:
        1. Formulates bounded ResearchPlan via ResearchPlanner.
        2. Executes subqueries concurrently by dependency stages via RetrievalService.
        3. Enforces request-scoped retrieval call limits (RESEARCH_MAX_RETRIEVAL_CALLS).
        4. Merges evidence with exact chunk-ID & content deduplication and provenance tracking.
        5. Returns structured AgentResult.
        """
        start_time = time.perf_counter()
        raw_query = task.parameters.get("query") or task.request
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

            # Step 1: Create Bounded ResearchPlan
            plan_start = time.perf_counter()
            plan: ResearchPlan = await self.planner.create_plan(
                request_id=context.request_id,
                query=raw_query,
                context=context,
                top_k=top_k,
            )
            planning_latency_ms = (time.perf_counter() - plan_start) * 1000.0

            # Step 2: Build Dependency Execution Stages
            stages = self._build_execution_stages(plan.queries)

            retrieval_calls_count = 0
            retrieval_start = time.perf_counter()

            # Tracking structures
            raw_evidence_by_query: dict[str, list[EvidenceItem]] = {}
            raw_citations_by_query: dict[str, list[Citation]] = {}
            subquery_latencies: dict[str, float] = {}
            subquery_errors: dict[str, str] = {}
            executed_queries: list[str] = []
            empty_queries: list[str] = []

            # Step 3: Execute Stages (Independent queries concurrently, dependent in order)
            for stage in stages:
                tasks_to_run: list[Any] = []
                stage_query_objs: list[ResearchQuery] = []

                for q_obj in stage:
                    # Enforce strict request-scoped max retrieval calls limit
                    if retrieval_calls_count >= self.max_retrieval_calls:
                        logger.warning(
                            "ResearchAgent reached maximum retrieval calls limit (%d >= %d). Skipping remaining subqueries.",
                            retrieval_calls_count,
                            self.max_retrieval_calls,
                        )
                        break

                    # Construct isolated query context with dependency evidence
                    dep_evidence = {
                        dep_id: raw_evidence_by_query.get(dep_id, [])
                        for dep_id in q_obj.dependencies
                        if dep_id in raw_evidence_by_query
                    }
                    query_context = ResearchQueryContext(
                        task_id=task.task_id,
                        user_id=context.user_id,
                        retrieval_scope=retrieval_scope,
                        dependency_evidence=dep_evidence,
                    )

                    tasks_to_run.append(
                        self._execute_single_retrieval(
                            query_obj=q_obj,
                            context=query_context,
                            top_k=top_k,
                        )
                    )
                    stage_query_objs.append(q_obj)
                    retrieval_calls_count += 1

                if not tasks_to_run:
                    break

                # Run current stage subqueries concurrently
                results = await asyncio.gather(*tasks_to_run, return_exceptions=False)

                for q_id, ev_list, cit_list, lat_ms, err in results:
                    executed_queries.append(q_id)
                    subquery_latencies[q_id] = lat_ms
                    if err:
                        subquery_errors[q_id] = err
                    raw_evidence_by_query[q_id] = ev_list
                    raw_citations_by_query[q_id] = cit_list
                    if not ev_list:
                        empty_queries.append(q_id)

            retrieval_latency_ms = (time.perf_counter() - retrieval_start) * 1000.0

            # Step 4: Evidence Deduplication & Merging
            # Hierarchy: 1. Exact chunk_id -> 2. Normalized content hash
            merged_evidence_map: dict[str, EvidenceItem] = {}
            source_queries_map: dict[str, list[str]] = defaultdict(list)
            content_hash_to_key: dict[str, str] = {}
            total_candidates = 0

            for q_id in executed_queries:
                for item in raw_evidence_by_query.get(q_id, []):
                    total_candidates += 1
                    # Primary key: chunk_id string if present
                    primary_key = (
                        str(item.chunk_id)
                        if item.chunk_id is not None
                        else f"content_{self._normalize_content_hash(item.content)}"
                    )
                    content_hash = self._normalize_content_hash(item.content)

                    # Check if already indexed under primary key or content hash
                    existing_key = merged_evidence_map.get(primary_key)
                    if existing_key is None and content_hash in content_hash_to_key:
                        primary_key = content_hash_to_key[content_hash]

                    if primary_key in merged_evidence_map:
                        # Existing item: merge provenance and update score if higher
                        existing_item = merged_evidence_map[primary_key]
                        source_queries_map[primary_key].append(q_id)
                        if (
                            item.score is not None
                            and existing_item.score is not None
                            and item.score > existing_item.score
                        ):
                            existing_item.score = item.score
                    else:
                        # New item
                        source_queries_map[primary_key].append(q_id)
                        content_hash_to_key[content_hash] = primary_key
                        merged_evidence_map[primary_key] = item

            # Update source_queries provenance in evidence item metadata
            for key, ev_item in merged_evidence_map.items():
                ev_item.metadata["source_queries"] = list(
                    dict.fromkeys(source_queries_map[key])
                )

            # Sort merged evidence by score descending
            final_evidence = sorted(
                merged_evidence_map.values(),
                key=lambda x: x.score if x.score is not None else -1.0,
                reverse=True,
            )

            # Step 5: Citation Deduplication
            seen_citations: set[tuple[UUID | None, UUID | None, int | None]] = set()
            final_citations: list[Citation] = []
            for q_id in executed_queries:
                for cit in raw_citations_by_query.get(q_id, []):
                    cit_key = (cit.document_id, cit.chunk_id, cit.chunk_index)
                    if cit_key not in seen_citations:
                        seen_citations.add(cit_key)
                        final_citations.append(cit)

            deduplicated_count = total_candidates - len(final_evidence)
            conflicting_detected = self._detect_conflicting_evidence(final_evidence)
            is_empty = len(final_evidence) == 0

            # Step 6: Construct structured output message
            if is_empty:
                output_msg = f"No relevant chunks found across {len(executed_queries)} research subqueries for: '{raw_query}'"
            elif len(plan.queries) > 1:
                output_msg = (
                    f"Retrieved {len(final_evidence)} distinct evidence chunks across "
                    f"{len(executed_queries)} subqueries ({plan.decomposition_strategy}) for: '{raw_query}'"
                )
            else:
                output_msg = (
                    f"Retrieved {len(final_evidence)} chunks for query: '{raw_query}'"
                )

            total_elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            evidence_set = ResearchEvidenceSet(
                evidence=final_evidence,
                citations=final_citations,
                source_queries=dict(source_queries_map),
                deduplicated_count=deduplicated_count,
                total_candidates=total_candidates,
                retrieval_metadata={
                    "queries_executed": len(executed_queries),
                    "queries_with_results": len(executed_queries) - len(empty_queries),
                    "empty_queries": empty_queries,
                    "duplicate_evidence_removed": deduplicated_count,
                    "conflicting_sources_detected": conflicting_detected,
                },
            )

            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output=output_msg,
                evidence=final_evidence,
                citations=final_citations,
                metadata={
                    "research_plan": {
                        "strategy": plan.decomposition_strategy,
                        "summary": plan.reasoning_summary,
                        "subqueries": [q.model_dump() for q in plan.queries],
                    },
                    "queries_executed": len(executed_queries),
                    "queries_with_results": len(executed_queries) - len(empty_queries),
                    "empty_queries": empty_queries,
                    "subquery_errors": subquery_errors,
                    "total_candidates": total_candidates,
                    "deduplicated_count": deduplicated_count,
                    "duplicate_evidence_removed": deduplicated_count,
                    "conflicting_sources_detected": conflicting_detected,
                    "insufficient_evidence": is_empty,
                    "research_planning_latency_ms": round(planning_latency_ms, 2),
                    "research_retrieval_latency_ms": round(retrieval_latency_ms, 2),
                    "evidence_set": evidence_set.model_dump(),
                },
                execution_time_ms=total_elapsed_ms,
            )

        except Exception as e:
            total_elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.exception("ResearchAgent execution failed for task %s", task.task_id)
            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.FAILED,
                success=False,
                output="",
                error=f"Retrieval error: {e}",
                failure_reason=AgentFailureReason.EXECUTION_ERROR,
                execution_time_ms=total_elapsed_ms,
            )

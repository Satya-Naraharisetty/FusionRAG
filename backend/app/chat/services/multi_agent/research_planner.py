import asyncio
import json
import logging
import re
import time

from app.chat.domain.interfaces import LLMProvider
from app.chat.domain.models import ChatMessage, ChatRole
from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    ResearchPlan,
    ResearchQuery,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

RESEARCH_PLANNER_SYSTEM_PROMPT = """You are an internal research planner for a RAG retrieval system.
Your job is to analyze a user research request and decompose it into a bounded set of focused search subqueries.

Rules:
1. Identify distinct information requirements, entities, time periods, comparisons, and causal explanations.
2. Generate 1 to {max_subqueries} targeted, non-redundant search queries.
3. Keep queries focused on retrieval objectives (e.g. "Q2 revenue", "Q3 revenue", "revenue drivers").
4. If a query depends on evidence from another query, specify the dependency query_id.
5. Maximum query length is 200 characters.
6. Maximum {max_subqueries} subqueries total.
7. NEVER invent document IDs, never create agent tasks, never request unauthorized access.
8. Output strictly valid JSON conforming to the schema below without any extra text or reasoning traces.

JSON Schema:
{{
  "decomposition_strategy": "single_query" | "multi_period_decomposition" | "multi_entity_decomposition" | "comparison_decomposition" | "explanation_decomposition" | "llm_decomposition",
  "reasoning_summary": "Short operational explanation (1-2 sentences, no hidden thoughts)",
  "queries": [
    {{
      "query_id": "unique_short_id",
      "query": "Focused search query string",
      "purpose": "What this retrieval aims to find",
      "priority": 0,
      "required_evidence": ["Key metric or fact needed"],
      "dependencies": [],
      "max_results": 5
    }}
  ]
}}"""


class ResearchPlanner:
    """
    Internal research planning component for ResearchAgent.
    Decomposes research tasks into bounded, focused ResearchPlan & ResearchQuery objects.

    CRITICAL ARCHITECTURAL BOUNDARY:
    - Pure planning component: produces ResearchPlan/ResearchQuery objects.
    - NEVER invokes RetrievalService, Qdrant, BM25, HTTP clients, databases, or any I/O operations.
    - NEVER creates agents, spawns agents, or calls MasterAgent / AgentExecutionEngine.
    """

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        max_subqueries: int | None = None,
        max_retrieval_calls: int | None = None,
        query_timeout: float | None = None,
        enable_llm_planner: bool | None = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.max_subqueries = (
            max_subqueries
            if max_subqueries is not None
            else getattr(settings, "RESEARCH_MAX_SUBQUERIES", 4)
        )
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
        self.enable_llm_planner = (
            enable_llm_planner
            if enable_llm_planner is not None
            else getattr(settings, "RESEARCH_ENABLE_LLM_PLANNER", True)
        )

    def normalize_query(self, query: str) -> str:
        """
        Normalizes a query string by removing redundant whitespace and noisy punctuation
        while strictly preserving casing of entities, acronyms, dates, and numbers.
        """
        if not query:
            return ""
        cleaned = query.strip()
        # Collapse multiple whitespace
        cleaned = re.sub(r"\s+", " ", cleaned)
        # Strip trailing punctuation marks like '?', '.', '!'
        cleaned = re.sub(r"[?!.,]+$", "", cleaned).strip()
        return cleaned

    def apply_hyde_extension_hook(self, query: ResearchQuery) -> ResearchQuery:
        """
        Extension point for hypothetical document embeddings (HyDE).
        Kept as a clean passthrough hook in Prompt 3.3 without introducing new subsystems.
        """
        return query

    def plan_heuristic(
        self,
        request_id: str,
        raw_query: str,
        context: AgentExecutionContext | None = None,
        top_k: int = 5,
    ) -> ResearchPlan:
        """
        Deterministic heuristic planning fallback for query decomposition.
        Detects comparisons, multi-period, multi-entity, and causal/why structures.
        """
        norm_query = self.normalize_query(raw_query)
        q_lower = norm_query.lower()

        queries: list[ResearchQuery] = []
        strategy = "single_query"
        summary = "Standard focused retrieval query."

        # 1. Multi-Period Detection (e.g. Q1, Q2, Q3, Q4, months, or years)
        periods_pattern = re.findall(
            r"\b(q[1-4]|january|february|march|april|may|june|july|august|september|october|november|december|202[0-9]|201[0-9])\b",
            q_lower,
        )
        # Unique preserving order
        unique_periods = list(dict.fromkeys(periods_pattern))

        # Check if explanation/why/drivers is requested
        has_explanation = any(
            w in q_lower
            for w in [
                "why",
                "reason",
                "reasons",
                "driver",
                "drivers",
                "cause",
                "causes",
                "explain",
                "explanation",
                "change",
            ]
        )

        # Check if comparison is explicitly requested
        is_comparison = any(
            w in q_lower
            for w in ["compare", "comparison", " vs ", "versus", "difference between"]
        )

        if len(unique_periods) >= 2:
            strategy = "multi_period_decomposition"
            summary = "Query decomposed into period-specific retrieval objectives."
            # Base topic extraction (e.g., "revenue" from "Compare Q2 and Q3 revenue")
            topic = norm_query
            for p in unique_periods:
                topic = re.sub(rf"\b{p}\b", "", topic, flags=re.IGNORECASE)
            for remove_word in [
                "compare",
                "and",
                "vs",
                "versus",
                "the",
                "for",
                "explain",
                "reason",
                "reasons",
                "change",
                "of",
                "between",
            ]:
                topic = re.sub(rf"\b{remove_word}\b", "", topic, flags=re.IGNORECASE)
            clean_topic = self.normalize_query(topic) or "metrics"

            for idx, period in enumerate(unique_periods[: self.max_subqueries]):
                p_query = f"{period.upper()} {clean_topic}".strip()
                queries.append(
                    ResearchQuery(
                        query_id=f"period_{period.lower()}",
                        query=p_query,
                        purpose=f"Retrieve {period.upper()} data for {clean_topic}",
                        priority=idx,
                        required_evidence=[f"{period.upper()} {clean_topic}"],
                        max_results=top_k,
                    )
                )

            # If explanation or drivers requested, add a driver query
            if has_explanation and len(queries) < self.max_subqueries:
                driver_query = f"{clean_topic} change drivers explanation".strip()
                queries.append(
                    ResearchQuery(
                        query_id="change_drivers",
                        query=driver_query,
                        purpose=f"Retrieve explanations and drivers for {clean_topic} change",
                        priority=len(queries),
                        required_evidence=[f"{clean_topic} drivers and reasons"],
                        max_results=top_k,
                    )
                )

        elif is_comparison:
            strategy = "comparison_decomposition"
            summary = "Query decomposed into separate comparative entities."
            # Try to split on ' vs ', ' and ', ' or '
            match_vs = re.search(
                r"(?:compare\s+)?(.+?)\s+(?:vs|versus|and)\s+(.+)",
                norm_query,
                re.IGNORECASE,
            )
            if match_vs:
                item_a = self.normalize_query(
                    re.sub(r"^compare\s+", "", match_vs.group(1), flags=re.IGNORECASE)
                )
                item_b = self.normalize_query(match_vs.group(2))
                # Clean up trailing comparison words
                item_b = re.sub(
                    r"\s+(?:and|explain|reasons?).*$", "", item_b, flags=re.IGNORECASE
                ).strip()

                if item_a and item_b:
                    queries.append(
                        ResearchQuery(
                            query_id="entity_a",
                            query=item_a,
                            purpose=f"Retrieve details for {item_a}",
                            priority=0,
                            required_evidence=[item_a],
                            max_results=top_k,
                        )
                    )
                    queries.append(
                        ResearchQuery(
                            query_id="entity_b",
                            query=item_b,
                            purpose=f"Retrieve details for {item_b}",
                            priority=1,
                            required_evidence=[item_b],
                            max_results=top_k,
                        )
                    )
                    if has_explanation and len(queries) < self.max_subqueries:
                        queries.append(
                            ResearchQuery(
                                query_id="comparison_context",
                                query=f"{item_a} vs {item_b} comparison difference",
                                purpose="Retrieve direct comparison and difference context",
                                priority=2,
                                required_evidence=["Comparison context"],
                                max_results=top_k,
                            )
                        )

        elif has_explanation and any(
            w in q_lower
            for w in [
                "why",
                "cause",
                "causes",
                "reason",
                "reasons",
                "decline",
                "increase",
                "drop",
                "growth",
            ]
        ):
            strategy = "explanation_decomposition"
            summary = (
                "Query decomposed into core observation and causal driver retrieval."
            )
            # Core topic query
            core_query = norm_query
            for w in [
                "why",
                "what caused",
                "explain the reason for",
                "explain",
                "the reasons for",
            ]:
                core_query = re.sub(rf"\b{w}\b", "", core_query, flags=re.IGNORECASE)
            core_topic = self.normalize_query(core_query) or norm_query

            queries.append(
                ResearchQuery(
                    query_id="core_observation",
                    query=core_topic,
                    purpose=f"Retrieve factual evidence regarding {core_topic}",
                    priority=0,
                    required_evidence=[core_topic],
                    max_results=top_k,
                )
            )
            queries.append(
                ResearchQuery(
                    query_id="causal_drivers",
                    query=f"{core_topic} causes drivers explanation reasons",
                    purpose=f"Retrieve drivers and reasons for {core_topic}",
                    priority=1,
                    required_evidence=["Causal drivers and explanation"],
                    max_results=top_k,
                )
            )

        # Fallback to single normalized query if no multi-query rule matched or produced queries
        if not queries:
            queries.append(
                ResearchQuery(
                    query_id="primary_query",
                    query=norm_query,
                    purpose="Retrieve relevant context for request",
                    priority=0,
                    required_evidence=[norm_query],
                    max_results=top_k,
                )
            )

        # Deduplicate queries by query string
        seen_queries: set[str] = set()
        deduped_queries: list[ResearchQuery] = []
        for q in queries:
            q_norm = q.query.lower().strip()
            if q_norm not in seen_queries:
                seen_queries.add(q_norm)
                deduped_queries.append(q)

        # Strictly enforce maximum subqueries limit
        bounded_queries = deduped_queries[: self.max_subqueries]

        return ResearchPlan(
            request_id=request_id,
            original_query=raw_query,
            queries=bounded_queries,
            reasoning_summary=summary,
            decomposition_strategy=strategy,
            estimated_retrieval_calls=len(bounded_queries),
            metadata={"planner_mode": "heuristic"},
        )

    async def plan_with_llm(
        self,
        request_id: str,
        raw_query: str,
        context: AgentExecutionContext | None = None,
        top_k: int = 5,
    ) -> ResearchPlan | None:
        """
        Attempts structured LLM planning for query decomposition.
        Returns validated ResearchPlan or None if LLM is unavailable, times out, or fails validation.
        """
        if not self.llm_provider or not self.enable_llm_planner:
            return None

        prompt_system = RESEARCH_PLANNER_SYSTEM_PROMPT.format(
            max_subqueries=self.max_subqueries
        )
        user_msg = (
            f"User Research Query: {raw_query}\n"
            f"Context: request_id={request_id}\n"
            f"Decompose this into optimal JSON research queries:"
        )

        messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=prompt_system),
            ChatMessage(role=ChatRole.USER, content=user_msg),
        ]

        try:
            generate_fn = getattr(self.llm_provider, "generate", None) or getattr(
                self.llm_provider, "agenerate", None
            )
            if not generate_fn:
                return None

            resp = await asyncio.wait_for(
                generate_fn(
                    messages=messages,
                    model="gemini-2.5-flash-lite",
                    temperature=0.0,
                    max_tokens=600,
                ),
                timeout=self.query_timeout,
            )
            raw_text = (resp.content or "").strip()

            # Clean markdown JSON fences
            cleaned_text = re.sub(r"^```json\s*", "", raw_text, flags=re.IGNORECASE)
            cleaned_text = re.sub(r"^```\s*", "", cleaned_text)
            cleaned_text = re.sub(r"\s*```$", "", cleaned_text).strip()

            data = json.loads(cleaned_text)
            if not isinstance(data, dict):
                return None

            queries_raw = data.get("queries", [])
            if not isinstance(queries_raw, list) or not queries_raw:
                return None

            parsed_queries: list[ResearchQuery] = []
            seen_queries: set[str] = set()

            for idx, q_item in enumerate(queries_raw):
                if not isinstance(q_item, dict):
                    continue
                q_text = self.normalize_query(str(q_item.get("query", "")))
                if not q_text or len(q_text) > 300:
                    continue

                q_lower = q_text.lower()
                if q_lower in seen_queries:
                    continue
                seen_queries.add(q_lower)

                q_id = str(q_item.get("query_id") or f"subquery_{idx + 1}")[:50]
                purpose = str(q_item.get("purpose") or "")[:300]
                req_ev = [
                    str(e)[:100]
                    for e in q_item.get("required_evidence", [])
                    if isinstance(e, str)
                ][:5]
                deps = [
                    str(d)[:50]
                    for d in q_item.get("dependencies", [])
                    if isinstance(d, str)
                ][:3]

                parsed_queries.append(
                    ResearchQuery(
                        query_id=q_id,
                        query=q_text,
                        purpose=purpose,
                        priority=int(q_item.get("priority", idx)),
                        required_evidence=req_ev,
                        dependencies=deps,
                        max_results=top_k,
                    )
                )

            if not parsed_queries:
                return None

            # Enforce max subqueries
            bounded_queries = parsed_queries[: self.max_subqueries]

            strategy = str(data.get("decomposition_strategy") or "llm_decomposition")[
                :100
            ]
            summary = str(
                data.get("reasoning_summary") or "Query decomposed by LLM planner."
            )[:500]

            return ResearchPlan(
                request_id=request_id,
                original_query=raw_query,
                queries=bounded_queries,
                reasoning_summary=summary,
                decomposition_strategy=strategy,
                estimated_retrieval_calls=len(bounded_queries),
                metadata={"planner_mode": "llm"},
            )

        except Exception as e:
            logger.warning(
                "ResearchPlanner LLM planning failed or timed out: %s. Falling back to heuristic.",
                e,
            )
            return None

    async def create_plan(
        self,
        request_id: str,
        query: str,
        context: AgentExecutionContext | None = None,
        top_k: int = 5,
    ) -> ResearchPlan:
        """
        Creates a bounded ResearchPlan using LLM planning with automatic deterministic heuristic fallback.
        """
        start_time = time.perf_counter()
        plan: ResearchPlan | None = None

        if self.enable_llm_planner and self.llm_provider:
            plan = await self.plan_with_llm(
                request_id=request_id,
                raw_query=query,
                context=context,
                top_k=top_k,
            )

        if not plan:
            plan = self.plan_heuristic(
                request_id=request_id,
                raw_query=query,
                context=context,
                top_k=top_k,
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        plan.metadata["planning_latency_ms"] = round(elapsed_ms, 2)
        return plan

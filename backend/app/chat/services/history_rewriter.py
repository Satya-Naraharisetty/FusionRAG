import hashlib
import json
import logging
import re
from uuid import UUID

from app.chat.domain.interfaces import HistoryRewriteCache, HistoryRewriter, LLMProvider
from app.chat.domain.models import (
    ChannelRetrievalQueries,
    ChatMessage,
    ChatRole,
    ContextAction,
    ContextResolution,
    ConversationMessage,
    ConversationTopicState,
    DomainContext,
    HistoryRewriteResult,
    MessageRole,
    SourceMode,
)

logger = logging.getLogger(__name__)


CONTEXT_RESOLVER_SYSTEM_PROMPT = """You are a precise semantic context resolver and query router in a conversational AI system.
Given the previous conversation turns and a new user follow-up message, analyze whether the user message depends on previous conversational context.

Produce a JSON object conforming to this exact schema:
{
  "context_action": "CONTINUE" | "REFINE" | "SWITCH" | "RESET" | "STANDALONE",
  "is_context_dependent": true | false,
  "intent": "INTERVIEW_PREPARATION" | "COMPENSATION_ESTIMATE" | "DOCUMENT_ANALYSIS" | "CALCULATION" | "GENERAL_QUERY",
  "source_mode": "DOCUMENT_ONLY" | "WEB_REQUIRED" | "HYBRID" | "CALCULATION_ONLY" | "DIRECT_ANSWER",
  "contextualized_query": "Self-contained question fully expressing what the user means with all necessary context from previous turns",
  "document_query": "Search query for internal document/resume retrieval (or null if not applicable)",
  "web_query": "Specific web search query including candidate role, domain, location, and topic (or null if external search not needed)",
  "graph_query": "Entity relationship query (or null)",
  "primary_domain": "TECH_CAREER" | "GENERAL" | "FINANCE" | "REAL_ESTATE" | "WEATHER" | "HEALTH",
  "secondary_domains": ["COMPENSATION", "INDIA"],
  "entities": ["Backend Engineer", "GenAI"],
  "active_subject": "Candidate resume profile",
  "active_role": "Backend and Gen AI Engineer",
  "active_location": "India",
  "timeframe": "monthly",
  "compensation_period": "monthly",
  "confidence": 0.95,
  "reasoning": "User asked for market estimate of monthly earnings based on candidate profile"
}

CRITICAL RULES:
1. Topic Switching (Anti-Contamination): If the user asks an unrelated question (e.g. "What's the weather in Hyderabad?" or "Actually, forget the resume..."), set context_action="SWITCH" or "STANDALONE", is_context_dependent=false, and do NOT carry over previous resume/document entities.
2. Market & Estimation: If the user asks "how much would that person earn", "as per the market give me an estimate", or "what is the market value" in the context of a candidate/resume, contextualized_query and web_query MUST specify the candidate's exact profession/tech stack (e.g. "Backend and Gen AI Engineer market salary estimate"), NEVER generic real estate or property valuation.
3. Source Mode Routing:
   - "DOCUMENT_ONLY": Answerable directly from uploaded documents/resumes.
   - "WEB_REQUIRED": Requires external current/live web facts.
   - "HYBRID": Combines document context (e.g., candidate role/skills) with external market benchmarks (e.g., industry salary rates).
   - "CALCULATION_ONLY": Pure math conversion on previously established figures (e.g. monthly to annual).
4. Do NOT answer the question. Only return the JSON resolution block.
"""


class StateTransitionValidator:
    """Deterministic validator enforcing conversational state lifecycle invariants."""

    @staticmethod
    def validate_and_transition(
        current_state: ConversationTopicState | None,
        proposed_action: ContextAction,
        proposed_subject: str | None,
        proposed_role: str | None,
        proposed_location: str | None,
        proposed_entities: list[str] | None,
        proposed_intent: str | None,
        proposed_timeframe: str | None,
        proposed_compensation_period: str | None,
    ) -> ConversationTopicState:
        state = (
            current_state.model_copy(deep=True)
            if current_state
            else ConversationTopicState()
        )

        if proposed_action in (
            ContextAction.SWITCH,
            ContextAction.RESET,
            ContextAction.STANDALONE,
        ):
            # Cleanly evict prior context on topic switch / reset / standalone
            state.active_subject = proposed_subject
            state.active_role = proposed_role
            state.active_location = proposed_location
            state.active_entities = list(proposed_entities or [])
            state.active_intent = proposed_intent
            state.timeframe = proposed_timeframe
            state.compensation_period = proposed_compensation_period
            return state

        # CONTINUE / REFINE: Evolve state deterministically
        if proposed_subject:
            state.active_subject = proposed_subject
        if proposed_role:
            state.active_role = proposed_role
        if proposed_location:
            state.active_location = proposed_location
        if proposed_intent:
            state.active_intent = proposed_intent
        if proposed_timeframe:
            state.timeframe = proposed_timeframe
        if proposed_compensation_period:
            state.compensation_period = proposed_compensation_period

        if proposed_entities:
            existing_set = set(state.active_entities)
            for ent in proposed_entities:
                if ent and ent not in existing_set:
                    state.active_entities.append(ent)

        return state


class LLMHistoryRewriter(HistoryRewriter):
    """
    Semantic Context Resolver and Multi-Channel Query Router.
    Analyzes conversation state, determines topic lifecycle actions (CONTINUE, REFINE, SWITCH, RESET, STANDALONE),
    and generates channel-specific retrieval queries.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        model: str,
        cache: HistoryRewriteCache,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        self._llm_provider = llm_provider
        self._model = model
        self._cache = cache
        self._cache_ttl = cache_ttl_seconds
        self._validator = StateTransitionValidator()

    def _get_cache_key(
        self, conversation_id: UUID, last_message_id: UUID, question: str
    ) -> str:
        q_hash = hashlib.sha256(question.strip().lower().encode("utf-8")).hexdigest()
        return f"resolution:{conversation_id}:{last_message_id}:{q_hash}"

    def _extract_json_from_response(self, text: str) -> dict:
        content = text.strip()
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if json_match:
            content = json_match.group(1)
        elif "{" in content and "}" in content:
            content = content[content.find("{") : content.rfind("}") + 1]
        try:
            return json.loads(content)
        except Exception:
            # Fallback for plain text LLM responses (e.g. mock or plain text generation)
            clean_text = content.strip().strip('"')
            return {
                "contextualized_query": clean_text,
                "confidence": 0.85,
                "is_context_dependent": True,
                "context_action": "CONTINUE",
            }

    def _build_deterministic_fallback(
        self,
        question: str,
        history: list[ConversationMessage],
        reason: str,
    ) -> HistoryRewriteResult:
        """Deterministic fallback when LLM resolution fails or returns low confidence."""
        # Check if question contains obvious conversational follow-up triggers
        q_lower = question.lower().strip()
        pronouns = {
            "it",
            "its",
            "they",
            "them",
            "he",
            "him",
            "his",
            "she",
            "her",
            "that",
            "this",
            "these",
            "those",
            "himself",
            "herself",
        }
        followup_phrases = [
            "what about",
            "how about",
            "what was",
            "who was",
            "where was",
            "and in",
            "and for",
            "and what",
            "as per",
            "give me",
        ]
        words = set(q_lower.translate(str.maketrans("", "", "?.,!/")).split())
        has_followup_phrase = any(p in q_lower for p in followup_phrases)
        is_followup = bool(
            not words.isdisjoint(pronouns) or has_followup_phrase or len(words) <= 2
        )

        rewritten = question
        action = ContextAction.STANDALONE
        if is_followup and history:
            # Extract last user query as anchor
            last_user_msg = next(
                (m.content for m in reversed(history) if m.role == MessageRole.USER),
                None,
            )
            if last_user_msg:
                rewritten = f"{last_user_msg} - {question}"
                action = ContextAction.CONTINUE

        resolution = ContextResolution(
            original_query=question,
            contextualized_query=rewritten,
            retrieval_queries=ChannelRetrievalQueries(
                document_query=rewritten,
                web_query=rewritten
                if "market" in q_lower or "salary" in q_lower
                else None,
            ),
            is_context_dependent=is_followup,
            context_action=action,
            intent="GENERAL_QUERY",
            source_mode=SourceMode.HYBRID
            if "market" in q_lower
            else SourceMode.DOCUMENT_ONLY,
            domain_context=DomainContext(primary="GENERAL"),
            confidence=0.6,
            rewrite_reason=reason,
        )

        return HistoryRewriteResult(
            original_query=question,
            rewritten_query=rewritten,
            rewrite_reason=reason,
            rewrite_applied=(rewritten != question),
            context_action=action,
            intent="GENERAL_QUERY",
            source_mode=resolution.source_mode,
            domain_context=resolution.domain_context,
            retrieval_queries=resolution.retrieval_queries,
            resolution=resolution,
            topic_state=ConversationTopicState(),
        )

    def _heuristically_needs_rewrite(self, question: str) -> bool:
        """
        Cheap pre-filter to determine if a query might be context-dependent.
        If pronouns, conversational openers, or follow-up markers are present,
        semantic LLM context resolution is invoked.
        """
        q_lower = question.lower().strip()
        pronouns = {
            "it",
            "its",
            "they",
            "them",
            "their",
            "he",
            "him",
            "his",
            "she",
            "her",
            "hers",
            "this",
            "that",
            "these",
            "those",
            "then",
            "there",
            "here",
            "himself",
            "herself",
            "former",
            "latter",
            "whom",
            "whose",
            "which",
            "me",
            "my",
            "mine",
            "myself",
            "us",
            "our",
        }
        words = set(q_lower.translate(str.maketrans("", "", "?.,!/")).split())
        if not words.isdisjoint(pronouns):
            return True

        follow_up_phrases = [
            "about",
            "more",
            "explain",
            "why",
            "how",
            "what about",
            "how about",
            "tell me",
            "give me",
            "can you",
            "could you",
            "as per",
            "estimate",
            "based on",
            "what was",
            "who was",
            "where was",
            "and in",
            "and for",
            "and what",
            "salary",
            "market",
            "compensation",
            "annually",
            "monthly",
        ]
        for phrase in follow_up_phrases:
            if phrase in q_lower:
                return True

        if len(words) <= 2:
            return True

        return False

    async def rewrite(
        self,
        question: str,
        history: list[ConversationMessage],
        current_state: ConversationTopicState | None = None,
    ) -> HistoryRewriteResult:
        """
        Resolve conversational context, update conversation state lifecycle,
        and generate channel-specific retrieval queries.
        """
        # 1. Standalone bypass if no history
        if not history:
            resolution = ContextResolution(
                original_query=question,
                contextualized_query=question,
                retrieval_queries=ChannelRetrievalQueries(
                    document_query=question,
                    web_query=None,
                ),
                is_context_dependent=False,
                context_action=ContextAction.STANDALONE,
                intent="GENERAL_QUERY",
                source_mode=SourceMode.DOCUMENT_ONLY,
                domain_context=DomainContext(primary="GENERAL"),
                confidence=1.0,
                rewrite_reason="First turn - no prior history.",
            )
            return HistoryRewriteResult(
                original_query=question,
                rewritten_query=question,
                rewrite_reason="No conversation history available.",
                rewrite_applied=False,
                context_action=ContextAction.STANDALONE,
                intent="GENERAL_QUERY",
                source_mode=SourceMode.DOCUMENT_ONLY,
                domain_context=DomainContext(primary="GENERAL"),
                retrieval_queries=resolution.retrieval_queries,
                resolution=resolution,
                topic_state=ConversationTopicState(),
            )

        # 2. Heuristic pre-filter for obvious standalone queries
        if not self._heuristically_needs_rewrite(question):
            resolution = ContextResolution(
                original_query=question,
                contextualized_query=question,
                retrieval_queries=ChannelRetrievalQueries(
                    document_query=question,
                    web_query=None,
                ),
                is_context_dependent=False,
                context_action=ContextAction.STANDALONE,
                intent="GENERAL_QUERY",
                source_mode=SourceMode.DOCUMENT_ONLY,
                domain_context=DomainContext(primary="GENERAL"),
                confidence=1.0,
                rewrite_reason="Query heuristically determined to be standalone.",
            )
            return HistoryRewriteResult(
                original_query=question,
                rewritten_query=question,
                rewrite_reason="Query heuristically determined to be standalone.",
                rewrite_applied=False,
                context_action=ContextAction.STANDALONE,
                intent="GENERAL_QUERY",
                source_mode=SourceMode.DOCUMENT_ONLY,
                domain_context=DomainContext(primary="GENERAL"),
                retrieval_queries=resolution.retrieval_queries,
                resolution=resolution,
                topic_state=current_state or ConversationTopicState(),
            )

        # 2. Check Cache
        last_message = history[-1]
        cache_key = self._get_cache_key(
            last_message.conversation_id, last_message.id, question
        )

        try:
            cached_val = await self._cache.get(cache_key)
            if cached_val:
                try:
                    cached_dict = json.loads(cached_val)
                    resolution = ContextResolution.model_validate(
                        cached_dict.get("resolution", cached_dict)
                    )
                    return HistoryRewriteResult(
                        original_query=question,
                        rewritten_query=resolution.contextualized_query,
                        rewrite_reason="Cache hit",
                        rewrite_applied=resolution.is_context_dependent,
                        context_action=resolution.context_action,
                        intent=resolution.intent,
                        source_mode=resolution.source_mode,
                        domain_context=resolution.domain_context,
                        retrieval_queries=resolution.retrieval_queries,
                        resolution=resolution,
                        topic_state=current_state or ConversationTopicState(),
                    )
                except Exception:
                    # Fallback for plain string cached values
                    return HistoryRewriteResult(
                        original_query=question,
                        rewritten_query=cached_val,
                        rewrite_reason="Cache hit (legacy format)",
                        rewrite_applied=True,
                        context_action=ContextAction.CONTINUE,
                        intent="GENERAL_QUERY",
                        source_mode=SourceMode.DOCUMENT_ONLY,
                        domain_context=DomainContext(primary="GENERAL"),
                        retrieval_queries=ChannelRetrievalQueries(
                            document_query=cached_val
                        ),
                        resolution=None,
                        topic_state=current_state or ConversationTopicState(),
                    )
        except Exception as e:
            logger.warning(f"Failed to read from rewrite cache: {e}")

        # 3. Format context turns
        messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=CONTEXT_RESOLVER_SYSTEM_PROMPT)
        ]

        # Include state summary if present
        state_summary = ""
        if current_state:
            state_dict = current_state.model_dump(exclude_none=True)
            if state_dict:
                state_summary = f"Current Conversation Topic State:\n{json.dumps(state_dict, indent=2)}\n\n"

        history_lines = []
        for msg in history[-6:]:
            role_str = "User" if msg.role == MessageRole.USER else "Assistant"
            history_lines.append(f"{role_str}: {msg.content}")

        user_content = (
            f"{state_summary}"
            f"Conversation History:\n" + "\n".join(history_lines) + f"\n\n"
            f"New User Message: {question}\n\n"
            f"Generate semantic context resolution JSON:"
        )
        messages.append(ChatMessage(role=ChatRole.USER, content=user_content))

        # 4. Invoke LLM for structured resolution
        try:
            raw_response = await self._llm_provider.generate(
                messages=messages,
                model=self._model,
                temperature=0.0,
                max_tokens=600,
            )
            resp_text = (
                raw_response.content
                if hasattr(raw_response, "content")
                else raw_response[0]
            )
            parsed_data = self._extract_json_from_response(resp_text)

            # Map raw dictionary to structured ContextResolution
            action_str = str(parsed_data.get("context_action", "CONTINUE")).upper()
            try:
                action_enum = ContextAction(action_str)
            except ValueError:
                action_enum = ContextAction.CONTINUE

            source_mode_str = str(
                parsed_data.get("source_mode", "DOCUMENT_ONLY")
            ).upper()
            try:
                source_mode_enum = SourceMode(source_mode_str)
            except ValueError:
                source_mode_enum = SourceMode.DOCUMENT_ONLY

            contextualized_q = str(
                parsed_data.get("contextualized_query") or question
            ).strip()
            confidence_val = float(parsed_data.get("confidence", 0.9))
            confidence_val = max(0.0, min(1.0, confidence_val))

            # Operational confidence validation: fallback if below conservative threshold
            if confidence_val < 0.60:
                return self._build_deterministic_fallback(
                    question=question,
                    history=history,
                    reason=f"LLM confidence {confidence_val:.2f} below threshold (0.60)",
                )

            primary_dom = str(parsed_data.get("primary_domain", "GENERAL")).upper()
            sec_doms = [
                str(d).upper() for d in parsed_data.get("secondary_domains", [])
            ]
            entities_list = [str(e) for e in parsed_data.get("entities", [])]

            channel_queries = ChannelRetrievalQueries(
                document_query=parsed_data.get("document_query") or contextualized_q,
                web_query=parsed_data.get("web_query"),
                graph_query=parsed_data.get("graph_query"),
            )

            domain_ctx = DomainContext(
                primary=primary_dom,
                secondary=sec_doms,
                entities=entities_list,
            )

            is_dependent = bool(
                parsed_data.get(
                    "is_context_dependent", action_enum != ContextAction.STANDALONE
                )
            )

            resolution = ContextResolution(
                original_query=question,
                contextualized_query=contextualized_q,
                retrieval_queries=channel_queries,
                is_context_dependent=is_dependent,
                context_action=action_enum,
                intent=str(parsed_data.get("intent", "GENERAL_QUERY")).upper(),
                source_mode=source_mode_enum,
                domain_context=domain_ctx,
                active_subject=parsed_data.get("active_subject"),
                active_role=parsed_data.get("active_role"),
                active_location=parsed_data.get("active_location"),
                active_entities=entities_list,
                confidence=confidence_val,
                rewrite_reason=parsed_data.get(
                    "reasoning", "LLM semantic resolution applied"
                ),
            )

            # Deterministic state transition
            updated_state = self._validator.validate_and_transition(
                current_state=current_state,
                proposed_action=action_enum,
                proposed_subject=resolution.active_subject,
                proposed_role=resolution.active_role,
                proposed_location=resolution.active_location,
                proposed_entities=resolution.active_entities,
                proposed_intent=resolution.intent,
                proposed_timeframe=parsed_data.get("timeframe"),
                proposed_compensation_period=parsed_data.get("compensation_period"),
            )

            # 5. Populate cache
            try:
                cache_payload = json.dumps({"resolution": resolution.model_dump()})
                await self._cache.set(cache_key, cache_payload, self._cache_ttl)
            except Exception as e:
                logger.warning(f"Failed to write to resolution cache: {e}")

            return HistoryRewriteResult(
                original_query=question,
                rewritten_query=contextualized_q,
                rewrite_reason=resolution.rewrite_reason
                or "Context resolution applied",
                rewrite_applied=(contextualized_q != question and is_dependent),
                context_action=action_enum,
                intent=resolution.intent,
                source_mode=source_mode_enum,
                domain_context=domain_ctx,
                retrieval_queries=channel_queries,
                resolution=resolution,
                topic_state=updated_state,
            )

        except Exception as e:
            logger.exception(
                f"Error during semantic context resolution: {e}. Applying deterministic fallback."
            )
            return self._build_deterministic_fallback(
                question=question,
                history=history,
                reason=f"Failed to generate structured resolution: {e}",
            )

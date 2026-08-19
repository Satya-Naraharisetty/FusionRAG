import logging
from collections.abc import AsyncIterator
from typing import Any

from app.chat.domain.interfaces import LLMProvider, StreamChunk
from app.chat.domain.models import ChatMessage, ChatRole, Citation, Usage
from app.chat.domain.multi_agent import (
    AgentResult,
    AgentType,
    SynthesisRequest,
)

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM_PROMPT = """You are a precise, grounded synthesis agent in a multi-agent system.
Your responsibility is to synthesize a final answer to the user's question using ONLY the provided evidence items and successful specialist findings.

STRICT EVIDENCE INTEGRITY RULES:
1. Ground your factual statements strictly in the provided evidence items and successful specialist outputs.
2. Failed or skipped specialist task descriptions are diagnostic warnings only. Do NOT treat failed task error messages or unexecuted steps as factual evidence.
3. Do NOT invent or hallucinate document IDs, chunk IDs, URLs, citations, or facts.
4. If the provided evidence is empty, conflicting, or insufficient to answer the question completely, you MUST explicitly state that the evidence is insufficient.
5. If a specialist task reported a failure or was skipped, acknowledge the limitation honestly without speculating."""


class SynthesisAgent:
    """
    Synthesis specialist agent.
    Combines verified specialist outputs and evidence into a final grounded response.
    Preserves citations and source attribution. Does NOT perform independent retrieval,
    database access, or arbitrary tool calls.
    """

    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm_provider = llm_provider

    @property
    def agent_type(self) -> AgentType:
        return AgentType.SYNTHESIS

    def _build_synthesis_prompt(self, request: SynthesisRequest) -> list[ChatMessage]:
        """Constructs grounded chat messages from specialist results and original user query."""
        evidence_sections: list[str] = []
        successful_summaries: list[str] = []
        diagnostic_failures: list[str] = []

        for res in request.specialist_results:
            if res.success:
                successful_summaries.append(
                    f"[{res.agent_type.value} Task '{res.task_id}']:\n{res.output}"
                )
                for ev in res.evidence:
                    doc_label = ev.document_name or "Unknown Document"
                    evidence_sections.append(
                        f"--- Source: {doc_label} ---\n{ev.content}"
                    )
            else:
                diagnostic_failures.append(
                    f"[{res.agent_type.value} Task '{res.task_id}' ({res.status.value})]: {res.error or 'Task failed'}"
                )

        combined_evidence = (
            "\n\n".join(evidence_sections)
            if evidence_sections
            else "(No document chunks retrieved)"
        )
        combined_successful = (
            "\n\n".join(successful_summaries)
            if successful_summaries
            else "(No successful specialist outputs)"
        )
        combined_failures = (
            "\n".join(diagnostic_failures)
            if diagnostic_failures
            else "(None - all tasks executed successfully)"
        )

        user_content = (
            f"User Question: {request.original_request}\n\n"
            f"=== Successful Specialist Findings ===\n{combined_successful}\n\n"
            f"=== Grounded Evidence ===\n{combined_evidence}\n\n"
            f"=== Diagnostic Notices / Incomplete Operations ===\n{combined_failures}\n\n"
            f"Please synthesize the final answer for the user based strictly on the above evidence:"
        )

        return [
            ChatMessage(role=ChatRole.SYSTEM, content=SYNTHESIS_SYSTEM_PROMPT),
            ChatMessage(role=ChatRole.USER, content=user_content),
        ]

    def _collect_citations(
        self, specialist_results: list[AgentResult]
    ) -> list[Citation]:
        """Collects unique citations from all successful specialist results."""
        seen_chunks = set()
        unique_citations: list[Citation] = []
        for res in specialist_results:
            if res.success:
                for cit in res.citations:
                    if cit.chunk_id not in seen_chunks:
                        seen_chunks.add(cit.chunk_id)
                        unique_citations.append(cit)
        return unique_citations

    async def synthesize(
        self,
        request: SynthesisRequest,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> tuple[str, list[Citation], Usage]:
        """
        Synthesizes a full grounded answer from specialist results.
        Returns (answer_text, citations, usage).
        """
        messages = self._build_synthesis_prompt(request)
        citations = self._collect_citations(request.specialist_results)

        response = await self.llm_provider.generate(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        from app.chat.domain.interfaces import ProviderResponse

        if isinstance(response, tuple) and not hasattr(response, "content"):
            response = ProviderResponse(content=response[0], usage=response[1])

        answer_text = response.content or ""
        usage = response.usage or Usage()

        return answer_text, citations, usage

    async def synthesize_stream(
        self,
        request: SynthesisRequest,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Streams synthesized response tokens and yields lifecycle SSE events.
        """
        messages = self._build_synthesis_prompt(request)
        citations = self._collect_citations(request.specialist_results)

        citations_data = [
            {
                "document_id": str(c.document_id),
                "document_name": c.document_name,
                "chunk_id": str(c.chunk_id),
                "chunk_index": c.chunk_index,
            }
            for c in citations
        ]

        # 1. Emit synthesis started
        yield {
            "event": "synthesis_started",
            "data": {
                "citations_count": len(citations),
                "specialist_count": len(request.specialist_results),
            },
        }

        # 2. Stream tokens from LLM
        final_usage = Usage()
        full_text = []

        async for chunk in self.llm_provider.stream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            if isinstance(chunk, tuple) and not hasattr(chunk, "text_delta"):
                chunk = StreamChunk(text_delta=chunk[0], usage=chunk[1])

            if chunk.text_delta:
                full_text.append(chunk.text_delta)
                yield {
                    "event": "text",
                    "data": {"text": chunk.text_delta},
                }

            if chunk.usage:
                final_usage = chunk.usage

        # 3. Emit synthesis completed
        yield {
            "event": "synthesis_done",
            "data": {
                "citations": citations_data,
                "usage": {
                    "prompt_tokens": final_usage.prompt_tokens,
                    "completion_tokens": final_usage.completion_tokens,
                    "total_tokens": final_usage.total_tokens,
                },
            },
        }

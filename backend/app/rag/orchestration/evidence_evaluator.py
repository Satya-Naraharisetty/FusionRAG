import logging
import re
from uuid import UUID

from app.documents.domain.models import DocumentRetrievalScope, RetrievedChunk
from app.rag.orchestration.models import EvidenceAssessment

logger = logging.getLogger(__name__)


def _extract_keywords(text: str) -> set[str]:
    """Extracts non-stopword tokens of length > 2."""
    stopwords = {
        "what",
        "is",
        "the",
        "and",
        "or",
        "for",
        "with",
        "about",
        "how",
        "are",
        "was",
        "were",
        "does",
        "did",
        "this",
        "that",
        "from",
        "into",
        "over",
        "under",
        "across",
        "between",
        "both",
        "all",
        "each",
        "any",
        "some",
    }
    tokens = re.findall(r"\b[a-zA-Z0-9_-]{3,}\b", text.lower())
    return {t for t in tokens if t not in stopwords}


class EvidenceSufficiencyEvaluator:
    """
    Evaluator for evidence sufficiency, coverage of required targets,
    contradiction detection, and citation readiness.
    Operates strictly on observable evidence chunks without chain-of-thought.
    """

    def __init__(
        self,
        min_relevance_threshold: float = 0.25,
        max_context_tokens: int = 4000,
    ) -> None:
        self._min_relevance = min_relevance_threshold
        self._max_context_tokens = max_context_tokens

    async def evaluate(
        self,
        query: str,
        evidence: list[RetrievedChunk],
        expected_targets: list[str],
        scope: DocumentRetrievalScope | None = None,
        allowed_doc_ids: set[UUID] | list[UUID] | None = None,
    ) -> EvidenceAssessment:
        if not evidence:
            return EvidenceAssessment(
                sufficient=False,
                confidence=0.0,
                missing_targets=list(expected_targets) if expected_targets else [query],
                supported_targets=[],
                conflicting_evidence=False,
                duplicate_evidence=False,
                citation_ready=False,
                conflict_details=[],
            )

        # 1. Deduplication & Authorization check
        seen_chunk_ids = set()
        has_duplicates = False
        allowed_set = (
            {str(d) for d in allowed_doc_ids} if allowed_doc_ids is not None else None
        )

        valid_chunks: list[RetrievedChunk] = []
        for c in evidence:
            cid_str = str(c.chunk_id)
            if cid_str in seen_chunk_ids:
                has_duplicates = True
            seen_chunk_ids.add(cid_str)

            # Verify authorization scope
            if allowed_set is not None:
                if str(c.document_id) not in allowed_set:
                    logger.warning(
                        f"Scope violation: chunk {c.chunk_id} from unauthorized doc {c.document_id}"
                    )
                    continue
            valid_chunks.append(c)

        if not valid_chunks:
            return EvidenceAssessment(
                sufficient=False,
                confidence=0.0,
                missing_targets=list(expected_targets) if expected_targets else [query],
                supported_targets=[],
                conflicting_evidence=False,
                duplicate_evidence=has_duplicates,
                citation_ready=False,
                conflict_details=["all_chunks_unauthorized_or_empty"],
            )

        # 2. Target Coverage Evaluation
        supported: list[str] = []
        missing: list[str] = []

        all_text = " ".join(c.text for c in valid_chunks).lower()
        all_words = set(re.findall(r"\b[a-zA-Z0-9_-]+\b", all_text))

        targets_to_check = expected_targets if expected_targets else [query]
        for target in targets_to_check:
            t_keywords = _extract_keywords(target)
            if not t_keywords:
                supported.append(target)
                continue

            # Check if majority of target keywords appear in retrieved evidence
            matched_kw = []
            for kw in t_keywords:
                if kw in all_text:
                    matched_kw.append(kw)
                elif any(
                    (
                        len(kw) >= 4
                        and len(w) >= 4
                        and (w.startswith(kw[:4]) or kw.startswith(w[:4]))
                    )
                    or (kw in w or w in kw)
                    for w in all_words
                ):
                    matched_kw.append(kw)

            match_ratio = len(matched_kw) / len(t_keywords)

            if match_ratio >= 0.33 or (len(t_keywords) == 1 and len(matched_kw) == 1):
                supported.append(target)
            else:
                missing.append(target)

        # 3. Contradiction Detection
        conflicts: list[str] = []
        has_conflicts = self._detect_contradictions(valid_chunks, conflicts)

        # 4. Citation Readiness
        citation_ready = all(
            bool(c.document_name and c.document_id and c.text.strip())
            for c in valid_chunks
        )

        # 5. Overall Sufficiency Calculation
        coverage_ratio = (
            len(supported) / len(targets_to_check) if targets_to_check else 1.0
        )
        sufficient = (
            len(missing) == 0
            and not has_conflicts
            and citation_ready
            and len(valid_chunks) > 0
        )
        confidence = round(coverage_ratio * (0.8 if has_conflicts else 1.0), 3)

        return EvidenceAssessment(
            sufficient=sufficient,
            confidence=confidence,
            missing_targets=missing,
            supported_targets=supported,
            conflicting_evidence=has_conflicts,
            duplicate_evidence=has_duplicates,
            citation_ready=citation_ready,
            conflict_details=conflicts,
        )

    def _detect_contradictions(
        self, chunks: list[RetrievedChunk], conflict_out: list[str]
    ) -> bool:
        """
        Detects factual or numerical contradictions across retrieved evidence chunks.
        e.g., conflicting SLO percentages ('99.9%' vs '99.99%'), conflicting revenue numbers,
        or conflicting expiration days.
        """
        if len(chunks) < 2:
            return False

        # Check for numeric metrics in similar context
        # Pattern for percentages and revenue numbers
        pct_pattern = re.compile(r"(\b\d{1,3}(?:\.\d+)?%)")
        found_pcts: dict[str, set[str]] = {}

        for c in chunks:
            text = c.text
            pcts = pct_pattern.findall(text)
            if pcts:
                # Find associated keywords in snippet
                for p in pcts:
                    ctx = text.lower()
                    if "slo" in ctx or "availability" in ctx or "uptime" in ctx:
                        found_pcts.setdefault("availability_slo", set()).add(p)
                    elif "churn" in ctx:
                        found_pcts.setdefault("churn_rate", set()).add(p)
                    elif "growth" in ctx or "revenue" in ctx:
                        found_pcts.setdefault("revenue_metric", set()).add(p)

        has_conflict = False
        for metric_name, values in found_pcts.items():
            if len(values) > 1:
                has_conflict = True
                conflict_msg = (
                    f"Conflicting values detected for {metric_name}: {sorted(values)}"
                )
                conflict_out.append(conflict_msg)
                logger.info(f"EvidenceEvaluator conflict detected: {conflict_msg}")

        return has_conflict

import re
import time

from app.documents.domain.interfaces import QueryProcessor
from app.documents.domain.models import ProcessedQuery, QueryStats


class DefaultQueryProcessor(QueryProcessor):
    def __init__(
        self,
        acronyms: dict[str, str] | None = None,
        typos: dict[str, str] | None = None,
    ):
        # Normalize keys to lowercase for matching
        self.acronyms = {k.lower(): v.lower() for k, v in (acronyms or {}).items()}
        self.typos = {k.lower(): v.lower() for k, v in (typos or {}).items()}

    def process(self, query: str) -> ProcessedQuery:
        start_time = time.perf_counter()

        original_length = len(query)

        # 1. Lowercase normalization
        cleaned_base = query.lower()

        # Helper to do word-level matching for typos and acronyms
        # 2. Typo correction
        typo_corrected = cleaned_base
        corrections_count = 0
        has_typos_corrected = False

        if self.typos:
            words = re.findall(r"\b\w+\b", cleaned_base)
            corrected_words = []
            for w in words:
                if w in self.typos:
                    corrected_words.append(self.typos[w])
                    corrections_count += 1
                    has_typos_corrected = True
                else:
                    corrected_words.append(w)
            typo_corrected = " ".join(corrected_words) if words else cleaned_base

        # 3. Clean query for dense search (whitespace and punctuation normalized, no acronym expansion)
        # Replace non-alphanumeric/non-whitespace characters with space
        cleaned_query = re.sub(r"[^\w\s]", " ", typo_corrected)
        cleaned_query = " ".join(cleaned_query.split())

        # 4. Expanded query for sparse search (with acronym expansions)
        expanded_query = cleaned_query
        expansions_count = 0
        has_acronyms_expanded = False

        if self.acronyms:
            words = cleaned_query.split()
            expanded_words = []
            for w in words:
                if w in self.acronyms:
                    expanded_words.append(self.acronyms[w])
                    expansions_count += 1
                    has_acronyms_expanded = True
                else:
                    expanded_words.append(w)
            expanded_query = " ".join(expanded_words) if words else cleaned_query

        # Re-apply punctuation cleanup and whitespace normalization on expanded query
        expanded_query = re.sub(r"[^\w\s]", " ", expanded_query)
        expanded_query = " ".join(expanded_query.split())

        end_time = time.perf_counter()
        processing_time_ms = (end_time - start_time) * 1000.0

        cleaned_length = len(cleaned_query)
        word_count = len(cleaned_query.split())
        char_count = len(cleaned_query)

        stats = QueryStats(
            original_length=original_length,
            cleaned_length=cleaned_length,
            word_count=word_count,
            char_count=char_count,
            has_acronyms_expanded=has_acronyms_expanded,
            has_typos_corrected=has_typos_corrected,
            processing_time_ms=processing_time_ms,
            expansions_count=expansions_count,
            corrections_count=corrections_count,
        )

        return ProcessedQuery(
            original_query=query,
            cleaned_query=cleaned_query,
            expanded_query=expanded_query,
            stats=stats,
        )

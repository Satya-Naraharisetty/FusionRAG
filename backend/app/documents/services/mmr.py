import re
from typing import Callable
from app.documents.domain.interfaces import MMRSelector
from app.documents.domain.models import RetrievedChunk

def tokenize(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    return text.split()

def jaccard_similarity(chunk1: RetrievedChunk, chunk2: RetrievedChunk) -> float:
    set1 = set(tokenize(chunk1.text))
    set2 = set(tokenize(chunk2.text))
    if not set1 or not set2:
        return 0.0
    return len(set1.intersection(set2)) / len(set1.union(set2))

class DefaultMMRSelector(MMRSelector):
    def select(
        self,
        chunks: list[RetrievedChunk],
        top_k: int,
        mmr_lambda: float = 0.5,
        similarity_fn: Callable[[RetrievedChunk, RetrievedChunk], float] | None = None,
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []

        # Determine the similarity function to use (default to Jaccard)
        sim_func = similarity_fn or jaccard_similarity

        # Select the first chunk (highest score)
        selected = [chunks[0]]
        remaining = chunks[1:]

        limit = min(top_k, len(chunks))

        while len(selected) < limit and remaining:
            best_score = -float('inf')
            best_chunk_idx = -1

            for idx, r_chunk in enumerate(remaining):
                # Sim1 is the score of the chunk. Use normalized_score if available, otherwise similarity_score.
                sim1 = r_chunk.normalized_score if r_chunk.normalized_score is not None else r_chunk.similarity_score

                # Sim2 is the max similarity between r_chunk and any selected chunk
                max_sim2 = 0.0
                for s_chunk in selected:
                    sim2 = sim_func(r_chunk, s_chunk)
                    if sim2 > max_sim2:
                        max_sim2 = sim2

                mmr_score = mmr_lambda * sim1 - (1.0 - mmr_lambda) * max_sim2
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_chunk_idx = idx

            if best_chunk_idx != -1:
                selected.append(remaining.pop(best_chunk_idx))
            else:
                break

        return selected

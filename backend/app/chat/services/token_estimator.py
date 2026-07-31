from app.chat.domain.interfaces import TokenEstimator


class CharacterTokenEstimator(TokenEstimator):
    """
    Simple character-based token estimator strategy (len(text) // 4).
    Matches the heuristic in ChunkingService.
    """

    def estimate(self, text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // 4)

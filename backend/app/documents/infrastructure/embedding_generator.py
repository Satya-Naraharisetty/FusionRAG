import asyncio
import logging

import httpx

from app.documents.domain.interfaces import EmbeddingGenerator

logger = logging.getLogger(__name__)


class LocalEmbeddingGenerator(EmbeddingGenerator):
    """
    Local embedding generator using sentence-transformers.
    Runs entirely offline - zero API costs, minimal latency.
    Uses sentence-transformers models like all-MiniLM-L6-v2 (384 dims, 256 max tokens).
    """

    def __init__(
        self, model_name: str = "all-MiniLM-L6-v2", device: str = "cpu"
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError(
                "sentence-transformers not installed. Run: pip install sentence-transformers"
            )

        self._model_name = model_name
        self._device = device
        self._model = SentenceTransformer(model_name, device=device)
        dim = self._model.get_sentence_embedding_dimension()
        if dim is None:
            raise RuntimeError(
                f"Could not retrieve embedding dimension for model {model_name}"
            )
        self._dimension: int = dim

    @property
    def dimension(self) -> int:
        return self._dimension

    async def generate(self, text: str) -> list[float]:
        results = await self.batch_generate([text])
        return results[0]

    async def batch_generate(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        def _encode():
            embeddings = self._model.encode(
                texts,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            return embeddings.tolist()

        return await asyncio.to_thread(_encode)


class GeminiEmbeddingGenerator(EmbeddingGenerator):
    """
    Gemini implementation of the EmbeddingGenerator.
    Queries the Google Generative Language API via HTTP POST using httpx.AsyncClient.
    """

    def __init__(self, api_key: str, model: str, dimension: int) -> None:
        self._api_key = api_key
        # Ensure the model name format is correct (models/text-embedding-004)
        if not model.startswith("models/"):
            self._model = f"models/{model}"
        else:
            self._model = model
        self._dimension = dimension

    async def generate(self, text: str) -> list[float]:
        results = await self.batch_generate([text])
        if not results:
            raise RuntimeError("Gemini API failed to return embeddings.")
        return results[0]

    async def batch_generate(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        # Gemini batch embedding endpoint
        url = f"https://generativelanguage.googleapis.com/v1beta/{self._model}:batchEmbedContents?key={self._api_key}"

        requests_payload = []
        for text in texts:
            requests_payload.append(
                {"model": self._model, "content": {"parts": [{"text": text}]}}
            )

        payload = {"requests": requests_payload}

        max_retries = 3
        backoff_factor = 2.0

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    data = response.json()

                    embeddings = [item["values"] for item in data["embeddings"]]

                    for i, emb in enumerate(embeddings):
                        if len(emb) != self._dimension:
                            raise ValueError(
                                f"Embedding dimension mismatch at index {i}: "
                                f"expected {self._dimension}, got {len(emb)}"
                            )

                    return embeddings
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if (
                    status_code in (429, 500, 502, 503, 504)
                    and attempt < max_retries - 1
                ):
                    sleep_time = backoff_factor**attempt
                    await asyncio.sleep(sleep_time)
                    continue
                raise
            except httpx.RequestError:
                if attempt < max_retries - 1:
                    sleep_time = backoff_factor**attempt
                    await asyncio.sleep(sleep_time)
                    continue
                raise

        raise RuntimeError(
            "Gemini embedding generation failed after all retry attempts."
        )

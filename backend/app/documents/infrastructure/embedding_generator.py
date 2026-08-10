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
        self._dimension = self._model.get_sentence_embedding_dimension()

    @property
    def dimension(self) -> int:
        return self._dimension

    def generate(self, text: str) -> list[float]:
        return self.batch_generate([text])[0]

    def batch_generate(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()


class OpenAIEmbeddingGenerator(EmbeddingGenerator):
    """
    OpenAI implementation of the EmbeddingGenerator.
    Queries the OpenAI API via HTTP POST using httpx.
    """

    def __init__(self, api_key: str, model: str, dimension: int) -> None:
        self._api_key = api_key
        self._model = model
        self._dimension = dimension
        self._url = "https://api.openai.com/v1/embeddings"

    def generate(self, text: str) -> list[float]:
        results = self.batch_generate([text])
        if not results:
            raise RuntimeError("OpenAI API failed to return embeddings.")
        return results[0]

    def batch_generate(self, texts: list[str]) -> list[list[float]]:
        import time

        if not texts:
            return []

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "input": texts,
            "model": self._model,
        }

        max_retries = 3
        backoff_factor = 2.0

        for attempt in range(max_retries):
            try:
                with httpx.Client() as client:
                    response = client.post(
                        self._url,
                        json=payload,
                        headers=headers,
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    data = response.json()

                    # Sort results by input index to match input order
                    sorted_data = sorted(data["data"], key=lambda x: x["index"])
                    embeddings = [item["embedding"] for item in sorted_data]

                    for i, emb in enumerate(embeddings):
                        if len(emb) != self._dimension:
                            raise ValueError(
                                f"Embedding dimension mismatch at index {i}: "
                                f"expected {self._dimension}, got {len(emb)}"
                            )

                    return embeddings
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                # Retry only on 429 (Rate Limit) and 5xx (Server Error) responses
                if (
                    status_code in (429, 500, 502, 503, 504)
                    and attempt < max_retries - 1
                ):
                    sleep_time = backoff_factor**attempt
                    time.sleep(sleep_time)
                    continue
                raise
            except httpx.RequestError:
                # Retry on connection/network level errors
                if attempt < max_retries - 1:
                    sleep_time = backoff_factor**attempt
                    time.sleep(sleep_time)
                    continue
                raise

        raise RuntimeError(
            "OpenAI embedding generation failed after all retry attempts."
        )


class GeminiEmbeddingGenerator(EmbeddingGenerator):
    """
    Gemini implementation of the EmbeddingGenerator.
    Queries the Google Generative Language API via HTTP POST using httpx.
    """

    def __init__(self, api_key: str, model: str, dimension: int) -> None:
        self._api_key = api_key
        # Ensure the model name format is correct (models/text-embedding-004)
        if not model.startswith("models/"):
            self._model = f"models/{model}"
        else:
            self._model = model
        self._dimension = dimension

    def generate(self, text: str) -> list[float]:
        results = self.batch_generate([text])
        if not results:
            raise RuntimeError("Gemini API failed to return embeddings.")
        return results[0]

    def batch_generate(self, texts: list[str]) -> list[list[float]]:
        import time

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
                with httpx.Client() as client:
                    response = client.post(
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
                    time.sleep(sleep_time)
                    continue
                raise
            except httpx.RequestError:
                if attempt < max_retries - 1:
                    sleep_time = backoff_factor**attempt
                    time.sleep(sleep_time)
                    continue
                raise

        raise RuntimeError(
            "Gemini embedding generation failed after all retry attempts."
        )

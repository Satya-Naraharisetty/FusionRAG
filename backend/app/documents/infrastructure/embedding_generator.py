import httpx
from app.documents.domain.interfaces import EmbeddingGenerator


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

from unittest.mock import MagicMock, patch

import pytest

from app.documents.infrastructure.embedding_generator import OpenAIEmbeddingGenerator


def test_openai_embedding_generator_success():
    api_key = "test-key"
    model = "text-embedding-3-small"
    dimension = 1536
    generator = OpenAIEmbeddingGenerator(api_key, model, dimension)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [{"embedding": [0.1] * 1536, "index": 0}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client.post", return_value=mock_response) as mock_post:
        result = generator.generate("hello world")
        assert len(result) == 1536
        assert result == [0.1] * 1536

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"
        assert kwargs["json"]["input"] == ["hello world"]
        assert kwargs["json"]["model"] == "text-embedding-3-small"


def test_openai_embedding_generator_dimension_mismatch():
    api_key = "test-key"
    model = "text-embedding-3-small"
    dimension = 1536
    generator = OpenAIEmbeddingGenerator(api_key, model, dimension)

    mock_response = MagicMock()
    mock_response.json.return_value = {"data": [{"embedding": [0.1] * 512, "index": 0}]}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client.post", return_value=mock_response):
        with pytest.raises(ValueError, match="Embedding dimension mismatch"):
            generator.generate("hello world")

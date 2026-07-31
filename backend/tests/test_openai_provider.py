from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.chat.domain.exceptions import LLMProviderError
from app.chat.domain.models import ChatMessage, ChatRole
from app.chat.infrastructure.openai_provider import OpenAIProvider


@pytest.mark.asyncio
async def test_openai_provider_generate_success():
    provider = OpenAIProvider(api_key="test-key")
    messages = [
        ChatMessage(role=ChatRole.SYSTEM, content="System prompt"),
        ChatMessage(role=ChatRole.USER, content="User prompt"),
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "This is the answer."}}],
        "usage": {
            "prompt_tokens": 15,
            "completion_tokens": 5,
            "total_tokens": 20,
        },
    }
    mock_response.raise_for_status = MagicMock()

    # Mock httpx.AsyncClient.post
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        content, usage = await provider.generate(
            messages=messages,
            model="gpt-4o-mini",
            temperature=0.0,
            max_tokens=100,
        )

        assert content == "This is the answer."
        assert usage.prompt_tokens == 15
        assert usage.completion_tokens == 5
        assert usage.total_tokens == 20

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"
        assert kwargs["json"]["model"] == "gpt-4o-mini"
        assert kwargs["json"]["temperature"] == 0.0
        assert kwargs["json"]["max_tokens"] == 100
        assert kwargs["json"]["stream"] is False


@pytest.mark.asyncio
async def test_openai_provider_generate_api_error():
    provider = OpenAIProvider(api_key="test-key")
    messages = [ChatMessage(role=ChatRole.USER, content="hello")]

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        import httpx
        # Simulate a 401 Unauthorized API error
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_post.side_effect = httpx.HTTPStatusError(
            "Unauthorized",
            request=MagicMock(),
            response=mock_response,
        )

        with pytest.raises(LLMProviderError, match="OpenAI API returned status 401"):
            await provider.generate(messages, "gpt-4o-mini", 0.0, 100)


@pytest.mark.asyncio
async def test_openai_provider_stream_success():
    provider = OpenAIProvider(api_key="test-key")
    messages = [ChatMessage(role=ChatRole.USER, content="hello")]

    # Mock the response lines for the stream
    stream_lines = [
        b'data: {"choices": [{"delta": {"content": "Hello"}}]}',
        b"",
        b'data: {"choices": [{"delta": {"content": " world"}}]}',
        b"",
        b'data: {"usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}',
        b"",
        b"data: [DONE]",
    ]

    class AsyncIteratorMock:
        def __init__(self, items):
            self.items = items

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0).decode("utf-8")

    class ResponseContextMock:
        def __init__(self, status_code, lines):
            self.status_code = status_code
            self.lines = lines

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        def aiter_lines(self):
            return AsyncIteratorMock(self.lines)

    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.return_value = ResponseContextMock(200, stream_lines)

        results = []
        async for chunk, usage in provider.stream(
            messages=messages,
            model="gpt-4o-mini",
            temperature=0.0,
            max_tokens=100,
        ):
            results.append((chunk, usage))

        assert len(results) == 3
        # First delta content
        assert results[0][0] == "Hello"
        assert results[0][1] is None
        # Second delta content
        assert results[1][0] == " world"
        assert results[1][1] is None
        # Third is usage metadata
        assert results[2][0] == ""
        assert results[2][1].prompt_tokens == 10
        assert results[2][1].completion_tokens == 2
        assert results[2][1].total_tokens == 12

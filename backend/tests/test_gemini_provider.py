from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.chat.domain.exceptions import LLMProviderError
from app.chat.domain.models import ChatMessage, ChatRole
from app.chat.infrastructure.gemini_provider import GeminiProvider


@pytest.mark.asyncio
async def test_gemini_provider_generate_success():
    provider = GeminiProvider(api_key="test-key")
    messages = [
        ChatMessage(role=ChatRole.SYSTEM, content="System prompt"),
        ChatMessage(role=ChatRole.USER, content="User prompt"),
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "This is Gemini's answer."}]
                }
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 15,
            "candidatesTokenCount": 5,
            "totalTokenCount": 20,
        },
    }
    mock_response.raise_for_status = MagicMock()

    # Mock httpx.AsyncClient.post
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        content, usage = await provider.generate(
            messages=messages,
            model="gemini-1.5-flash",
            temperature=0.0,
            max_tokens=100,
        )

        assert content == "This is Gemini's answer."
        assert usage.prompt_tokens == 15
        assert usage.completion_tokens == 5
        assert usage.total_tokens == 20

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        # Verify Gemini URL format
        assert "gemini-1.5-flash:generateContent" in args[0]
        assert "key=test-key" in args[0]
        
        # Verify payload mapping
        payload = kwargs["json"]
        assert payload["systemInstruction"]["parts"][0]["text"] == "System prompt"
        assert len(payload["contents"]) == 1
        assert payload["contents"][0]["role"] == "user"
        assert payload["contents"][0]["parts"][0]["text"] == "User prompt"
        assert payload["generationConfig"]["temperature"] == 0.0
        assert payload["generationConfig"]["maxOutputTokens"] == 100


@pytest.mark.asyncio
async def test_gemini_provider_generate_api_error():
    provider = GeminiProvider(api_key="test-key")
    messages = [ChatMessage(role=ChatRole.USER, content="hello")]

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        import httpx
        # Simulate a 400 Bad Request API error
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "API Key Invalid"
        mock_post.side_effect = httpx.HTTPStatusError(
            "Bad Request",
            request=MagicMock(),
            response=mock_response,
        )

        with pytest.raises(LLMProviderError, match="Gemini API returned status 400"):
            await provider.generate(messages, "gemini-1.5-flash", 0.0, 100)


@pytest.mark.asyncio
async def test_gemini_provider_stream_success():
    provider = GeminiProvider(api_key="test-key")
    messages = [ChatMessage(role=ChatRole.USER, content="hello")]

    # Mock the SSE response lines for Gemini
    stream_lines = [
        b'data: {"candidates": [{"content": {"parts": [{"text": "Hello"}]}}]}',
        b"",
        b'data: {"candidates": [{"content": {"parts": [{"text": " world"}]}}]}',
        b"",
        b'data: {"usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 2, "totalTokenCount": 12}}',
        b"",
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
            model="gemini-1.5-flash",
            temperature=0.0,
            max_tokens=100,
        ):
            results.append((chunk, usage))

        assert len(results) == 3
        assert results[0][0] == "Hello"
        assert results[0][1] is None
        assert results[1][0] == " world"
        assert results[1][1] is None
        assert results[2][0] == ""
        assert results[2][1].prompt_tokens == 10
        assert results[2][1].completion_tokens == 2
        assert results[2][1].total_tokens == 12

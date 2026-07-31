import json
from typing import AsyncIterator
import httpx

from app.chat.domain.exceptions import LLMProviderError
from app.chat.domain.interfaces import LLMProvider
from app.chat.domain.models import ChatMessage, Usage


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.url = "https://api.openai.com/v1/chat/completions"

    async def generate(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, Usage]:
        if not self.api_key:
            raise LLMProviderError("OpenAI API key is missing or not configured.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": msg.role.value, "content": msg.content} for msg in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.url,
                    json=payload,
                    headers=headers,
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()

                content = data["choices"][0]["message"]["content"]
                usage_data = data.get("usage", {})
                usage = Usage(
                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                    completion_tokens=usage_data.get("completion_tokens", 0),
                    total_tokens=usage_data.get("total_tokens", 0),
                )
                return content, usage
        except httpx.HTTPStatusError as e:
            raise LLMProviderError(f"OpenAI API returned status {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            raise LLMProviderError(f"OpenAI network request failed: {e}")
        except (KeyError, IndexError) as e:
            raise LLMProviderError(f"Failed to parse OpenAI API response: {e}")
        except Exception as e:
            raise LLMProviderError(f"OpenAI generation failed: {e}")

    async def stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[tuple[str, Usage | None]]:
        if not self.api_key:
            raise LLMProviderError("OpenAI API key is missing or not configured.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": msg.role.value, "content": msg.content} for msg in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    self.url,
                    json=payload,
                    headers=headers,
                    timeout=60.0,
                ) as response:
                    if response.status_code != 200:
                        await response.aread()  # load body for details
                        raise LLMProviderError(
                            f"OpenAI API returned status {response.status_code}: {response.text}"
                        )

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        if line == "data: [DONE]":
                            break
                        if line.startswith("data: "):
                            data_str = line[len("data: "):].strip()
                            data = json.loads(data_str)

                            # Extract usage metadata if present
                            usage_data = data.get("usage", None)
                            usage = None
                            if usage_data:
                                usage = Usage(
                                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                                    completion_tokens=usage_data.get("completion_tokens", 0),
                                    total_tokens=usage_data.get("total_tokens", 0),
                                )

                            # Extract choices delta content
                            choices = data.get("choices", [])
                            delta_content = ""
                            if choices:
                                delta = choices[0].get("delta", {})
                                delta_content = delta.get("content", "")

                            if delta_content or usage:
                                yield delta_content, usage
        except httpx.HTTPStatusError as e:
            raise LLMProviderError(f"OpenAI API returned status {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            raise LLMProviderError(f"OpenAI network request failed: {e}")
        except json.JSONDecodeError as e:
            raise LLMProviderError(f"Failed to decode stream line: {e}")
        except Exception as e:
            raise LLMProviderError(f"Streaming failed: {e}")

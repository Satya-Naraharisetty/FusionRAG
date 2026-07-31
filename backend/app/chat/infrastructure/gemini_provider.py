import json
from typing import AsyncIterator
import httpx

from app.chat.domain.exceptions import LLMProviderError
from app.chat.domain.interfaces import LLMProvider
from app.chat.domain.models import ChatMessage, ChatRole, Usage


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def _get_url(self, model: str, stream: bool) -> str:
        method = "streamGenerateContent" if stream else "generateContent"
        alt_sse = "&alt=sse" if stream else ""
        return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:{method}?key={self.api_key}{alt_sse}"

    def _build_payload(
        self,
        messages: list[ChatMessage],
        temperature: float,
        max_tokens: int,
    ) -> dict:
        contents = []
        system_instruction_content = ""

        for msg in messages:
            if msg.role == ChatRole.SYSTEM:
                system_instruction_content = msg.content
            else:
                # Map user/assistant to user/model
                role = "user" if msg.role == ChatRole.USER else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg.content}]
                })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            }
        }

        if system_instruction_content:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction_content}]
            }

        return payload

    async def generate(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, Usage]:
        if not self.api_key:
            raise LLMProviderError("Gemini API key is missing or not configured.")

        url = self._get_url(model, stream=False)
        payload = self._build_payload(messages, temperature, max_tokens)
        headers = {"Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()

                # Parse text
                candidates = data.get("candidates", [])
                if not candidates:
                    raise LLMProviderError("No generation candidates returned from Gemini.")

                parts = candidates[0].get("content", {}).get("parts", [])
                content = parts[0].get("text", "") if parts else ""

                # Parse token usage
                usage_data = data.get("usageMetadata", {})
                usage = Usage(
                    prompt_tokens=usage_data.get("promptTokenCount", 0),
                    completion_tokens=usage_data.get("candidatesTokenCount", 0),
                    total_tokens=usage_data.get("totalTokenCount", 0),
                )
                return content, usage
        except httpx.HTTPStatusError as e:
            raise LLMProviderError(f"Gemini API returned status {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            raise LLMProviderError(f"Gemini network request failed: {e}")
        except Exception as e:
            raise LLMProviderError(f"Gemini generation failed: {e}")

    async def stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[tuple[str, Usage | None]]:
        if not self.api_key:
            raise LLMProviderError("Gemini API key is missing or not configured.")

        url = self._get_url(model, stream=True)
        payload = self._build_payload(messages, temperature, max_tokens)
        headers = {"Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    url,
                    json=payload,
                    headers=headers,
                    timeout=60.0,
                ) as response:
                    if response.status_code != 200:
                        await response.aread()
                        raise LLMProviderError(
                            f"Gemini API returned status {response.status_code}: {response.text}"
                        )

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data_str = line[len("data: "):].strip()
                            data = json.loads(data_str)

                            # Parse text delta
                            candidates = data.get("candidates", [])
                            delta_content = ""
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                if parts:
                                    delta_content = parts[0].get("text", "")

                            # Parse token usage
                            usage_data = data.get("usageMetadata", None)
                            usage = None
                            if usage_data:
                                usage = Usage(
                                    prompt_tokens=usage_data.get("promptTokenCount", 0),
                                    completion_tokens=usage_data.get("candidatesTokenCount", 0),
                                    total_tokens=usage_data.get("totalTokenCount", 0),
                                )

                            if delta_content or usage:
                                yield delta_content, usage
        except httpx.HTTPStatusError as e:
            raise LLMProviderError(f"Gemini API returned status {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            raise LLMProviderError(f"Gemini network request failed: {e}")
        except json.JSONDecodeError as e:
            raise LLMProviderError(f"Failed to decode stream line: {e}")
        except Exception as e:
            raise LLMProviderError(f"Streaming failed: {e}")

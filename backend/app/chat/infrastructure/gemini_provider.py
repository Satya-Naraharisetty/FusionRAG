import json
import logging
import uuid
from collections.abc import AsyncIterator
from enum import Enum

import httpx
from app.chat.domain.agents import ToolCall, ToolDefinition
from app.chat.domain.exceptions import LLMProviderError
from app.chat.domain.interfaces import LLMProvider, ProviderResponse, StreamChunk
from app.chat.domain.models import ChatMessage, Usage

logger = logging.getLogger(__name__)


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
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> dict:
        contents = []
        system_instruction_content = ""

        for msg in messages:
            role_str = msg.role.value if isinstance(msg.role, Enum) else str(msg.role)
            if role_str == "system":
                system_instruction_content = msg.content
                continue

            # Map user/assistant/tool to Gemini roles
            parts = []
            if role_str == "tool":
                role = "tool"
                parts.append(
                    {
                        "functionResponse": {
                            "name": msg.name,
                            "response": {"result": msg.content},
                        }
                    }
                )
            elif role_str == "assistant" or role_str == "model":
                role = "model"
                if msg.content:
                    parts.append({"text": msg.content})
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        func_call = tc.get("function", {}) if "function" in tc else tc
                        args = func_call.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except ValueError:
                                pass
                        parts.append(
                            {
                                "functionCall": {
                                    "name": func_call.get("name"),
                                    "args": args,
                                }
                            }
                        )
            else:
                role = "user"
                parts.append({"text": msg.content})

            contents.append({"role": role, "parts": parts})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        if system_instruction_content:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction_content}]
            }

        if tools:
            function_declarations = []
            for t in tools:
                function_declarations.append(
                    {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    }
                )
            payload["tools"] = [{"functionDeclarations": function_declarations}]

            if tool_choice:
                mode = "AUTO"
                if tool_choice == "none":
                    mode = "NONE"
                elif tool_choice == "any":
                    mode = "ANY"
                payload["toolConfig"] = {"functionCallingConfig": {"mode": mode}}

        return payload

    async def generate(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> ProviderResponse:
        if not self.api_key:
            raise LLMProviderError("Gemini API key is missing or not configured.")

        url = self._get_url(model, stream=False)
        payload = self._build_payload(
            messages, temperature, max_tokens, tools, tool_choice
        )
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

                candidates = data.get("candidates", [])
                if not candidates:
                    raise LLMProviderError(
                        "No generation candidates returned from Gemini."
                    )

                content = ""
                tool_calls = []
                parts = candidates[0].get("content", {}).get("parts", [])
                for part in parts:
                    if "text" in part:
                        content += part["text"]
                    if "functionCall" in part:
                        fc = part["functionCall"]
                        tc_id = f"call_{fc['name']}_{uuid.uuid4().hex[:8]}"
                        tool_calls.append(
                            ToolCall(
                                id=tc_id,
                                name=fc["name"],
                                arguments=fc.get("args") or {},
                            )
                        )

                usage_data = data.get("usageMetadata", {})
                usage = Usage(
                    prompt_tokens=usage_data.get("promptTokenCount", 0),
                    completion_tokens=usage_data.get("candidatesTokenCount", 0),
                    total_tokens=usage_data.get("totalTokenCount", 0),
                )
                return ProviderResponse(
                    content=content, usage=usage, tool_calls=tool_calls
                )
        except httpx.HTTPStatusError as e:
            raise LLMProviderError(
                f"Gemini API returned status {e.response.status_code}: {e.response.text}"
            )
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
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        if not self.api_key:
            raise LLMProviderError("Gemini API key is missing or not configured.")

        url = self._get_url(model, stream=True)
        payload = self._build_payload(
            messages, temperature, max_tokens, tools, tool_choice
        )
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
                            data_str = line[len("data: ") :].strip()
                            data = json.loads(data_str)

                            candidates = data.get("candidates", [])
                            delta_content = ""
                            tool_calls = []
                            if candidates:
                                parts = (
                                    candidates[0].get("content", {}).get("parts", [])
                                )
                                for part in parts:
                                    if "text" in part:
                                        delta_content = part["text"]
                                    if "functionCall" in part:
                                        fc = part["functionCall"]
                                        tc_id = (
                                            f"call_{fc['name']}_{uuid.uuid4().hex[:8]}"
                                        )
                                        tool_calls.append(
                                            ToolCall(
                                                id=tc_id,
                                                name=fc["name"],
                                                arguments=fc.get("args") or {},
                                            )
                                        )

                            usage_data = data.get("usageMetadata", None)
                            usage = None
                            if usage_data:
                                usage = Usage(
                                    prompt_tokens=usage_data.get("promptTokenCount", 0),
                                    completion_tokens=usage_data.get(
                                        "candidatesTokenCount", 0
                                    ),
                                    total_tokens=usage_data.get("totalTokenCount", 0),
                                )

                            if delta_content or tool_calls or usage:
                                yield StreamChunk(
                                    text_delta=delta_content,
                                    usage=usage,
                                    tool_calls=tool_calls,
                                )
        except httpx.HTTPStatusError as e:
            raise LLMProviderError(
                f"Gemini API returned status {e.response.status_code}: {e.response.text}"
            )
        except httpx.RequestError as e:
            raise LLMProviderError(f"Gemini network request failed: {e}")
        except json.JSONDecodeError as e:
            raise LLMProviderError(f"Failed to decode stream line: {e}")
        except Exception as e:
            raise LLMProviderError(f"Streaming failed: {e}")

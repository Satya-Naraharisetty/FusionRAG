import json
import logging
from typing import AsyncIterator
from enum import Enum

import httpx

from app.chat.domain.exceptions import LLMProviderError
from app.chat.domain.interfaces import LLMProvider, ProviderResponse, StreamChunk
from app.chat.domain.models import ChatMessage, Usage
from app.chat.domain.agents import ToolDefinition, ToolCall


logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.url = "https://api.openai.com/v1/chat/completions"

    def _build_payload(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
        stream: bool = False,
    ) -> dict:
        formatted_messages = []
        for msg in messages:
            role_str = msg.role.value if isinstance(msg.role, Enum) else str(msg.role)
            entry = {"role": role_str}
            if msg.content is not None:
                entry["content"] = msg.content
            if msg.tool_calls:
                entry["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            if msg.name:
                entry["name"] = msg.name
            formatted_messages.append(entry)

        payload = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
            if tool_choice:
                payload["tool_choice"] = tool_choice

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
            raise LLMProviderError("OpenAI API key is missing or not configured.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = self._build_payload(
            messages, model, temperature, max_tokens, tools, tool_choice, stream=False
        )

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

                message = data["choices"][0]["message"]
                content = message.get("content")
                raw_tc = message.get("tool_calls", [])
                tool_calls = []

                for tc in raw_tc:
                    if tc.get("type") == "function":
                        fn = tc["function"]
                        try:
                            arguments = json.loads(fn["arguments"])
                        except ValueError:
                            arguments = {"raw_value": fn["arguments"]}
                        tool_calls.append(
                            ToolCall(
                                id=tc["id"],
                                name=fn["name"],
                                arguments=arguments,
                            )
                        )

                usage_data = data.get("usage", {})
                usage = Usage(
                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                    completion_tokens=usage_data.get("completion_tokens", 0),
                    total_tokens=usage_data.get("total_tokens", 0),
                )
                return ProviderResponse(content=content, usage=usage, tool_calls=tool_calls)
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
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        if not self.api_key:
            raise LLMProviderError("OpenAI API key is missing or not configured.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = self._build_payload(
            messages, model, temperature, max_tokens, tools, tool_choice, stream=True
        )
        payload["stream_options"] = {"include_usage": True}

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
                        await response.aread()
                        raise LLMProviderError(
                            f"OpenAI API returned status {response.status_code}: {response.text}"
                        )

                    accumulated_tcs = {}
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        if line == "data: [DONE]":
                            break
                        if line.startswith("data: "):
                            data_str = line[len("data: "):].strip()
                            data = json.loads(data_str)

                            usage_data = data.get("usage", None)
                            usage = None
                            if usage_data:
                                usage = Usage(
                                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                                    completion_tokens=usage_data.get("completion_tokens", 0),
                                    total_tokens=usage_data.get("total_tokens", 0),
                                )

                            choices = data.get("choices", [])
                            delta_content = ""
                            tool_calls = []
                            if choices:
                                delta = choices[0].get("delta", {})
                                delta_content = delta.get("content", "")

                                delta_tcs = delta.get("tool_calls", [])
                                for dtc in delta_tcs:
                                    idx = dtc["index"]
                                    if idx not in accumulated_tcs:
                                        accumulated_tcs[idx] = {
                                            "id": dtc.get("id", ""),
                                            "name": dtc.get("function", {}).get("name", ""),
                                            "arguments": [],
                                        }

                                    if dtc.get("id"):
                                        accumulated_tcs[idx]["id"] = dtc["id"]
                                    if dtc.get("function", {}).get("name"):
                                        accumulated_tcs[idx]["name"] = dtc["function"]["name"]
                                    if dtc.get("function", {}).get("arguments"):
                                        accumulated_tcs[idx]["arguments"].append(dtc["function"]["arguments"])

                                    arg_chunk = dtc.get("function", {}).get("arguments", "")
                                    tool_calls.append(
                                        ToolCall(
                                            id=accumulated_tcs[idx]["id"],
                                            name=accumulated_tcs[idx]["name"],
                                            arguments={"delta": arg_chunk},
                                        )
                                    )

                            if delta_content or tool_calls or usage:
                                yield StreamChunk(text_delta=delta_content, usage=usage, tool_calls=tool_calls)
        except httpx.HTTPStatusError as e:
            raise LLMProviderError(f"OpenAI API returned status {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            raise LLMProviderError(f"OpenAI network request failed: {e}")
        except json.JSONDecodeError as e:
            raise LLMProviderError(f"Failed to decode stream line: {e}")
        except Exception as e:
            raise LLMProviderError(f"Streaming failed: {e}")

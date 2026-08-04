import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

from app.chat.domain.agents import (
    AgentIteration,
    AgentResponse,
    AgentState,
    ToolCall,
    ToolContext,
    ToolResult,
)
from app.chat.domain.exceptions import AgentIterationLimitExceeded
from app.chat.domain.interfaces import LLMProvider, TokenEstimator
from app.chat.domain.models import (
    ChatMessage,
    ChatRole,
    ConversationMessage,
    MessageRole,
    MessageStatus,
    Usage,
)
from app.chat.services.tool_executor import ToolExecutor
from app.chat.services.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentExecutor:
    def __init__(
        self,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        conversation_manager: Any,
        token_estimator: TokenEstimator,
        max_iterations: int = 5,
        max_tools_per_request: int = 10,
    ) -> None:
        self.llm_provider = llm_provider
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.conversation_manager = conversation_manager
        self.token_estimator = token_estimator
        self.max_iterations = max_iterations
        self.max_tools_per_request = max_tools_per_request

    async def execute_single_tool(
        self, tc: ToolCall, context: ToolContext
    ) -> ToolResult:
        tool_start = time.perf_counter()
        try:
            tool = self.tool_registry.get(tc.name)
            result = await self.tool_executor.execute(tool, tc.arguments, context)
            result.tool_call_id = tc.id
        except Exception as e:
            result = ToolResult(
                tool_call_id=tc.id,
                name=tc.name,
                content=f"Execution error: {e}",
                is_error=True,
            )
        result.execution_time_ms = (time.perf_counter() - tool_start) * 1000
        return result

    async def execute_single_tool_with_events(
        self,
        tc: ToolCall,
        context: ToolContext,
        event_callback: Callable[[str, dict], Coroutine[Any, Any, None]],
    ) -> ToolResult:
        await event_callback(
            "tool_call_started",
            {"id": tc.id, "name": tc.name, "arguments": tc.arguments},
        )
        result = await self.execute_single_tool(tc, context)
        await event_callback(
            "tool_call_finished",
            {
                "id": tc.id,
                "name": tc.name,
                "execution_time_ms": result.execution_time_ms,
            },
        )
        await event_callback(
            "tool_result",
            {
                "id": tc.id,
                "name": tc.name,
                "result": result.content,
                "is_error": result.is_error,
            },
        )
        return result

    async def execute(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        context: ToolContext,
    ) -> AgentResponse:
        iterations = []
        step = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        start_time = time.perf_counter()

        current_messages = list(messages)

        while step < self.max_iterations:
            step += 1
            step_start = time.perf_counter()

            # State transition to THINKING
            iteration = AgentIteration(
                step=step,
                state=AgentState.THINKING,
                timestamp=datetime.now(UTC),
            )

            tools = [tool.definition for tool in self.tool_registry.list_tools()]

            response = await self.llm_provider.generate(
                messages=current_messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
            )
            from app.chat.domain.interfaces import ProviderResponse

            if isinstance(response, tuple) and not hasattr(response, "tool_calls"):
                response = ProviderResponse(content=response[0], usage=response[1])

            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            total_prompt_tokens += prompt_tokens
            total_completion_tokens += completion_tokens

            tool_calls = response.tool_calls
            iteration.tool_calls = tool_calls
            iteration.assistant_response = response.content
            iteration.thought_tokens = completion_tokens
            iteration.provider_latency = (time.perf_counter() - step_start) * 1000

            # If model returned text, add to context
            if response.content:
                current_messages.append(
                    ChatMessage(role=ChatRole.ASSISTANT, content=response.content)
                )

            # If no tool calls, loop ends
            if not tool_calls:
                iteration.state = AgentState.FINISHED
                iterations.append(iteration)
                break

            if len(tool_calls) > self.max_tools_per_request:
                raise ValueError(
                    f"Too many tool calls requested: {len(tool_calls)}. "
                    f"Max limit is {self.max_tools_per_request}."
                )

            iteration.state = AgentState.CALLING_TOOL

            # Persist assistant message with tool calls to database
            assistant_msg_id = uuid.uuid4()
            await self.conversation_manager._message_repo.add_message(
                ConversationMessage(
                    id=assistant_msg_id,
                    conversation_id=context.conversation_id,
                    role=MessageRole.ASSISTANT,
                    content=response.content or "",
                    status=MessageStatus.COMPLETED,
                    tool_calls=[
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.arguments},
                        }
                        for tc in tool_calls
                    ],
                    created_at=datetime.now(UTC),
                )
            )

            # Keep trace in current message history
            current_messages.append(
                ChatMessage(
                    role=ChatRole.ASSISTANT,
                    content=response.content,
                    tool_calls=[
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.arguments},
                        }
                        for tc in tool_calls
                    ],
                )
            )

            # Execute tools in parallel using asyncio.gather
            iteration.state = AgentState.WAITING_TOOL
            tool_start_time = time.perf_counter()

            results = await asyncio.gather(
                *(self.execute_single_tool(tc, context) for tc in tool_calls)
            )

            iteration.tool_latency = (time.perf_counter() - tool_start_time) * 1000
            iteration.tool_results = results
            iteration.state = AgentState.OBSERVING_RESULT

            # Persist tool outcomes and append to message context
            for result in results:
                await self.conversation_manager._message_repo.add_message(
                    ConversationMessage(
                        id=uuid.uuid4(),
                        conversation_id=context.conversation_id,
                        role=MessageRole.TOOL,
                        content=result.content,
                        status=MessageStatus.COMPLETED,
                        metadata={
                            "tool_call_id": result.tool_call_id,
                            "name": result.name,
                            "is_error": result.is_error,
                            "execution_time_ms": result.execution_time_ms,
                        },
                        created_at=datetime.now(UTC),
                    )
                )

                current_messages.append(
                    ChatMessage(
                        role=MessageRole.TOOL,
                        content=result.content,
                        tool_call_id=result.tool_call_id,
                        name=result.name,
                    )
                )

            iterations.append(iteration)
        else:
            raise AgentIterationLimitExceeded(
                f"Agent exceeded maximum reasoning iterations ({self.max_iterations})."
            )

        total_time_ms = (time.perf_counter() - start_time) * 1000
        final_answer = iterations[-1].assistant_response or ""

        return AgentResponse(
            answer=final_answer,
            iterations=iterations,
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
            total_time_ms=total_time_ms,
            model=model,
        )

    async def execute_stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        context: ToolContext,
    ) -> AsyncIterator[dict]:
        step = 0
        current_messages = list(messages)
        start_time = time.perf_counter()
        total_prompt_tokens = 0
        total_completion_tokens = 0
        iterations = []

        while step < self.max_iterations:
            step += 1
            step_start = time.perf_counter()

            # State transition to THINKING
            iteration = AgentIteration(
                step=step,
                state=AgentState.THINKING,
                timestamp=datetime.now(UTC),
            )

            # Format and list registered tools
            tools = [tool.definition for tool in self.tool_registry.list_tools()]

            accumulated_text = []
            accumulated_tool_calls = {}
            final_usage = None

            # Stream from provider
            async for chunk in self.llm_provider.stream(
                messages=current_messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
            ):
                from app.chat.domain.interfaces import StreamChunk

                if isinstance(chunk, tuple) and not hasattr(chunk, "text_delta"):
                    chunk = StreamChunk(text_delta=chunk[0], usage=chunk[1])
                text_delta = chunk.text_delta
                if text_delta:
                    accumulated_text.append(text_delta)
                    # Yield incremental text
                    yield {"event": "text", "data": {"text": text_delta}}

                # Accumulate partial tool calls
                if chunk.tool_calls:
                    for tc in chunk.tool_calls:
                        if tc.id not in accumulated_tool_calls:
                            accumulated_tool_calls[tc.id] = {
                                "id": tc.id,
                                "name": tc.name,
                                "arguments_str": "",
                            }
                        if tc.arguments and "delta" in tc.arguments:
                            accumulated_tool_calls[tc.id]["arguments_str"] += (
                                tc.arguments["delta"]
                            )

                if chunk.usage:
                    final_usage = chunk.usage

            full_text = "".join(accumulated_text)

            # Reconstruct complete parameters dictionary for tool calls
            tool_calls = []
            for tc_id, tc_data in accumulated_tool_calls.items():
                args_str = tc_data["arguments_str"].strip()
                try:
                    args = json.loads(args_str) if args_str else {}
                except ValueError:
                    args = {"raw_value": args_str}
                tool_calls.append(
                    ToolCall(id=tc_id, name=tc_data["name"], arguments=args)
                )

            # Estimate tokens if not returned by stream
            if not final_usage:
                prompt_tokens_est = self.token_estimator.estimate(str(current_messages))
                completion_tokens_est = self.token_estimator.estimate(full_text)
                final_usage = Usage(
                    prompt_tokens=prompt_tokens_est,
                    completion_tokens=completion_tokens_est,
                    total_tokens=prompt_tokens_est + completion_tokens_est,
                )

            total_prompt_tokens += final_usage.prompt_tokens
            total_completion_tokens += final_usage.completion_tokens

            iteration.tool_calls = tool_calls
            iteration.assistant_response = full_text
            iteration.thought_tokens = final_usage.completion_tokens
            iteration.provider_latency = (time.perf_counter() - step_start) * 1000

            if full_text:
                current_messages.append(
                    ChatMessage(role=ChatRole.ASSISTANT, content=full_text)
                )

            # If no tools, finish loop
            if not tool_calls:
                iteration.state = AgentState.FINISHED
                iterations.append(iteration)
                break

            if len(tool_calls) > self.max_tools_per_request:
                yield {
                    "event": "error",
                    "data": {
                        "code": "LIMIT_EXCEEDED",
                        "message": f"Too many tool calls requested: {len(tool_calls)}",
                    },
                }
                return

            iteration.state = AgentState.CALLING_TOOL

            # Persist intermediate assistant tool call message
            assistant_msg_id = uuid.uuid4()
            await self.conversation_manager._message_repo.add_message(
                ConversationMessage(
                    id=assistant_msg_id,
                    conversation_id=context.conversation_id,
                    role=MessageRole.ASSISTANT,
                    content=full_text,
                    status=MessageStatus.COMPLETED,
                    tool_calls=[
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.arguments},
                        }
                        for tc in tool_calls
                    ],
                    created_at=datetime.now(UTC),
                )
            )

            current_messages.append(
                ChatMessage(
                    role=ChatRole.ASSISTANT,
                    content=full_text,
                    tool_calls=[
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.arguments},
                        }
                        for tc in tool_calls
                    ],
                )
            )

            # Execute tool calls concurrently using asyncio.gather with callback events
            iteration.state = AgentState.WAITING_TOOL
            tool_start_time = time.perf_counter()

            async def send_event(ev: str, payload: dict):
                # Yield SSE-compatible event representation
                # We wrap it in a dictionary to let ChatOrchestrator handle the yielding
                pass

            # Define a thread-safe callback generator
            queue = asyncio.Queue()

            async def event_callback(event_type: str, event_data: dict):
                await queue.put({"event": event_type, "data": event_data})

            async def gather_tools():
                results = await asyncio.gather(
                    *(
                        self.execute_single_tool_with_events(
                            tc, context, event_callback
                        )
                        for tc in tool_calls
                    )
                )
                await queue.put(None)  # Sentinel to end queue reading
                return results

            # Run gather_tools concurrently with reading events from queue
            gather_task = asyncio.create_task(gather_tools())

            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item

            results = await gather_task

            iteration.tool_latency = (time.perf_counter() - tool_start_time) * 1000
            iteration.tool_results = results
            iteration.state = AgentState.OBSERVING_RESULT

            # Persist outcomes and append to message context
            for result in results:
                await self.conversation_manager._message_repo.add_message(
                    ConversationMessage(
                        id=uuid.uuid4(),
                        conversation_id=context.conversation_id,
                        role=MessageRole.TOOL,
                        content=result.content,
                        status=MessageStatus.COMPLETED,
                        metadata={
                            "tool_call_id": result.tool_call_id,
                            "name": result.name,
                            "is_error": result.is_error,
                            "execution_time_ms": result.execution_time_ms,
                        },
                        created_at=datetime.now(UTC),
                    )
                )

                current_messages.append(
                    ChatMessage(
                        role=MessageRole.TOOL,
                        content=result.content,
                        tool_call_id=result.tool_call_id,
                        name=result.name,
                    )
                )

            iterations.append(iteration)

        else:
            yield {
                "event": "error",
                "data": {
                    "code": "ITERATION_LIMIT",
                    "message": f"Agent exceeded maximum iterations: {self.max_iterations}",
                },
            }
            return

        total_time_ms = (time.perf_counter() - start_time) * 1000
        final_answer = iterations[-1].assistant_response or ""

        # Yield completion payload conforming to AnswerResponse format
        yield {
            "event": "done",
            "data": {
                "answer": final_answer,
                "citations": [],
                "generation_time_ms": round(total_time_ms, 2),
                "total_time_ms": round(total_time_ms, 2),
                "model": model,
                "usage": {
                    "prompt_tokens": total_prompt_tokens,
                    "completion_tokens": total_completion_tokens,
                    "total_tokens": total_prompt_tokens + total_completion_tokens,
                },
                "conversation_id": str(context.conversation_id),
                "iterations": [iter_obj.model_dump() for iter_obj in iterations],
            },
        }

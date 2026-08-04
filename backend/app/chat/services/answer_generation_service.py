import warnings
from typing import Any

from app.chat.services.agent_executor import AgentExecutor
from app.chat.services.chat_orchestrator import ChatOrchestrator
from app.chat.services.llm_generation_service import LLMGenerationService
from app.chat.services.tool_executor import ToolExecutor
from app.chat.services.tool_registry import ToolRegistry


class AnswerGenerationService(ChatOrchestrator):
    def __init__(
        self,
        retrieval_service: Any,
        prompt_builder: Any,
        llm_provider: Any,
        token_estimator: Any,
        conversation_manager: Any,
        context_builder: Any,
        model: str,
        temperature: float,
        max_response_tokens: int,
        system_prompt_tokens_limit: int,
        max_context_tokens: int,
        reserved_completion_tokens: int,
        max_memory_tokens: int = 3000,
        enable_conversation_memory: bool = True,
    ) -> None:
        warnings.warn(
            "AnswerGenerationService is deprecated. Use ChatOrchestrator instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        llm_gen = LLMGenerationService(llm_provider)
        registry = ToolRegistry([])
        executor = ToolExecutor()
        agent_exec = AgentExecutor(
            llm_provider=llm_provider,
            tool_registry=registry,
            tool_executor=executor,
            conversation_manager=conversation_manager,
            token_estimator=token_estimator,
        )

        super().__init__(
            retrieval_service=retrieval_service,
            prompt_builder=prompt_builder,
            llm_generation_service=llm_gen,
            token_estimator=token_estimator,
            conversation_manager=conversation_manager,
            context_builder=context_builder,
            agent_executor=agent_exec,
            model=model,
            temperature=temperature,
            max_response_tokens=max_response_tokens,
            system_prompt_tokens_limit=system_prompt_tokens_limit,
            max_context_tokens=max_context_tokens,
            reserved_completion_tokens=reserved_completion_tokens,
            max_memory_tokens=max_memory_tokens,
            enable_conversation_memory=enable_conversation_memory,
            enable_tool_calling=False,  # Legacy code disables tools by default
        )

from abc import ABC, abstractmethod

from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentResult,
    AgentTask,
    AgentType,
)


class BaseSpecialistAgent(ABC):
    @property
    @abstractmethod
    def agent_type(self) -> AgentType:
        """The specialist type this agent implements."""
        pass

    @abstractmethod
    async def execute_task(
        self,
        task: AgentTask,
        context: AgentExecutionContext,
    ) -> AgentResult:
        """Execute a bounded specialist task within the given execution context."""
        pass

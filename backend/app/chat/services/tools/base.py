from abc import ABC, abstractmethod
from typing import Any

from app.chat.domain.agents import (
    ToolCategory,
    ToolContext,
    ToolDefinition,
    ToolPermission,
    ToolResult,
)


class Tool(ABC):
    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Get the schema definition of the tool."""
        pass

    @property
    @abstractmethod
    def category(self) -> ToolCategory:
        """Get the classification of this tool."""
        pass

    @property
    @abstractmethod
    def required_permission(self) -> ToolPermission:
        """Get the permission required to run this tool."""
        pass

    @abstractmethod
    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
        cancellation_token: Any | None = None,
    ) -> ToolResult:
        """Execute the tool's business logic."""
        pass


class BuiltinTool(Tool, ABC):
    """Base class for native in-app tools."""
    pass


class ExternalTool(Tool, ABC):
    """Base class for future remote plugins and Model Context Protocol (MCP) tools."""
    pass

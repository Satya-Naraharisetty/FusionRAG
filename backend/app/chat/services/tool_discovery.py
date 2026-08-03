from app.chat.domain.agents import ToolDefinition
from app.chat.services.tool_registry import ToolRegistry


class ToolDiscoveryService:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def get_available_tools(self) -> list[ToolDefinition]:
        """
        Retrieve definitions of all available unique tools for schema exposition.
        """
        return [tool.definition for tool in self.registry.list_tools()]

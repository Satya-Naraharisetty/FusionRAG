from app.chat.domain.exceptions import ToolNotFoundError
from app.chat.services.tools.base import Tool


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        if tools:
            for tool in tools:
                self.register(tool)

    def register(self, tool: Tool, aliases: list[str] | None = None) -> None:
        name = tool.definition.name.lower()
        self._tools[name] = tool
        if aliases:
            for alias in aliases:
                self._tools[alias.lower()] = tool

    def get(self, name: str) -> Tool:
        key = name.lower()
        if key not in self._tools:
            raise ToolNotFoundError(f"Tool '{name}' was not found in the registry.")
        return self._tools[key]

    def list_tools(self) -> list[Tool]:
        # Return unique tools (avoid duplicates from aliases)
        seen = set()
        unique_tools = []
        for tool in self._tools.values():
            if tool not in seen:
                seen.add(tool)
                unique_tools.append(tool)
        return unique_tools

from datetime import datetime
from typing import Any

from app.chat.domain.agents import (
    ToolCategory,
    ToolDefinition,
    ToolPermission,
    ToolResult,
    ToolContext,
)
from app.chat.services.tools.base import BuiltinTool


class DateTimeTool(BuiltinTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_current_datetime",
            description="Get the current date and time in ISO format.",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.UTILITY

    @property
    def required_permission(self) -> ToolPermission:
        return ToolPermission.READ

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
        cancellation_token: Any | None = None,
    ) -> ToolResult:
        now_str = datetime.utcnow().isoformat()
        return ToolResult(
            tool_call_id="",
            name=self.definition.name,
            content=now_str,
            structured_output={"datetime": now_str},
            is_error=False,
        )

from typing import Any

from app.chat.domain.agents import (
    ToolCategory,
    ToolContext,
    ToolDefinition,
    ToolPermission,
    ToolResult,
)
from app.chat.services.tools.base import BuiltinTool
from app.chat.services.web_search_service import WebSearchService


class WebSearchTool(BuiltinTool):
    """
    Tool allowing single-agent ReAct workflows to perform real-time web searches.
    """

    def __init__(self, web_search_service: WebSearchService | None = None) -> None:
        self.web_search_service = web_search_service or WebSearchService()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web_search",
            description=(
                "Search the public internet for up-to-date information, real-time facts, "
                "current news, online articles, or external data."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to look up on the web.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of search results to return (default: 5).",
                    },
                },
                "required": ["query"],
            },
        )

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.KNOWLEDGE

    @property
    def required_permission(self) -> ToolPermission:
        return ToolPermission.READ

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
        cancellation_token: Any | None = None,
    ) -> ToolResult:
        query = str(arguments.get("query", "")).strip()
        max_results = int(arguments.get("max_results") or 5)

        if not query:
            return ToolResult(
                tool_call_id="",
                name=self.definition.name,
                content="Error: Search query cannot be empty.",
                is_error=True,
            )

        try:
            results = await self.web_search_service.search(
                query=query, max_results=max_results
            )
            if not results:
                return ToolResult(
                    tool_call_id="",
                    name=self.definition.name,
                    content=f"No web results found for '{query}'.",
                    structured_output={"results": []},
                    is_error=False,
                )

            formatted = []
            structured = []
            for idx, r in enumerate(results, 1):
                formatted.append(
                    f"{idx}. {r.title}\nURL: {r.url}\nSnippet: {r.snippet}"
                )
                structured.append(r.model_dump())

            return ToolResult(
                tool_call_id="",
                name=self.definition.name,
                content="\n\n".join(formatted),
                structured_output={"results": structured},
                metadata={"results_count": len(results)},
                is_error=False,
            )
        except Exception as e:
            return ToolResult(
                tool_call_id="",
                name=self.definition.name,
                content=f"Web search error: {e}",
                is_error=True,
            )

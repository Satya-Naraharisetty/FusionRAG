import asyncio
import json
import logging
import time
from typing import Any

from app.chat.domain.agents import ToolContext, ToolResult
from app.chat.domain.exceptions import ToolValidationError
from app.chat.services.tools.base import Tool

logger = logging.getLogger(__name__)


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> None:
    """
    Validate tool arguments against its JSON Schema definition.
    """
    # 1. Check required parameters
    required = schema.get("required", [])
    for field in required:
        if field not in arguments:
            raise ToolValidationError(f"Missing required parameter: {field}")

    # 2. Check parameter types
    properties = schema.get("properties", {})
    for field, val in arguments.items():
        if field not in properties:
            raise ToolValidationError(f"Unknown parameter provided: {field}")

        prop_schema = properties[field]
        expected_type = prop_schema.get("type")

        if val is None:
            continue

        if expected_type == "string":
            if not isinstance(val, str):
                raise ToolValidationError(
                    f"Parameter '{field}' must be a string, got {type(val).__name__}."
                )
            if prop_schema.get("format") == "uuid":
                import uuid
                try:
                    uuid.UUID(val)
                except ValueError:
                    raise ToolValidationError(
                        f"Parameter '{field}' must be a valid UUID, got '{val}'."
                    )
        elif expected_type in ("number", "integer"):
            if expected_type == "integer" and not isinstance(val, int) and not (isinstance(val, float) and val.is_integer()):
                raise ToolValidationError(
                    f"Parameter '{field}' must be an integer, got {type(val).__name__}."
                )
            if not isinstance(val, (int, float)):
                raise ToolValidationError(
                    f"Parameter '{field}' must be a number, got {type(val).__name__}."
                )
        elif expected_type == "boolean":
            if not isinstance(val, bool):
                raise ToolValidationError(
                    f"Parameter '{field}' must be a boolean, got {type(val).__name__}."
                )
        elif expected_type == "array":
            if not isinstance(val, list):
                raise ToolValidationError(
                    f"Parameter '{field}' must be a list, got {type(val).__name__}."
                )
            item_schema = prop_schema.get("items", {})
            item_type = item_schema.get("type")
            if item_type:
                for idx, item in enumerate(val):
                    if item_type == "string":
                        if not isinstance(item, str):
                            raise ToolValidationError(
                                f"Item at index {idx} in array '{field}' must be a string."
                            )
                        if item_schema.get("format") == "uuid":
                            import uuid
                            try:
                                uuid.UUID(item)
                            except ValueError:
                                raise ToolValidationError(
                                    f"Item at index {idx} in array '{field}' must be a valid UUID."
                                )


def serialize_and_truncate(data: Any, limit: int) -> str:
    """
    Serializes output to a JSON string or text, safely truncating to prevent
    exceeding size limits without corrupting JSON structures where possible.
    """
    if isinstance(data, str):
        if len(data) <= limit:
            return data
        try:
            parsed = json.loads(data)
            return serialize_and_truncate(parsed, limit)
        except Exception:
            return data[:limit] + "\n... [Result truncated cleanly to fit limit]"

    try:
        raw_json = json.dumps(data)
    except Exception:
        raw_json = str(data)

    if len(raw_json) <= limit:
        return raw_json

    if isinstance(data, list):
        for i in range(len(data) - 1, 0, -1):
            subset = data[:i]
            subset_json = json.dumps(
                {
                    "data": subset,
                    "warning": f"Result truncated. Kept {i} of {len(data)} items.",
                }
            )
            if len(subset_json) <= limit:
                return subset_json
    elif isinstance(data, dict):
        truncated_dict = {}
        for k, v in data.items():
            if isinstance(v, str) and len(v) > 1000:
                truncated_dict[k] = v[:1000] + "... [Field truncated]"
            else:
                truncated_dict[k] = v
        subset_json = json.dumps(truncated_dict)
        if len(subset_json) <= limit:
            return subset_json

    return raw_json[:limit] + "\n... [Result truncated cleanly to fit limit]"


class ToolExecutor:
    def __init__(
        self,
        timeout: float = 30.0,
        result_size_limit: int = 50000,
        auto_retry_count: int = 1,
    ) -> None:
        self.timeout = timeout
        self.result_size_limit = result_size_limit
        self.auto_retry_count = auto_retry_count

    async def execute(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        context: ToolContext,
        cancellation_token: Any | None = None,
    ) -> ToolResult:
        # 1. Validate JSON schema arguments
        try:
            validate_arguments(tool.definition.parameters, arguments)
        except ToolValidationError as e:
            return ToolResult(
                tool_call_id="",
                name=tool.definition.name,
                content=f"Validation Error: {e}",
                is_error=True,
            )

        start_time = time.perf_counter()
        retries = self.auto_retry_count

        while True:
            try:
                # 2. Execute with timeout
                async with asyncio.timeout(self.timeout):
                    result = await tool.execute(
                        arguments=arguments,
                        context=context,
                        cancellation_token=cancellation_token,
                    )

                # 3. Truncate output safely
                result.content = serialize_and_truncate(
                    result.content, self.result_size_limit
                )
                result.execution_time_ms = (time.perf_counter() - start_time) * 1000
                return result

            except TimeoutError:
                if retries > 0:
                    retries -= 1
                    logger.warning(
                        f"Tool '{tool.definition.name}' timed out. Retrying..."
                    )
                    continue
                latency_ms = (time.perf_counter() - start_time) * 1000
                return ToolResult(
                    tool_call_id="",
                    name=tool.definition.name,
                    content=f"Timeout Error: Execution exceeded limit of {self.timeout}s.",
                    is_error=True,
                    execution_time_ms=latency_ms,
                )
            except Exception as e:
                if retries > 0:
                    retries -= 1
                    logger.warning(
                        f"Tool '{tool.definition.name}' failed with error: {e}. Retrying..."
                    )
                    continue
                latency_ms = (time.perf_counter() - start_time) * 1000
                return ToolResult(
                    tool_call_id="",
                    name=tool.definition.name,
                    content=f"Execution Error: {e}",
                    is_error=True,
                    execution_time_ms=latency_ms,
                )

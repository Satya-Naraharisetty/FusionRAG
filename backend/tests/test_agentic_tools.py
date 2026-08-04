import asyncio
import time
import uuid

import pytest
from app.chat.domain.agents import (
    AgentState,
    ToolCall,
    ToolCategory,
    ToolContext,
    ToolDefinition,
    ToolPermission,
    ToolResult,
)
from app.chat.domain.exceptions import (
    ToolNotFoundError,
    ToolValidationError,
)
from app.chat.domain.models import ChatMessage, ChatRole, Usage
from app.chat.services.agent_executor import AgentExecutor
from app.chat.services.tool_discovery import ToolDiscoveryService
from app.chat.services.tool_executor import ToolExecutor, validate_arguments
from app.chat.services.tool_registry import ToolRegistry
from app.chat.services.tools.base import BuiltinTool
from app.chat.services.tools.calculator import CalculatorTool, SafeCalculator

# --- 1. AST Calculator Tests ---

def test_safe_calculator_valid():
    calc = SafeCalculator()
    assert calc.evaluate("1 + 1") == 2
    assert calc.evaluate("15 * 2 + 10") == 40
    assert calc.evaluate("(10 - 2) * 5") == 40
    assert calc.evaluate("2 ** 3") == 8
    assert calc.evaluate("10 // 3") == 3
    assert calc.evaluate("10 % 3") == 1
    assert calc.evaluate("-5 + 10") == 5


def test_safe_calculator_invalid_syntax():
    calc = SafeCalculator()
    with pytest.raises(ValueError, match="Invalid math syntax"):
        calc.evaluate("1 + +")


def test_safe_calculator_malicious_code():
    calc = SafeCalculator()
    # Reject system commands / imports / variable assignments
    with pytest.raises(ValueError):
        calc.evaluate("import os")
    with pytest.raises(ValueError):
        calc.evaluate("os.system('ls')")
    with pytest.raises(ValueError):
        calc.evaluate("x = 5")
    with pytest.raises(ValueError):
        calc.evaluate("__import__('sys').exit()")


def test_safe_calculator_overflow_prevention():
    calc = SafeCalculator()
    with pytest.raises(ValueError, match="Exponent too large"):
        calc.evaluate("2 ** 1001")


# --- 2. Schema Validation Tests ---

def test_validate_arguments_success():
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
            "active": {"type": "boolean"},
            "ids": {
                "type": "array",
                "items": {"type": "string", "format": "uuid"}
            }
        },
        "required": ["query"]
    }
    
    # Valid arguments
    args = {
        "query": "test query",
        "limit": 10,
        "active": True,
        "ids": [str(uuid.uuid4())]
    }
    validate_arguments(schema, args)


def test_validate_arguments_missing_required():
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"]
    }
    with pytest.raises(ToolValidationError, match="Missing required parameter"):
        validate_arguments(schema, {})


def test_validate_arguments_invalid_types():
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"}
        }
    }
    with pytest.raises(ToolValidationError, match="must be a string"):
        validate_arguments(schema, {"query": 123})
        
    with pytest.raises(ToolValidationError, match="must be an integer"):
        validate_arguments(schema, {"limit": "not an int"})


def test_validate_arguments_invalid_uuid():
    schema = {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "format": "uuid"}
        }
    }
    with pytest.raises(ToolValidationError, match="must be a valid UUID"):
        validate_arguments(schema, {"doc_id": "not-a-uuid"})


# --- 3. Registry and Discovery Tests ---

class MockSimpleTool(BuiltinTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="mock_tool",
            description="A mock tool",
            parameters={"type": "object", "properties": {}}
        )

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.UTILITY

    @property
    def required_permission(self) -> ToolPermission:
        return ToolPermission.READ

    async def execute(self, arguments: dict, context: ToolContext, cancellation_token=None) -> ToolResult:
        return ToolResult(tool_call_id="", name="mock_tool", content="mock success")


def test_tool_registry_aliases():
    tool = MockSimpleTool()
    registry = ToolRegistry()
    registry.register(tool, aliases=["alias1", "alias2"])
    
    assert registry.get("mock_tool") == tool
    assert registry.get("alias1") == tool
    assert registry.get("alias2") == tool
    
    with pytest.raises(ToolNotFoundError):
        registry.get("unknown")


def test_tool_discovery():
    tool = MockSimpleTool()
    registry = ToolRegistry([tool])
    discovery = ToolDiscoveryService(registry)
    
    defs = discovery.get_available_tools()
    assert len(defs) == 1
    assert defs[0].name == "mock_tool"
    assert defs[0].description == "A mock tool"


# --- 4. ToolExecutor Concurrency and Timeout Tests ---

class LatencyTool(BuiltinTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="latency_tool",
            description="Sleeps",
            parameters={"type": "object", "properties": {"sleep_sec": {"type": "number"}}}
        )

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.UTILITY

    @property
    def required_permission(self) -> ToolPermission:
        return ToolPermission.READ

    async def execute(self, arguments: dict, context: ToolContext, cancellation_token=None) -> ToolResult:
        sleep_sec = arguments.get("sleep_sec", 0.1)
        await asyncio.sleep(sleep_sec)
        return ToolResult(tool_call_id="", name="latency_tool", content=f"slept {sleep_sec}")


@pytest.mark.asyncio
async def test_tool_executor_timeout():
    # Set tight timeout of 0.05 seconds
    executor = ToolExecutor(timeout=0.05, auto_retry_count=0)
    tool = LatencyTool()
    context = ToolContext(user_id=uuid.uuid4(), conversation_id=uuid.uuid4(), db_session=None)
    
    result = await executor.execute(tool, {"sleep_sec": 0.2}, context)
    assert result.is_error is True
    assert "Timeout Error" in result.content


@pytest.mark.asyncio
async def test_tool_executor_parallel_gather():
    tool1 = LatencyTool()
    tool2 = LatencyTool()
    
    # We want to verify they run in parallel.
    # Running two 0.2s sleeps in sequence takes >0.4s. In parallel, it takes ~0.2s.
    context = ToolContext(user_id=uuid.uuid4(), conversation_id=uuid.uuid4(), db_session=None)
    executor = ToolExecutor(timeout=1.0)
    
    start = time.perf_counter()
    await asyncio.gather(
        executor.execute(tool1, {"sleep_sec": 0.2}, context),
        executor.execute(tool2, {"sleep_sec": 0.2}, context)
    )
    duration = time.perf_counter() - start
    # Should be well below 0.4s if parallelized
    assert duration < 0.35


# --- 5. Agent Executor State Machine & Iteration Tests ---

class MockLLMProvider:
    def __init__(self, responses: list):
        self.responses = responses
        self.call_count = 0

    async def generate(self, messages, model, temperature, max_tokens, tools=None, tool_choice=None):
        from app.chat.domain.interfaces import ProviderResponse
        response_data = self.responses[self.call_count]
        self.call_count += 1
        
        return ProviderResponse(
            content=response_data.get("content"),
            usage=Usage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
            tool_calls=response_data.get("tool_calls")
        )


class MockMsgRepo:
    async def add_message(self, message):
        return message


class MockConvMgr:
    def __init__(self):
        self._message_repo = MockMsgRepo()


class DummyTokenEstimator:
    def estimate(self, text: str) -> int:
        return len(text) // 4


@pytest.mark.asyncio
async def test_agent_executor_loop_finished_state():
    # Scenario: LLM returns text response immediately (0 tools)
    llm = MockLLMProvider([{"content": "Hello user, I can answer without tools."}])
    registry = ToolRegistry()
    executor = ToolExecutor()
    conv_mgr = MockConvMgr()
    estimator = DummyTokenEstimator()
    
    agent = AgentExecutor(llm, registry, executor, conv_mgr, estimator)
    context = ToolContext(user_id=uuid.uuid4(), conversation_id=uuid.uuid4(), db_session=None)
    
    messages = [ChatMessage(role=ChatRole.USER, content="Hello")]
    resp = await agent.execute(messages, "model-x", 0.0, 100, context)
    
    assert resp.answer == "Hello user, I can answer without tools."
    assert len(resp.iterations) == 1
    assert resp.iterations[0].state == AgentState.FINISHED
    assert len(resp.iterations[0].tool_calls) == 0


@pytest.mark.asyncio
async def test_agent_executor_loop_with_tool_call():
    # Scenario: LLM calls calculator first, then gets math answer, then generates final answer text.
    calc_tool = CalculatorTool()
    registry = ToolRegistry([calc_tool])
    executor = ToolExecutor()
    conv_mgr = MockConvMgr()
    estimator = DummyTokenEstimator()
    
    llm = MockLLMProvider([
        {
            "content": None,
            "tool_calls": [ToolCall(id="call_calc", name="calculator", arguments={"expression": "12 * 12"})]
        },
        {
            "content": "The result is 144.",
            "tool_calls": []
        }
    ])
    
    agent = AgentExecutor(llm, registry, executor, conv_mgr, estimator)
    context = ToolContext(user_id=uuid.uuid4(), conversation_id=uuid.uuid4(), db_session=None)
    
    messages = [ChatMessage(role=ChatRole.USER, content="What is 12 * 12?")]
    resp = await agent.execute(messages, "model-x", 0.0, 100, context)
    
    assert resp.answer == "The result is 144."
    assert len(resp.iterations) == 2
    # First iteration states
    assert resp.iterations[0].state == AgentState.OBSERVING_RESULT
    assert resp.iterations[0].tool_results[0].content in ("144", "144.0")
    
    # Second iteration states
    assert resp.iterations[1].state == AgentState.FINISHED
    assert len(resp.iterations[1].tool_calls) == 0

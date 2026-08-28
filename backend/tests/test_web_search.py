import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.chat.domain.agents import ToolContext
from app.chat.domain.interfaces import LLMProvider
from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentTask,
    AgentType,
    ExecutionPlan,
)
from app.chat.services.multi_agent.capability_registry import (
    create_default_capability_registry,
)
from app.chat.services.multi_agent.execution_engine import AgentExecutionEngine
from app.chat.services.multi_agent.master_agent import MasterAgent
from app.chat.services.multi_agent.synthesis_agent import SynthesisAgent
from app.chat.services.multi_agent.task_router import TaskRouter
from app.chat.services.multi_agent.web_search_agent import WebSearchAgent
from app.chat.services.tools.web_search import WebSearchTool
from app.chat.services.web_search_service import WebSearchResult, WebSearchService


@pytest.mark.asyncio
async def test_web_search_service_serpapi():
    service = WebSearchService(provider="serpapi", serpapi_api_key="test-serp-key")
    mock_serp_response = {
        "organic_results": [
            {
                "title": "Google AI Updates",
                "link": "https://google.com/ai-news",
                "snippet": "Google announces new features.",
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_serp_response
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        results = await service.search("google ai news", max_results=5)

        assert len(results) == 1
        assert results[0].title == "Google AI Updates"
        assert results[0].url == "https://google.com/ai-news"
        assert results[0].snippet == "Google announces new features."
        assert results[0].source == "serpapi"


@pytest.mark.asyncio
async def test_web_search_service_firecrawl():
    service = WebSearchService(provider="firecrawl", firecrawl_api_key="test-fc-key")
    mock_fc_response = {
        "success": True,
        "data": [
            {
                "title": "Firecrawl Documentation",
                "url": "https://docs.firecrawl.dev",
                "description": "Turn websites into LLM-ready markdown.",
            }
        ],
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_fc_response
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        results = await service.search("firecrawl docs", max_results=5)

        assert len(results) == 1
        assert results[0].title == "Firecrawl Documentation"
        assert results[0].url == "https://docs.firecrawl.dev"
        assert "LLM-ready markdown" in results[0].snippet
        assert results[0].source == "firecrawl"


@pytest.mark.asyncio
async def test_web_search_service_firecrawl_scrape():
    service = WebSearchService(firecrawl_api_key="test-fc-key")
    mock_scrape_response = {
        "success": True,
        "data": {"markdown": "# Firecrawl\nScrape web pages to markdown."},
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_scrape_response
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        md = await service.scrape_url("https://example.com")
        assert md == "# Firecrawl\nScrape web pages to markdown."


@pytest.mark.asyncio
async def test_web_search_service_duckduckgo_fallback():
    service = WebSearchService(provider="duckduckgo")
    sample_html = """
    <div class="result results_links results_links_deep web-result">
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fstory"><b>Test Story</b></a>
        <a class="result__snippet">This is a snippet describing the test story.</a>
    </div>
    """
    mock_resp = MagicMock()
    mock_resp.text = sample_html
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        results = await service.search("test query", max_results=5)

        assert len(results) == 1
        assert results[0].title == "Test Story"
        assert results[0].url == "https://example.com/story"
        assert "This is a snippet describing" in results[0].snippet


@pytest.mark.asyncio
async def test_web_search_service_empty_query():
    service = WebSearchService()
    results = await service.search("   ")
    assert results == []


@pytest.mark.asyncio
async def test_web_search_agent_success():
    mock_service = MagicMock(spec=WebSearchService)
    mock_service.search = AsyncMock(
        return_value=[
            WebSearchResult(
                title="Federal Reserve Update",
                url="https://federalreserve.gov/news",
                snippet="Interest rates held steady.",
                score=0.9,
                source="test",
            ),
            WebSearchResult(
                title="Market Analysis",
                url="https://markets.com/analysis",
                snippet="Stocks rose following the announcement.",
                score=0.85,
                source="test",
            ),
        ]
    )

    agent = WebSearchAgent(web_search_service=mock_service)
    task = AgentTask(
        task_id="web_1",
        request="What is the latest Federal Reserve interest rate?",
        agent_type=AgentType.WEB_SEARCH,
        parameters={"query": "Federal Reserve interest rate"},
    )
    context = AgentExecutionContext(
        request_id="req-1",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
    )

    result = await agent.execute_task(task, context)

    assert result.success is True
    assert result.task_id == "web_1"
    assert result.agent_type == AgentType.WEB_SEARCH
    assert len(result.evidence) == 2
    assert len(result.citations) == 2
    assert result.evidence[0].document_name == "[Web] Federal Reserve Update"
    assert "https://federalreserve.gov/news" in result.evidence[0].content
    assert len(result.metadata["sources"]) == 2


@pytest.mark.asyncio
async def test_web_search_agent_empty_results():
    mock_service = MagicMock(spec=WebSearchService)
    mock_service.search = AsyncMock(return_value=[])

    agent = WebSearchAgent(web_search_service=mock_service)
    task = AgentTask(
        task_id="web_1",
        request="Nonexistent topic",
        agent_type=AgentType.WEB_SEARCH,
    )
    context = AgentExecutionContext(
        request_id="req-1",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
    )

    result = await agent.execute_task(task, context)

    assert result.success is True
    assert len(result.evidence) == 0
    assert result.metadata.get("insufficient_evidence") is True


@pytest.mark.asyncio
async def test_web_search_tool():
    mock_service = MagicMock(spec=WebSearchService)
    mock_service.search = AsyncMock(
        return_value=[
            WebSearchResult(
                title="AI Breakthrough",
                url="https://ai.org/news",
                snippet="New model released.",
                score=1.0,
            )
        ]
    )
    tool = WebSearchTool(web_search_service=mock_service)
    ctx = MagicMock(spec=ToolContext)

    result = await tool.execute({"query": "AI breakthrough"}, ctx)

    assert result.is_error is False
    assert "AI Breakthrough" in result.content
    assert len(result.structured_output["results"]) == 1


@pytest.mark.asyncio
async def test_master_agent_heuristic_web_search_plan():
    llm = MagicMock(spec=LLMProvider)
    llm.generate = AsyncMock(return_value=None)
    engine = MagicMock(spec=AgentExecutionEngine)
    synth = MagicMock(spec=SynthesisAgent)

    master = MasterAgent(
        llm_provider=llm,
        execution_engine=engine,
        synthesis_agent=synth,
    )

    ctx = AgentExecutionContext(
        request_id="req-1",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
    )

    # 1. Pure web search query
    plan_web = await master.create_plan(
        "What is the latest news today about space exploration?", ctx
    )
    assert len(plan_web.tasks) >= 1
    assert any(t.agent_type == AgentType.WEB_SEARCH for t in plan_web.tasks)

    # 2. Compound query: Document + Web + Math
    plan_compound = await master.create_plan(
        "Compare my uploaded report with latest online inflation rate and calculate growth rate from 3.2 to 4.5",
        ctx,
    )
    task_types = [t.agent_type for t in plan_compound.tasks]
    assert AgentType.RESEARCH in task_types
    assert AgentType.WEB_SEARCH in task_types
    assert AgentType.ANALYSIS in task_types


@pytest.mark.asyncio
async def test_execution_engine_with_web_search_specialist():
    mock_service = MagicMock(spec=WebSearchService)
    mock_service.search = AsyncMock(
        return_value=[
            WebSearchResult(
                title="Stock Price",
                url="https://stocks.com/apple",
                snippet="Apple stock is $200.",
                score=1.0,
            )
        ]
    )
    web_agent = WebSearchAgent(web_search_service=mock_service)
    registry = create_default_capability_registry()
    router = TaskRouter(registry=registry)

    engine = AgentExecutionEngine(
        specialist_agents=[web_agent],
        task_router=router,
        capability_registry=registry,
    )

    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="web_task_1",
                request="Check latest Apple stock price online",
                agent_type=AgentType.WEB_SEARCH,
                dependencies=[],
            )
        ],
    )
    ctx = AgentExecutionContext(
        request_id="req-1",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
    )

    outcome = await engine.execute(plan, ctx)

    assert len(outcome.completed_results) == 1
    assert outcome.completed_results[0].agent_type == AgentType.WEB_SEARCH
    assert len(outcome.completed_results[0].evidence) == 1

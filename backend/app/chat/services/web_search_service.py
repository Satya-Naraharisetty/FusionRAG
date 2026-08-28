import html
import logging
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)


class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    score: float = 1.0
    source: str = "web"
    metadata: dict[str, Any] = Field(default_factory=dict)


class WebSearchService:
    """
    Multi-provider asynchronous Web Search Service.
    Supports SerpAPI (Google Search), Firecrawl (Search & Scrape),
    and zero-config DuckDuckGo fallback.
    """

    def __init__(
        self,
        provider: str | None = None,
        serpapi_api_key: str | None = None,
        firecrawl_api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.provider = str(
            provider or getattr(settings, "WEB_SEARCH_PROVIDER", "auto") or "auto"
        ).lower()
        self.serpapi_api_key = (
            serpapi_api_key or getattr(settings, "SERPAPI_API_KEY", None) or ""
        ).strip()
        self.firecrawl_api_key = (
            firecrawl_api_key or getattr(settings, "FIRECRAWL_API_KEY", None) or ""
        ).strip()
        self.timeout = (
            timeout
            if timeout is not None
            else getattr(settings, "WEB_SEARCH_TIMEOUT", 10.0)
        )

    async def search(self, query: str, max_results: int = 5) -> list[WebSearchResult]:
        """
        Executes a web search for the query, choosing the best available provider.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        # 1. SerpAPI (Google Search) if explicitly requested or if auto & API key is available
        if (
            self.provider == "serpapi"
            or (self.provider == "auto" and self.serpapi_api_key)
        ) and self.serpapi_api_key:
            try:
                results = await self._search_serpapi(clean_query, max_results)
                if results:
                    return results
            except Exception as e:
                logger.warning("SerpAPI search failed, falling back: %s", e)

        # 2. Firecrawl if explicitly requested or if auto & API key is available
        if (
            self.provider == "firecrawl"
            or (self.provider == "auto" and self.firecrawl_api_key)
        ) and self.firecrawl_api_key:
            try:
                results = await self._search_firecrawl(clean_query, max_results)
                if results:
                    return results
            except Exception as e:
                logger.warning("Firecrawl search failed, falling back: %s", e)

        # 3. DuckDuckGo as reliable zero-config fallback
        try:
            return await self._search_duckduckgo(clean_query, max_results)
        except Exception as e:
            logger.warning("DuckDuckGo search failed: %s", e)
            return []

    async def _search_serpapi(
        self, query: str, max_results: int
    ) -> list[WebSearchResult]:
        """Executes search via SerpAPI (Google Search engine)."""
        url = "https://serpapi.com/search.json"
        params: dict[str, str | int] = {
            "q": query,
            "api_key": self.serpapi_api_key,
            "engine": "google",
            "num": max_results,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        results: list[WebSearchResult] = []
        for item in data.get("organic_results", [])[:max_results]:
            title = item.get("title") or "Web Page"
            item_url = item.get("link") or ""
            snippet = item.get("snippet") or ""
            if item_url and snippet:
                results.append(
                    WebSearchResult(
                        title=title,
                        url=item_url,
                        snippet=snippet,
                        score=1.0,
                        source="serpapi",
                    )
                )
        return results

    async def _search_firecrawl(
        self, query: str, max_results: int
    ) -> list[WebSearchResult]:
        """Executes search via Firecrawl Search API."""
        url = "https://api.firecrawl.dev/v1/search"
        headers = {
            "Authorization": f"Bearer {self.firecrawl_api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "query": query,
            "limit": max_results,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        results: list[WebSearchResult] = []
        items = data.get("data", []) if isinstance(data, dict) else []
        for item in items[:max_results]:
            title = (
                item.get("title") or item.get("metadata", {}).get("title") or "Web Page"
            )
            item_url = item.get("url") or item.get("metadata", {}).get("url") or ""
            description = (
                item.get("description")
                or item.get("snippet")
                or item.get("metadata", {}).get("description")
                or ""
            )
            # If markdown is returned, extract leading paragraph if description is empty
            if not description and item.get("markdown"):
                raw_md = item.get("markdown", "")
                clean_lines = [
                    line.strip()
                    for line in raw_md.split("\n")
                    if line.strip() and not line.strip().startswith("#")
                ]
                description = " ".join(clean_lines[:3])[:300]

            if item_url and (title or description):
                results.append(
                    WebSearchResult(
                        title=title,
                        url=item_url,
                        snippet=description or title,
                        score=1.0,
                        source="firecrawl",
                    )
                )
        return results

    async def scrape_url(self, url: str) -> str | None:
        """
        Scrapes a single URL to clean markdown using Firecrawl Scrape API.
        """
        if not self.firecrawl_api_key:
            return None
        api_url = "https://api.firecrawl.dev/v1/scrape"
        headers = {
            "Authorization": f"Bearer {self.firecrawl_api_key}",
            "Content-Type": "application/json",
        }
        payload = {"url": url, "formats": ["markdown"]}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(api_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("data", {}).get("markdown")
        except Exception as e:
            logger.warning("Firecrawl scrape failed for %s: %s", url, e)
            return None

    async def _search_duckduckgo(
        self, query: str, max_results: int
    ) -> list[WebSearchResult]:
        """Executes search via DuckDuckGo HTML endpoint without requiring API keys."""
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        data = {"q": query, "b": ""}

        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True
        ) as client:
            response = await client.post(url, headers=headers, data=data)
            response.raise_for_status()
            html_text = response.text

        return self._parse_duckduckgo_html(html_text, max_results)

    def _parse_duckduckgo_html(
        self, html_text: str, max_results: int
    ) -> list[WebSearchResult]:
        """Extracts search results from DuckDuckGo HTML response."""
        results: list[WebSearchResult] = []

        # Find link & snippet pairs directly
        links = re.findall(
            r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html_text,
            re.DOTALL,
        )
        snippets = re.findall(
            r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
            html_text,
            re.DOTALL,
        )

        for idx, (raw_url, raw_title) in enumerate(links):
            if len(results) >= max_results:
                break

            title = html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
            raw_snippet = snippets[idx] if idx < len(snippets) else ""
            snippet = html.unescape(re.sub(r"<[^>]+>", "", raw_snippet)).strip()

            actual_url = raw_url
            if (
                "/l/?" in raw_url
                or "duckduckgo.com/l/?" in raw_url
                or "uddg=" in raw_url
            ):
                parsed = urlparse(raw_url)
                qs = parse_qs(parsed.query)
                if "uddg" in qs:
                    actual_url = unquote(qs["uddg"][0])
                elif "u" in qs:
                    actual_url = unquote(qs["u"][0])

            if actual_url.startswith("//"):
                actual_url = "https:" + actual_url

            if title and actual_url:
                results.append(
                    WebSearchResult(
                        title=title,
                        url=actual_url,
                        snippet=snippet or title,
                        score=1.0,
                        source="duckduckgo",
                    )
                )

        return results

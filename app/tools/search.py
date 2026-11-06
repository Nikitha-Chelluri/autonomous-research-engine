from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import get_settings


class WebSearchTool:
    """Search via Tavily (preferred) or Google Serper."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        if self.settings.tavily_api_key:
            return await self._tavily(query, max_results)
        if self.settings.serper_api_key:
            return await self._serper(query, max_results)
        return self._mock_results(query, max_results)

    async def _tavily(self, query: str, max_results: int) -> list[dict[str, Any]]:
        from tavily import AsyncTavilyClient

        client = AsyncTavilyClient(api_key=self.settings.tavily_api_key)
        response = await client.search(query=query, max_results=max_results, include_raw_content=False)
        results: list[dict[str, Any]] = []
        for item in response.get("results", []):
            results.append(
                {
                    "url": item.get("url", ""),
                    "title": item.get("title", ""),
                    "snippet": item.get("content", "") or item.get("snippet", ""),
                }
            )
        return results

    async def _serper(self, query: str, max_results: int) -> list[dict[str, Any]]:
        url = "https://google.serper.dev/search"
        headers = {"X-API-KEY": self.settings.serper_api_key, "Content-Type": "application/json"}
        payload = {"q": query, "num": max_results}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        results: list[dict[str, Any]] = []
        for item in data.get("organic", [])[:max_results]:
            results.append(
                {
                    "url": item.get("link", ""),
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                }
            )
        return results

    def _mock_results(self, query: str, max_results: int) -> list[dict[str, Any]]:
        base = [
            {
                "url": "https://example.com/market-overview",
                "title": f"Market overview — {query}",
                "snippet": "Synthetic result for local development without search API keys.",
            },
            {
                "url": "https://example.com/competitor-analysis",
                "title": "Competitive landscape snapshot",
                "snippet": "Placeholder competitive intelligence snippet for pipeline testing.",
            },
        ]
        return base[:max_results]

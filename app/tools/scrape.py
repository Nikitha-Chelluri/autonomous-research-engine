from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings


def _html_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:12000]


class WebScrapeTool:
    async def scrape(self, url: str) -> str:
        settings = get_settings()
        if settings.firecrawl_api_key:
            content = await self._firecrawl(url)
            if content:
                return content
        return await self._httpx_scrape(url)

    async def _firecrawl(self, url: str) -> str:
        settings = get_settings()
        api_url = "https://api.firecrawl.dev/v1/scrape"
        headers = {"Authorization": f"Bearer {settings.firecrawl_api_key}", "Content-Type": "application/json"}
        payload = {"url": url, "formats": ["markdown"]}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(api_url, headers=headers, json=payload)
            if resp.status_code >= 400:
                return ""
            data = resp.json()
        md = (data.get("data") or {}).get("markdown") or ""
        return md[:12000]

    async def _httpx_scrape(self, url: str) -> str:
        if url.startswith("https://example.com"):
            return (
                f"# Scraped placeholder for {url}\n\n"
                "This is mock scraped content used when no live scrape is available.\n"
                "Include factual statements only when real sources are configured."
            )
        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": "ResearchEngine/1.0 (+research-bot)"},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return _html_to_markdown(resp.text)
        except Exception as exc:  # noqa: BLE001 — return error text to agent context
            return f"_Failed to scrape {url}: {exc}_"

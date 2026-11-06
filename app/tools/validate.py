from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from app.agents.state import ReviewResult

CITATION_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)|\((https?://[^)]+)\)")
URL_PATTERN = re.compile(r"https?://[^\s)\]>]+")


def extract_urls_from_markdown(markdown: str) -> list[str]:
    urls: list[str] = []
    for match in CITATION_PATTERN.finditer(markdown):
        urls.append(match.group(2) or match.group(3))
    for match in URL_PATTERN.finditer(markdown):
        u = match.group(0).rstrip(".,;")
        if u not in urls:
            urls.append(u)
    return urls


async def check_url_reachable(url: str) -> bool:
    if url.startswith("https://example.com"):
        return True
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.head(url)
            if resp.status_code >= 400:
                resp = await client.get(url)
            return resp.status_code < 400
    except Exception:
        return False


def markdown_structure_issues(markdown: str) -> list[str]:
    issues: list[str] = []
    required_sections = [
        "## Executive Summary",
        "## Key Findings",
        "## Competitive Landscape",
        "## Deep Dive",
    ]
    for section in required_sections:
        if section not in markdown:
            issues.append(f"Missing section: {section}")
    if len(markdown.strip()) < 400:
        issues.append("Report body is too short for a competitive intelligence brief.")
    return issues


async def run_code_validator(markdown: str, raw_notes: str) -> ReviewResult:
    issues = markdown_structure_issues(markdown)
    urls = extract_urls_from_markdown(markdown)
    broken: list[str] = []
    for url in urls[:15]:
        if not await check_url_reachable(url):
            broken.append(url)

    missing_sources: list[str] = []
    if not urls:
        missing_sources.append("No inline citations or source URLs found in the report.")

    # Heuristic: flag lines that look like strong claims without nearby URL in same paragraph
    for block in markdown.split("\n\n"):
        if any(kw in block.lower() for kw in ("leading", "market share", "revenue", "dominates")):
            if "http" not in block:
                missing_sources.append(f"Unsourced claim block: {block[:80]}...")

    approved = not issues and not broken and not missing_sources
    confidence = 1.0
    if issues:
        confidence -= 0.2 * len(issues)
    if broken:
        confidence -= 0.15 * len(broken)
    if missing_sources:
        confidence -= 0.1 * len(missing_sources)
    confidence = max(0.0, min(1.0, confidence))

    return ReviewResult(
        approved=approved,
        confidence_score=round(confidence, 2),
        issues=issues,
        missing_sources=missing_sources,
        broken_urls=broken,
    )

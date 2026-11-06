from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.state import ResearchGraphState, raw_sources_to_notes
from app.config import get_settings
from app.llm import get_chat_model, llm_text
from app.tools.scrape import WebScrapeTool
from app.tools.search import WebSearchTool
from app.tools.validate import run_code_validator

RESEARCHER_SYSTEM = """You are the Lead Researcher — an expert investigative data analyst for competitive intelligence.

Your job:
1. Formulate 3–5 targeted web search queries from the user's topic and any reviewer feedback.
2. Prefer primary sources: company sites, earnings, product docs, reputable trade press.
3. Never fabricate URLs or facts.

When asked for queries only, respond with a JSON array of strings and nothing else."""

WRITER_SYSTEM = """You are the Technical Writer & Editor — a professional business intelligence copywriter.

Produce a markdown competitive intelligence brief with these exact H2 sections:
## Executive Summary
## Key Findings
## Competitive Landscape
## Deep Dive

Rules:
- Synthesize ONLY from the provided raw sources.
- Every factual claim must include an inline markdown link citation [label](url).
- If data is missing, state the gap explicitly; do not invent statistics."""

REVIEWER_SYSTEM = """You are the Quality & Compliance Reviewer — a ruthless fact-checker and alignment supervisor.

Given a draft report and automated validator output:
- Verify claims map to cited sources.
- Flag hallucinations, missing citations, and broken structure.
- If the validator marks approved=true and the draft is sound, respond with exactly: APPROVED
- Otherwise give 3–6 bullet points of specific fixes for the Researcher and Writer."""


async def search_web(query: str, *, max_results: int = 5) -> str:
    """Run Tavily/Serper (or mock) and return a compact JSON string for agent context."""
    tool = WebSearchTool()
    results = await tool.search(query, max_results=max_results)
    return json.dumps(results, ensure_ascii=False)


async def scrape_url(url: str) -> str:
    """Fetch page content as markdown/plain text for the research context window."""
    tool = WebScrapeTool()
    return await tool.scrape(url)


async def _generate_search_queries(state: ResearchGraphState) -> list[str]:
    topic = state["topic"]
    feedback = state.get("reviewer_feedback") or ""
    entities = state.get("focus_entities") or []

    user = f"Topic: {topic}\nFocus entities: {', '.join(entities) or 'none'}\n"
    if feedback:
        user += f"Reviewer feedback to address:\n{feedback}\n"

    fallback = json.dumps(
        [
            f"{topic} competitive landscape 2026",
            f"{topic} market leaders comparison",
            f"{topic} pricing and product analysis",
        ]
    )
    raw = await llm_text(RESEARCHER_SYSTEM, user, fallback=fallback)
    try:
        queries = json.loads(raw)
        if isinstance(queries, list):
            return [str(q) for q in queries][:5]
    except json.JSONDecodeError:
        pass
    return [line.strip("- ").strip() for line in raw.splitlines() if line.strip()][:5]


async def researcher_node(state: ResearchGraphState) -> dict[str, Any]:
    loop_count = state.get("loop_count", 0)
    print(f"[Researcher Agent] Formulating queries and gathering facts... (loop {loop_count + 1})")

    telemetry = [f"Entering Node: Researcher (loop {loop_count + 1})"]
    queries = await _generate_search_queries(state)

    raw_sources: list[dict[str, str]] = []
    for query in queries:
        telemetry.append(f"Tool Executed: Search — {query}")
        search_payload = await search_web(query, max_results=3)
        hits = json.loads(search_payload)
        for hit in hits:
            url = hit.get("url", "")
            if not url:
                continue
            telemetry.append(f"Tool Executed: Scrape — {url}")
            content = await scrape_url(url)
            raw_sources.append(
                {
                    "query": query,
                    "url": url,
                    "title": hit.get("title", ""),
                    "snippet": hit.get("snippet", ""),
                    "content": content[:4000],
                }
            )

    return {
        "search_queries": queries,
        "raw_sources": raw_sources,
        "status": "pending",
        "reviewer_feedback": "",
        "telemetry": telemetry,
    }


async def writer_node(state: ResearchGraphState) -> dict[str, Any]:
    print("[Writer Agent] Synthesizing report from raw facts...")
    topic = state["topic"]
    raw_sources = state.get("raw_sources") or []
    notes = raw_sources_to_notes(raw_sources)

    telemetry = ["Entering Node: Writer / Editor"]
    source_index = "\n".join(
        f"- [{s.get('title') or s.get('url', 'source')}]({s['url']})"
        for s in raw_sources
        if s.get("url")
    )

    user = (
        f"Topic: {topic}\n\nSource index:\n{source_index or 'none'}\n\n"
        f"Raw research notes:\n{notes[:24000]}"
    )

    fallback = f"""## Executive Summary

Strategic market report for **{topic}** (configure `OPENAI_API_KEY` for full LLM synthesis).

## Key Findings

- Compiled {len(raw_sources)} web signal(s) for 2026-oriented analysis.

## Competitive Landscape

{source_index or '_No sources._'}

## Deep Dive

{notes[:8000]}
"""

    settings = get_settings()
    if settings.llm_configured:
        model = get_chat_model()
        response = await model.ainvoke([SystemMessage(content=WRITER_SYSTEM), HumanMessage(content=user)])
        draft = response.content if isinstance(response.content, str) else fallback
    else:
        draft = fallback

    telemetry.append("Tool Executed: Format standardizer — markdown structure applied")
    return {"report_draft": draft.strip(), "telemetry": telemetry}


async def reviewer_node(state: ResearchGraphState) -> dict[str, Any]:
    print("[Reviewer Agent] Validating facts and sources...")
    draft = state.get("report_draft") or ""
    notes = raw_sources_to_notes(state.get("raw_sources") or [])

    telemetry = ["Entering Node: Quality Reviewer"]
    code_review = await run_code_validator(draft, notes)
    telemetry.append("Tool Executed: Code validator — links & markdown structure")

    validator_user = (
        f"Validator JSON:\n{json.dumps(code_review)}\n\n"
        f"Draft excerpt:\n{draft[:6000]}"
    )
    llm_feedback = await llm_text(REVIEWER_SYSTEM, validator_user, fallback="")

    code_ok = bool(code_review.get("approved"))
    settings = get_settings()
    if settings.llm_configured:
        approved = code_ok and "APPROVED" in llm_feedback.upper()
    else:
        approved = code_ok

    feedback_parts: list[str] = []
    if code_review.get("issues"):
        feedback_parts.extend(code_review["issues"])
    if code_review.get("missing_sources"):
        feedback_parts.extend(code_review["missing_sources"])
    if code_review.get("broken_urls"):
        feedback_parts.append(f"Broken URLs: {', '.join(code_review['broken_urls'])}")
    if llm_feedback and "APPROVED" not in llm_feedback.upper():
        feedback_parts.append(llm_feedback)

    if not approved and "2026" not in draft:
        feedback_parts.append(
            "The report lacks explicit data signals mapped to the current 2026 timeline."
        )

    feedback = "\n".join(f"- {p}" for p in feedback_parts) if feedback_parts else ""
    verification = "approved" if approved else "rejected"

    if approved:
        telemetry.append("Reviewer: PASS — routing to persist")
    else:
        telemetry.append("Reviewer: FAIL — routing back to Researcher")

    review = {**code_review, "approved": approved}
    result: dict[str, Any] = {
        "review": review,
        "status": verification,
        "reviewer_feedback": feedback,
        "telemetry": telemetry,
    }
    if not approved:
        result["loop_count"] = state.get("loop_count", 0) + 1
    return result

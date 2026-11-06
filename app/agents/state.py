from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

ReportType = Literal["competitive_intelligence"]
VerificationStatus = Literal["approved", "rejected", "pending"]


class ResearchState(TypedDict):
    """Persistent data passed between agents during a research job."""

    topic: str
    search_queries: list[str]
    raw_sources: list[dict[str, str]]
    report_draft: str
    reviewer_feedback: str
    status: str
    loop_count: int


class ReviewResult(TypedDict, total=False):
    approved: bool
    confidence_score: float
    issues: list[str]
    missing_sources: list[str]
    broken_urls: list[str]


class ResearchGraphState(ResearchState, total=False):
    """ResearchState plus LangGraph orchestration and persistence fields."""

    job_id: str
    report_type: ReportType
    focus_entities: list[str]
    max_loops: int

    review: ReviewResult
    telemetry: Annotated[list[str], operator.add]
    final_payload: dict[str, Any]
    job_status: Literal["running", "completed", "failed"]
    error: str
    _started_at: float


def raw_sources_to_notes(sources: list[dict[str, str]]) -> str:
    blocks: list[str] = []
    for source in sources:
        url = source.get("url", "")
        title = source.get("title") or url
        content = source.get("content") or source.get("scraped_markdown") or source.get("snippet") or ""
        blocks.append(f"### Source: {title}\nURL: {url}\n\n{content}")
    return "\n\n".join(blocks) if blocks else "_No sources retrieved._"

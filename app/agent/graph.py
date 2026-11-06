from __future__ import annotations

import time
from typing import Literal

from langgraph.graph import END, StateGraph

from app.agent.nodes import researcher_node, reviewer_node, writer_node
from app.agent.state import ResearchGraphState
from app.config import get_settings


def route_review_result(state: ResearchGraphState) -> Literal["researcher", "finalize"]:
    """Self-correction router: approve → finalize; reject → researcher until loop cap."""
    if state["status"] == "approved":
        return "finalize"

    max_loops = state.get("max_loops") or get_settings().max_research_iterations
    if state.get("loop_count", 0) < max_loops:
        print(
            "[Quality Control] Report rejected. Routing back to Researcher for refinement."
        )
        return "researcher"

    print("[Quality Control] Max review loop iterations reached. Forcing completion.")
    return "finalize"


async def finalize_node(state: ResearchGraphState) -> dict:
    review = state.get("review") or {}
    raw_sources = state.get("raw_sources") or []
    started = state.get("_started_at")
    execution_time = time.time() - started if started else 0.0

    approved = state.get("status") == "approved"
    job_status: Literal["completed", "failed"] = "completed" if approved else "failed"

    payload = {
        "topic": state.get("topic"),
        "report_type": state.get("report_type", "competitive_intelligence"),
        "markdown_body": state.get("report_draft", ""),
        "sources_compiled": [
            {"url": s.get("url"), "title": s.get("title")} for s in raw_sources if s.get("url")
        ],
        "execution_time_seconds": round(execution_time, 2),
        "confidence_score": review.get("confidence_score", 0.0),
        "approved": approved,
        "verification_status": state.get("status", "pending"),
        "loop_count": state.get("loop_count", 0),
        "review_issues": review.get("issues", []),
    }

    return {
        "final_payload": payload,
        "job_status": job_status,
        "telemetry": [
            "Entering Node: Finalize",
            f"Job status: {job_status} (verification={state.get('status')})",
        ],
    }


def build_agent_graph():
    workflow = StateGraph(ResearchGraphState)

    workflow.add_node("researcher", researcher_node)
    workflow.add_node("writer", writer_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("finalize", finalize_node)

    workflow.set_entry_point("researcher")
    workflow.add_edge("researcher", "writer")
    workflow.add_edge("writer", "reviewer")

    workflow.add_conditional_edges(
        "reviewer",
        route_review_result,
        {
            "researcher": "researcher",
            "finalize": "finalize",
        },
    )
    workflow.add_edge("finalize", END)

    return workflow.compile()


agent_graph = build_agent_graph()

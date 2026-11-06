from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import research_graph
from app.agents.state import ResearchGraphState
from app.config import get_settings
from app.db.models import ResearchJob


def _initial_state(job_id: str, topic: str, report_type: str, focus_entities: list[str]) -> ResearchGraphState:
    settings = get_settings()
    return ResearchGraphState(
        job_id=job_id,
        topic=topic,
        report_type=report_type,  # type: ignore[typeddict-item]
        focus_entities=focus_entities,
        search_queries=[],
        raw_sources=[],
        report_draft="",
        reviewer_feedback="",
        status="pending",
        loop_count=0,
        max_loops=settings.max_research_iterations,
        telemetry=["Graph started"],
        job_status="running",
        _started_at=time.time(),
    )


async def run_research_graph(
    job_id: uuid.UUID,
    topic: str,
    report_type: str,
    focus_entities: list[str],
    *,
    on_event: Callable[[str, dict], None] | None = None,
) -> dict[str, Any]:
    state = _initial_state(str(job_id), topic, report_type, focus_entities)
    accumulated_telemetry: list[str] = list(state.get("telemetry") or [])

    final_state: ResearchGraphState = state
    async for event in research_graph.astream(state, stream_mode="updates"):
        for node_name, node_update in event.items():
            if on_event:
                on_event(node_name, node_update)
            chunk_telemetry = node_update.get("telemetry") or []
            accumulated_telemetry.extend(chunk_telemetry)
            final_state = {**final_state, **node_update}  # type: ignore[typeddict-item]

    final_state["telemetry"] = accumulated_telemetry  # type: ignore[typeddict-item]
    return dict(final_state)


async def persist_job_result(session: AsyncSession, job_id: uuid.UUID, graph_result: dict[str, Any]) -> None:
    result = await session.execute(select(ResearchJob).where(ResearchJob.id == job_id))
    job = result.scalar_one()

    payload = graph_result.get("final_payload") or {}
    job.status = graph_result.get("job_status") or "failed"
    job.result_payload = payload
    job.trace_log = graph_result.get("telemetry") or []
    job.markdown_body = payload.get("markdown_body") or graph_result.get("report_draft")
    job.confidence_score = payload.get("confidence_score")
    job.execution_time_seconds = payload.get("execution_time_seconds")
    if graph_result.get("error"):
        job.error_message = graph_result["error"]

    await session.commit()

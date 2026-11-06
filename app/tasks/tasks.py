from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

import redis

from app.agent.graph import agent_graph
from app.agent.state import ResearchGraphState
from app.config import get_settings
from app.db.session import get_session_factory, init_db, reset_async_engine
from app.services.research_runner import persist_job_result
from app.tasks.celery_app import celery_app


def _telemetry_key(job_id: str) -> str:
    return f"research:telemetry:{job_id}"


def _publish_event(job_id: str, node: str, data: dict[str, Any]) -> None:
    settings = get_settings()
    client = redis.from_url(settings.celery_broker_url)
    payload = {"node": node, "telemetry": data.get("telemetry", [])}
    client.publish(f"research:stream:{job_id}", json.dumps(payload))
    key = _telemetry_key(job_id)
    for line in data.get("telemetry") or []:
        client.rpush(key, line)
    client.expire(key, 86400)


def build_initial_state(
    job_id: str,
    topic: str,
    *,
    report_type: str = "competitive_intelligence",
    focus_entities: list[str] | None = None,
) -> ResearchGraphState:
    settings = get_settings()
    return ResearchGraphState(
        job_id=job_id,
        topic=topic,
        report_type=report_type,  # type: ignore[typeddict-item]
        focus_entities=focus_entities or [],
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


async def execute_agent_graph(
    initial_state: ResearchGraphState,
    *,
    job_id: str,
    stream_telemetry: bool = True,
) -> dict[str, Any]:
    accumulated_telemetry: list[str] = list(initial_state.get("telemetry") or [])
    final_state: dict[str, Any] = dict(initial_state)

    async for event in agent_graph.astream(initial_state, stream_mode="updates"):
        for node_name, node_update in event.items():
            if stream_telemetry:
                _publish_event(job_id, node_name, node_update)
            accumulated_telemetry.extend(node_update.get("telemetry") or [])
            final_state = {**final_state, **node_update}

    final_state["telemetry"] = accumulated_telemetry
    return final_state


async def _run_and_persist(
    job_id: str,
    topic: str,
    report_type: str,
    focus_entities: list[str],
) -> dict[str, Any]:
    # Celery calls asyncio.run() per task; a process-global async engine must not be reused
    # across closed event loops (asyncpg / SQLAlchemy async).
    await reset_async_engine()
    await init_db()
    jid = uuid.UUID(job_id)
    initial_state = build_initial_state(
        job_id,
        topic,
        report_type=report_type,
        focus_entities=focus_entities,
    )

    try:
        final_state = await execute_agent_graph(initial_state, job_id=job_id)
        factory = get_session_factory()
        async with factory() as session:
            await persist_job_result(session, jid, final_state)

        print(f"[OK] Job {job_id} complete! Status: {final_state.get('status')}")
        return {
            "job_id": job_id,
            "verification_status": final_state.get("status"),
            "job_status": final_state.get("job_status"),
            "report_draft": final_state.get("report_draft", ""),
        }
    except Exception as exc:  # noqa: BLE001
        factory = get_session_factory()
        async with factory() as session:
            from sqlalchemy import select

            from app.db.models import ResearchJob

            row = await session.execute(select(ResearchJob).where(ResearchJob.id == jid))
            job = row.scalar_one()
            job.status = "failed"
            job.error_message = str(exc)
            await session.commit()
        raise


@celery_app.task(name="app.tasks.run_agent_research")
def run_agent_research(
    job_id: str,
    topic: str,
    report_type: str = "competitive_intelligence",
    focus_entities: list[str] | None = None,
) -> dict[str, Any]:
    """Run LangGraph in a Celery worker thread (asyncio.run) so the API stays responsive."""
    entities = focus_entities or []
    return asyncio.run(_run_and_persist(job_id, topic, report_type, entities))

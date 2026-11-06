from __future__ import annotations

import asyncio
import json
import uuid

import redis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.db.models import ResearchJob
from app.db.session import get_db_session
from app.schemas.report import ResearchJobCreate, ResearchJobDetail, ResearchJobResponse
from app.tasks.tasks import run_agent_research

router = APIRouter(prefix="/research", tags=["research"])


@router.post("/jobs", response_model=ResearchJobResponse)
async def create_research_job(
    body: ResearchJobCreate,
    session: AsyncSession = Depends(get_db_session),
) -> ResearchJobResponse:
    job = ResearchJob(
        topic=body.topic,
        report_type=body.report_type,
        status="queued",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    task = run_agent_research.delay(
        str(job.id),
        body.topic,
        body.report_type,
        body.focus_entities,
    )
    job.celery_task_id = task.id
    job.status = "running"
    await session.commit()

    return ResearchJobResponse(id=job.id, status=job.status, celery_task_id=task.id)


@router.get("/jobs/{job_id}", response_model=ResearchJobDetail)
async def get_research_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> ResearchJobDetail:
    result = await session.execute(select(ResearchJob).where(ResearchJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return ResearchJobDetail(
        id=job.id,
        topic=job.topic,
        report_type=job.report_type,
        status=job.status,
        result_payload=job.result_payload,
        trace_log=job.trace_log,
        markdown_body=job.markdown_body,
        confidence_score=job.confidence_score,
        execution_time_seconds=job.execution_time_seconds,
        error_message=job.error_message,
    )


@router.get("/jobs/{job_id}/stream")
async def stream_job_telemetry(job_id: uuid.UUID) -> EventSourceResponse:
    settings = get_settings()
    channel = f"research:stream:{job_id}"
    list_key = f"research:telemetry:{job_id}"

    async def event_generator():
        client = redis.from_url(settings.celery_broker_url)
        pubsub = client.pubsub()
        pubsub.subscribe(channel)

        # Replay buffered telemetry
        for line in client.lrange(list_key, 0, -1):
            decoded = line.decode() if isinstance(line, bytes) else str(line)
            yield {"event": "telemetry", "data": decoded}

        while True:
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "message":
                data = message["data"]
                decoded = data.decode() if isinstance(data, bytes) else str(data)
                try:
                    payload = json.loads(decoded)
                    for line in payload.get("telemetry", []):
                        yield {"event": "telemetry", "data": line}
                    yield {"event": "node", "data": payload.get("node", "")}
                except json.JSONDecodeError:
                    yield {"event": "telemetry", "data": decoded}
            await asyncio.sleep(0.3)

    return EventSourceResponse(event_generator())

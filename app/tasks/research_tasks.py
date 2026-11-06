"""Legacy task name used by the API; delegates to app.tasks.tasks.run_agent_research."""

from __future__ import annotations

from typing import Any

from app.tasks.celery_app import celery_app
from app.tasks.tasks import run_agent_research


@celery_app.task(name="research.run_job", bind=True)
def run_research_job_task(
    self,
    job_id: str,
    topic: str,
    report_type: str,
    focus_entities: list[str],
) -> dict[str, Any]:
    return run_agent_research(job_id, topic, report_type, focus_entities)

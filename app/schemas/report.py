from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class ResearchJobCreate(BaseModel):
    topic: str = Field(..., min_length=3, max_length=512)
    report_type: Literal["competitive_intelligence"] = "competitive_intelligence"
    focus_entities: list[str] = Field(default_factory=list, max_length=10)


class ResearchJobResponse(BaseModel):
    id: uuid.UUID
    status: str
    celery_task_id: str | None = None


class ResearchJobDetail(BaseModel):
    id: uuid.UUID
    topic: str
    report_type: str
    status: str
    result_payload: dict | None = None
    trace_log: list[str] | None = None
    markdown_body: str | None = None
    confidence_score: float | None = None
    execution_time_seconds: float | None = None
    error_message: str | None = None

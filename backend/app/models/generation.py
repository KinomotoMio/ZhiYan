"""Generation v2 data models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GenerationMode(str, Enum):
    AUTO = "auto"
    REVIEW_OUTLINE = "review_outline"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_OUTLINE_REVIEW = "waiting_outline_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StageStatus(str, Enum):
    PARSE = "parse"
    OUTLINE = "outline"
    LAYOUT = "layout"
    SLIDES = "slides"
    ASSETS = "assets"
    VERIFY = "verify"
    FIX = "fix"
    COMPLETE = "complete"


class EventType(str, Enum):
    JOB_STARTED = "job_started"
    STAGE_STARTED = "stage_started"
    STAGE_PROGRESS = "stage_progress"
    OUTLINE_READY = "outline_ready"
    LAYOUT_READY = "layout_ready"
    SLIDE_READY = "slide_ready"
    STAGE_FAILED = "stage_failed"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    JOB_CANCELLED = "job_cancelled"
    HEARTBEAT = "heartbeat"


TERMINAL_EVENTS = {
    EventType.JOB_COMPLETED,
    EventType.JOB_FAILED,
    EventType.JOB_CANCELLED,
}


class GenerationRequestData(BaseModel):
    topic: str = ""
    content: str = ""
    source_ids: list[str] = Field(default_factory=list)
    template_id: str | None = None
    num_pages: int = 5
    title: str = "新演示文稿"
    resolved_content: str = ""


class StageResult(BaseModel):
    stage: StageStatus
    status: str
    started_at: str
    ended_at: str | None = None
    duration_ms: int | None = None
    error: str | None = None


class GenerationEvent(BaseModel):
    seq: int
    type: EventType
    job_id: str
    ts: str = Field(default_factory=now_iso)
    stage: StageStatus | None = None
    message: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class GenerationJob(BaseModel):
    job_id: str
    mode: GenerationMode = GenerationMode.AUTO
    status: JobStatus = JobStatus.PENDING
    current_stage: StageStatus | None = None

    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    request: GenerationRequestData

    document_metadata: dict[str, Any] = Field(default_factory=dict)
    outline: dict[str, Any] = Field(default_factory=dict)
    layouts: list[dict[str, Any]] = Field(default_factory=list)
    slides: list[dict[str, Any]] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    failed_slide_indices: list[int] = Field(default_factory=list)

    outline_accepted: bool = False
    fix_passes: int = 0
    cancel_requested: bool = False
    events_seq: int = 0

    presentation: dict[str, Any] | None = None
    error: str | None = None

    stage_results: list[StageResult] = Field(default_factory=list)


class CreateJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: str
    event_stream_url: str


class AcceptOutlineRequest(BaseModel):
    outline: dict[str, Any] | None = None


class JobActionResponse(BaseModel):
    job_id: str
    status: JobStatus
    current_stage: StageStatus | None = None


class CreateJobRequest(BaseModel):
    topic: str = ""
    content: str = ""
    source_ids: list[str] = Field(default_factory=list)
    template_id: str | None = None
    num_pages: int = 5
    mode: GenerationMode = GenerationMode.AUTO

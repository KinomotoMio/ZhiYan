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


class PresentationOutputMode(str, Enum):
    STRUCTURED = "structured"
    HTML = "html"
    SLIDEV = "slidev"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_OUTLINE_REVIEW = "waiting_outline_review"
    WAITING_FIX_REVIEW = "waiting_fix_review"
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
    JOB_WAITING_FIX_REVIEW = "job_waiting_fix_review"
    FIX_PREVIEW_READY = "fix_preview_ready"
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
    """Job request payload stored alongside the generation job.

    Note: this model must remain backward compatible because older jobs are loaded
    from disk without newer fields.
    """

    class SourceHints(BaseModel):
        """A light-weight material inventory derived from source_ids.

        This is intentionally coarse (counts only) and is safe to omit.
        Downstream stages can use it to bias outline/layout decisions when users
        upload images or data files.
        """

        total_sources: int = 0
        images: int = 0
        documents: int = 0
        slides: int = 0
        data: int = 0
        unknown: int = 0
        by_file_category: dict[str, int] = Field(default_factory=dict)

    topic: str = ""
    content: str = ""
    session_id: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    source_hints: SourceHints = Field(default_factory=SourceHints)
    template_id: str | None = None
    num_pages: int = 5
    title: str = "新演示文稿"
    resolved_content: str = ""
    output_mode: PresentationOutputMode = PresentationOutputMode.STRUCTURED
    skill_id: str | None = None


class RunTokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ActivatedSkill(BaseModel):
    skill_id: str
    name: str | None = None
    scope: str | None = None
    path: str | None = None
    source: str
    reason: str
    default_for_output: str | None = None
    resources: list[str] = Field(default_factory=list)
    shadowed: list[dict[str, Any]] = Field(default_factory=list)


class RunMetadata(BaseModel):
    run_id: str = ""
    skill_id: str | None = None
    base_skill_id: str | None = None
    activated_skills: list[ActivatedSkill] = Field(default_factory=list)
    output_mode: PresentationOutputMode = PresentationOutputMode.STRUCTURED
    latency_ms: int | None = None
    token_usage: RunTokenUsage = Field(default_factory=RunTokenUsage)
    tool_events: list[dict[str, Any]] = Field(default_factory=list)
    artifact_refs: dict[str, Any] = Field(default_factory=dict)
    error_class: str | None = None


class StageResult(BaseModel):
    stage: StageStatus
    status: str
    started_at: str
    ended_at: str | None = None
    duration_ms: int | None = None
    error: str | None = None
    error_code: str | None = None
    retriable: bool | None = None
    timeout_seconds: float | None = None
    provider_model: str | None = None
    provider: str | None = None


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
    output_mode: PresentationOutputMode = PresentationOutputMode.STRUCTURED

    document_metadata: dict[str, Any] = Field(default_factory=dict)
    outline: dict[str, Any] = Field(default_factory=dict)
    layouts: list[dict[str, Any]] = Field(default_factory=list)
    slides: list[dict[str, Any]] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    failed_slide_indices: list[int] = Field(default_factory=list)
    hard_issue_slide_ids: list[str] = Field(default_factory=list)
    advisory_issue_count: int = 0
    fix_preview_slides: list[dict[str, Any]] = Field(default_factory=list)
    fix_preview_source_ids: list[str] = Field(default_factory=list)

    outline_accepted: bool = False
    fix_passes: int = 0
    cancel_requested: bool = False
    events_seq: int = 0

    presentation: dict[str, Any] | None = None
    error: str | None = None
    run_metadata: RunMetadata | None = None

    stage_results: list[StageResult] = Field(default_factory=list)


class CreateJobResponse(BaseModel):
    job_id: str
    session_id: str | None = None
    status: JobStatus
    created_at: str
    event_stream_url: str
    skill_id: str | None = None
    run_id: str | None = None
    run_metadata: RunMetadata | None = None


class AcceptOutlineRequest(BaseModel):
    outline: dict[str, Any] | None = None
    output_mode: PresentationOutputMode | None = None


class FixPreviewRequest(BaseModel):
    slide_ids: list[str] | None = None


class FixApplyRequest(BaseModel):
    slide_ids: list[str] = Field(default_factory=list)


class JobActionResponse(BaseModel):
    job_id: str
    status: JobStatus
    current_stage: StageStatus | None = None


class CreateJobRequest(BaseModel):
    topic: str = ""
    content: str = ""
    session_id: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    template_id: str | None = None
    num_pages: int = 5
    mode: GenerationMode = GenerationMode.AUTO
    approved_outline: dict[str, Any] | None = None
    output_mode: PresentationOutputMode = PresentationOutputMode.STRUCTURED
    skill_id: str | None = None

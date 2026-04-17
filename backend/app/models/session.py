"""Session API models."""

from typing import Any

from pydantic import BaseModel, Field

from app.models.source import SourceMeta


class SessionSummary(BaseModel):
    id: str
    workspace_id: str
    title: str
    title_edited_by_user: bool = False
    status: str = "active"
    is_pinned: bool = False
    archived_at: str | None = None
    created_at: str
    updated_at: str
    last_opened_at: str | None = None
    source_count: int = 0
    chat_count: int = 0
    has_presentation: bool = False


class ChatRecord(BaseModel):
    id: str
    role: str
    content: str
    created_at: str
    model_meta: dict = Field(default_factory=dict)


class SnapshotMeta(BaseModel):
    id: str
    version_no: int
    is_snapshot: bool
    snapshot_label: str | None = None
    created_at: str


class LatestPresentationWriteRequest(BaseModel):
    presentation: dict | None = None
    source: str | None = "editor"
    output_mode: str | None = None
    html_deck: dict[str, Any] | None = None
    slidev_deck: dict[str, Any] | None = None


class LatestGenerationJobMeta(BaseModel):
    job_id: str
    status: str
    updated_at: str


class PlanningOutlineItem(BaseModel):
    slide_number: int
    title: str
    content_brief: str = ""
    key_points: list[str] = Field(default_factory=list)
    content_hints: list[str] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)
    suggested_slide_role: str = "narrative"
    note: str = ""


class PlanningState(BaseModel):
    session_id: str
    mode: str = "agentic"
    status: str = "collecting_requirements"
    output_mode: str = "slidev"
    mode_selection_source: str = "default"
    brief: dict[str, Any] = Field(default_factory=dict)
    outline: dict[str, Any] = Field(default_factory=dict)
    outline_version: int = 0
    source_ids: list[str] = Field(default_factory=list)
    source_digest: str = ""
    outline_stale: bool = False
    active_job_id: str | None = None
    agent_workspace_root: str | None = None
    agent_session_version: int = 0
    assistant_status: str | None = None
    topic_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: str


class SessionDetail(BaseModel):
    session: SessionSummary
    sources: list[SourceMeta] = Field(default_factory=list)
    chat_messages: list[ChatRecord] = Field(default_factory=list)
    latest_presentation: dict | None = None
    latest_generation_job: LatestGenerationJobMeta | None = None
    planning_state: PlanningState | None = None

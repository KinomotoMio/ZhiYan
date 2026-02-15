"""Session API models."""

from pydantic import BaseModel, Field

from app.models.source import SourceMeta


class SessionSummary(BaseModel):
    id: str
    workspace_id: str
    title: str
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
    presentation: dict
    source: str | None = "editor"


class LatestGenerationJobMeta(BaseModel):
    job_id: str
    status: str
    updated_at: str


class SessionDetail(BaseModel):
    session: SessionSummary
    sources: list[SourceMeta] = Field(default_factory=list)
    chat_messages: list[ChatRecord] = Field(default_factory=list)
    latest_presentation: dict | None = None
    latest_generation_job: LatestGenerationJobMeta | None = None

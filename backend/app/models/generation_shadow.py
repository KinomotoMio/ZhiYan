"""Shadow/A-B evaluation records for generation v2 (C-plan Phase 2).

Records are persisted per job as JSON, and are safe to evolve (forward compatible).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.generation import now_iso


class ShadowRoute(BaseModel):
    enabled: bool = False
    shadow_engine: str = "internal_v2"
    sample_rate: float = 0.0
    sampled: bool = False
    strategy: str = "config"
    reason: str = ""
    decided_at: str = Field(default_factory=now_iso)


class EngineMetrics(BaseModel):
    engine_id: str
    status: str = "unknown"  # running | completed | failed | skipped
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    ttfs_ms: int | None = None

    stage_durations_ms: dict[str, int] = Field(default_factory=dict)
    llm_usage: dict[str, int] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)

    error_code: str | None = None
    error_message: str | None = None
    retriable: bool | None = None


class ShadowABRecord(BaseModel):
    job_id: str
    updated_at: str = Field(default_factory=now_iso)

    primary_engine: str = "internal_v2"
    shadow_route: ShadowRoute | None = None

    primary: EngineMetrics | None = None
    shadow: EngineMetrics | None = None

    deltas: dict[str, int | float | None] = Field(default_factory=dict)
    notes: dict[str, Any] = Field(default_factory=dict)


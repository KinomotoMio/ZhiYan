"""Engine router for generation (C-plan).

Phase 1 goal:
- Single routing entry point (auditable)
- Keep default internal pipeline behavior unchanged

Later phases can extend this router to support shadow/A-B and governance rules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import settings
from app.models.generation import GenerationJob, now_iso

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EngineRouteDecision:
    primary_engine: str
    strategy: str
    reason: str
    decided_at: str

    def to_metadata(self) -> dict[str, str]:
        return {
            "primary_engine": self.primary_engine,
            "strategy": self.strategy,
            "reason": self.reason,
            "decided_at": self.decided_at,
        }


def decide_engine_route(job: GenerationJob) -> EngineRouteDecision:
    """Return an engine route decision for this job.

    Default behavior is stable: internal_v2 unless explicitly configured otherwise.
    """
    configured = (getattr(settings, "generation_primary_engine", "") or "").strip().lower()
    primary = configured or "internal_v2"

    # Phase 1: keep a single, explicit decision record. Any smart routing rules can be
    # layered on later (complexity, template, source types, etc.).
    strategy = "config"
    reason = f"settings.generation_primary_engine={primary}"
    decision = EngineRouteDecision(
        primary_engine=primary,
        strategy=strategy,
        reason=reason,
        decided_at=now_iso(),
    )

    logger.info(
        "engine_route_decided",
        extra={
            "event": "engine_route_decided",
            "job_id": job.job_id,
            "primary_engine": decision.primary_engine,
            "strategy": decision.strategy,
            "reason": decision.reason,
        },
    )
    return decision


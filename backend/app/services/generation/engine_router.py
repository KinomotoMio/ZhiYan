"""Engine router for generation (C-plan).

Phase 1 goal:
- Single routing entry point (auditable)
- Keep default internal pipeline behavior unchanged

Later phases can extend this router to support shadow/A-B and governance rules.
"""

from __future__ import annotations

import hashlib
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


@dataclass(frozen=True)
class ShadowRouteDecision:
    enabled: bool
    shadow_engine: str
    sample_rate: float
    sampled: bool
    strategy: str
    reason: str
    decided_at: str

    def to_metadata(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "shadow_engine": self.shadow_engine,
            "sample_rate": self.sample_rate,
            "sampled": self.sampled,
            "strategy": self.strategy,
            "reason": self.reason,
            "decided_at": self.decided_at,
        }


def decide_shadow_route(job: GenerationJob) -> ShadowRouteDecision:
    """Return a deterministic shadow routing decision for this job.

    Shadow mode is used for evaluation: it must never affect the primary user-facing result.
    """
    enabled = bool(getattr(settings, "generation_shadow_enabled", False))
    shadow_engine = (getattr(settings, "generation_shadow_engine", "") or "").strip().lower() or "internal_v2"
    try:
        sample_rate = float(getattr(settings, "generation_shadow_sample_rate", 0.0) or 0.0)
    except (ValueError, TypeError):
        sample_rate = 0.0
    sample_rate = max(0.0, min(sample_rate, 1.0))

    strategy = "config"
    if not enabled or sample_rate <= 0:
        reason = f"settings.generation_shadow_enabled={enabled}, sample_rate={sample_rate:.3f}"
        decision = ShadowRouteDecision(
            enabled=enabled,
            shadow_engine=shadow_engine,
            sample_rate=sample_rate,
            sampled=False,
            strategy=strategy,
            reason=reason,
            decided_at=now_iso(),
        )
    else:
        # Deterministic sampling so retries/resumes stay comparable.
        digest = hashlib.md5((job.job_id or "").encode("utf-8")).hexdigest()  # noqa: S324
        bucket = int(digest[:8], 16) % 10_000
        threshold = int(sample_rate * 10_000)
        sampled = bucket < threshold
        reason = f"bucket={bucket}/10000 < threshold={threshold} (rate={sample_rate:.3f})"
        decision = ShadowRouteDecision(
            enabled=enabled,
            shadow_engine=shadow_engine,
            sample_rate=sample_rate,
            sampled=sampled,
            strategy=strategy,
            reason=reason,
            decided_at=now_iso(),
        )

    logger.info(
        "shadow_route_decided",
        extra={
            "event": "shadow_route_decided",
            "job_id": job.job_id,
            "enabled": decision.enabled,
            "shadow_engine": decision.shadow_engine,
            "sample_rate": decision.sample_rate,
            "sampled": decision.sampled,
            "strategy": decision.strategy,
            "reason": decision.reason,
        },
    )
    return decision

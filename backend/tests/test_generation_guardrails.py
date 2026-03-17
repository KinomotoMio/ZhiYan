import asyncio

from app.core.config import settings
from app.models.generation import GenerationJob, GenerationRequestData
from app.services.generation.engine_guard import EngineGuard, EngineGuardStore
from app.services.generation import engine_router


def _job(job_id: str = "job-guard") -> GenerationJob:
    return GenerationJob(
        job_id=job_id,
        request=GenerationRequestData(
            topic="t",
            content="c",
            resolved_content="c",
            num_pages=3,
        ),
        outline_accepted=True,
    )


def test_shadow_route_disabled_when_breaker_open(tmp_path, monkeypatch):
    async def _case():
        store = EngineGuardStore(tmp_path / "guard.json")
        guard = EngineGuard(store)
        monkeypatch.setattr(engine_router, "guard", guard)

        monkeypatch.setattr(settings, "generation_guardrails_enabled", True)
        monkeypatch.setattr(settings, "generation_shadow_enabled", True)
        monkeypatch.setattr(settings, "generation_shadow_engine", "internal_v2")
        monkeypatch.setattr(settings, "generation_shadow_sample_rate", 1.0)

        await guard.open(mode="shadow", engine_id="internal_v2", reason="test_open")

        decision = await engine_router.decide_shadow_route_with_guard(_job("job-shadow-guard"))
        assert decision.sampled is False
        assert "guard_open" in decision.reason

    asyncio.run(_case())


def test_primary_route_falls_back_when_breaker_open(tmp_path, monkeypatch):
    async def _case():
        store = EngineGuardStore(tmp_path / "guard.json")
        guard = EngineGuard(store)
        monkeypatch.setattr(engine_router, "guard", guard)

        monkeypatch.setattr(settings, "generation_guardrails_enabled", True)
        monkeypatch.setattr(settings, "generation_primary_engine", "presenton")

        await guard.open(mode="primary", engine_id="presenton", reason="test_open")

        decision = await engine_router.decide_engine_route_with_guard(_job("job-primary-guard"))
        assert decision.primary_engine == "internal_v2"
        assert decision.strategy == "guard_fallback"

    asyncio.run(_case())


def test_guard_store_opens_on_fail_rate(tmp_path, monkeypatch):
    async def _case():
        store = EngineGuardStore(tmp_path / "guard.json")
        guard = EngineGuard(store)
        monkeypatch.setattr(settings, "generation_guardrails_enabled", True)
        monkeypatch.setattr(settings, "generation_guard_fail_rate_threshold", 0.1)
        monkeypatch.setattr(settings, "generation_guard_window_size", 10)
        monkeypatch.setattr(settings, "generation_guard_min_samples", 1)

        for _ in range(5):
            decision = await guard.record(
                mode="shadow",
                engine_id="internal_v2",
                metrics={"status": "failed", "ttfs_ms": 1, "duration_ms": 2, "total_tokens": 3},
            )
        assert decision.open is True
        assert decision.allowed is False

    asyncio.run(_case())

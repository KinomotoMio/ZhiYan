import asyncio

from app.models.slide import Slide
from app.services.agents import layout_verifier
from app.services.pipeline.graph import PipelineState, stage_verify_slides


def test_stage_verify_slides_skips_slow_aesthetic_verification(monkeypatch):
    slide = Slide(
        slideId="slide-1",
        layoutType="intro-slide",
        layoutId="intro-slide",
        contentData={"title": "封面"},
        components=[],
    )

    async def slow_aesthetic(*args, **kwargs):  # noqa: ARG001
        await asyncio.sleep(0.05)
        return None

    monkeypatch.setattr(layout_verifier, "verify_programmatic", lambda slides: [])
    monkeypatch.setattr(layout_verifier, "run_aesthetic_verification", slow_aesthetic)

    state = PipelineState(topic="测试", slides=[slide])

    asyncio.run(
        stage_verify_slides(
            state,
            enable_vision=True,
            vision_timeout_seconds=0.05,
            aesthetic_timeout_seconds=0.01,
        )
    )

    assert any(issue["source"] == "aesthetic_timeout_fallback" for issue in state.verification_issues)
    assert all(issue["tier"] == "advisory" for issue in state.verification_issues)

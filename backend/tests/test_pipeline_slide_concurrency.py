import asyncio

import pytest

from app.core.config import settings
from app.services.pipeline import graph
from app.services.pipeline.graph import PipelineState, stage_generate_slides


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (3, 3),
        (0, 1),
        (-5, 1),
        (100, 20),
        ("2", 2),
        ("bad", 2),
        (None, 2),
    ],
)
def test_stage_generate_slides_uses_configured_concurrency(monkeypatch, configured, expected):
    async def _case():
        # Patch settings for this test run.
        monkeypatch.setattr(settings, "generation_slides_concurrency", configured, raising=False)

        captured: list[int] = []
        original_semaphore = graph.asyncio.Semaphore

        def _spy_semaphore(value: int):
            captured.append(int(value))
            return original_semaphore(value)

        monkeypatch.setattr(graph.asyncio, "Semaphore", _spy_semaphore)

        async def fake_generate_slide_content(**kwargs):  # noqa: ARG001
            return {"title": "T", "items": [{"title": "a", "description": "b"}]}

        monkeypatch.setattr(
            "app.services.agents.slide_generator.generate_slide_content",
            fake_generate_slide_content,
        )

        state = PipelineState(
            raw_content="x",
            topic="t",
            num_pages=2,
            job_id="job-test",
            outline={
                "items": [
                    {"slide_number": 1, "title": "S1"},
                    {"slide_number": 2, "title": "S2"},
                ]
            },
            layout_selections=[
                {"slide_number": 1, "layout_id": "bullet-with-icons"},
                {"slide_number": 2, "layout_id": "bullet-with-icons"},
            ],
        )

        await stage_generate_slides(state, per_slide_timeout=0.2)
        assert captured, "Semaphore should be constructed once per slides stage"
        assert captured[0] == expected

    asyncio.run(_case())


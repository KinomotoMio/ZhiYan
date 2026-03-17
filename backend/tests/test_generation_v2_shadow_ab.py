import asyncio
import time

from app.core.config import settings
from app.models.generation import GenerationJob, GenerationRequestData, JobStatus
from app.models.slide import Slide
from app.services.generation.event_bus import GenerationEventBus
from app.services.generation.job_store import GenerationJobStore
from app.services.generation.runner import GenerationRunner


def _build_job(job_id: str) -> GenerationJob:
    return GenerationJob(
        job_id=job_id,
        request=GenerationRequestData(
            topic="测试",
            content="测试内容",
            resolved_content="测试内容",
            num_pages=3,
        ),
        outline_accepted=True,
    )


def _patch_pipeline(monkeypatch):
    from app.services.pipeline import graph as graph_mod

    async def stub_parse(state, progress=None):  # noqa: ARG001
        state.document_metadata = {"char_count": 4, "estimated_tokens": 1, "heading_count": 0}

    async def stub_outline(state, progress=None):  # noqa: ARG001
        state.outline = {
            "items": [
                {"slide_number": 1, "title": "A", "key_points": []},
                {"slide_number": 2, "title": "B", "key_points": []},
                {"slide_number": 3, "title": "C", "key_points": []},
            ]
        }

    async def stub_layout(state, progress=None):  # noqa: ARG001
        state.layout_selections = [
            {"slide_number": 1, "layout_id": "bullet-with-icons"},
            {"slide_number": 2, "layout_id": "bullet-with-icons"},
            {"slide_number": 3, "layout_id": "bullet-with-icons"},
        ]

    async def stub_slides(state, *, per_slide_timeout, progress=None, on_slide=None):  # noqa: ARG001
        state.slide_contents = [
            {
                "slide_number": 1,
                "layout_id": "bullet-with-icons",
                "content_data": {"title": "A", "items": []},
            },
            {
                "slide_number": 2,
                "layout_id": "bullet-with-icons",
                "content_data": {"title": "B", "items": []},
            },
            {
                "slide_number": 3,
                "layout_id": "bullet-with-icons",
                "content_data": {"title": "C", "items": []},
            },
        ]
        if on_slide:
            slide = Slide(
                slideId="slide-1",
                layoutType="bullet-with-icons",
                layoutId="bullet-with-icons",
                contentData={"title": "A", "items": []},
                components=[],
            )
            await on_slide({"slide_index": 0, "slide": slide.model_dump(mode="json", by_alias=True)})

    async def stub_assets(state, progress=None):  # noqa: ARG001
        state.slides = [
            Slide(
                slideId=f"slide-{sc['slide_number']}",
                layoutType=sc["layout_id"],
                layoutId=sc["layout_id"],
                contentData=sc["content_data"],
                components=[],
            )
            for sc in state.slide_contents
        ]

    async def stub_verify(state, progress=None, enable_vision=True):  # noqa: ARG001
        state.verification_issues = []

    monkeypatch.setattr(graph_mod, "stage_parse_document", stub_parse)
    monkeypatch.setattr(graph_mod, "stage_generate_outline", stub_outline)
    monkeypatch.setattr(graph_mod, "stage_select_layouts", stub_layout)
    monkeypatch.setattr(graph_mod, "stage_generate_slides", stub_slides)
    monkeypatch.setattr(graph_mod, "stage_resolve_assets", stub_assets)
    monkeypatch.setattr(graph_mod, "stage_verify_slides", stub_verify)


def test_shadow_mode_generates_record_and_does_not_break_primary(monkeypatch, tmp_path):
    async def _case():
        store = GenerationJobStore(tmp_path / "jobs")
        bus = GenerationEventBus()
        runner = GenerationRunner(store, bus)
        _patch_pipeline(monkeypatch)

        monkeypatch.setattr(settings, "generation_shadow_enabled", True)
        monkeypatch.setattr(settings, "generation_shadow_engine", "internal_v2")
        monkeypatch.setattr(settings, "generation_shadow_sample_rate", 1.0)

        job = _build_job("job-shadow-ok")
        await store.create_job(job)
        await runner._run_job(job.job_id)  # noqa: SLF001

        loaded = await store.get_job(job.job_id)
        assert loaded is not None
        assert loaded.status == JobStatus.COMPLETED

        # Shadow task runs in background; poll until it finalizes or timeout.
        deadline = time.monotonic() + 1.0
        record = None
        while time.monotonic() < deadline:
            record = await store.get_shadow_record(loaded.job_id)
            if record and isinstance(record.get("shadow"), dict) and record["shadow"].get("status") != "running":
                break
            await asyncio.sleep(0.01)

        assert record is not None
        assert record.get("primary_engine") == "internal_v2"
        assert isinstance(record.get("primary"), dict)
        assert isinstance(record.get("shadow"), dict)
        assert record["primary"]["status"] == "completed"
        assert record["shadow"]["status"] == "completed"

    asyncio.run(_case())


def test_shadow_engine_failure_is_isolated(monkeypatch, tmp_path):
    async def _case():
        store = GenerationJobStore(tmp_path / "jobs")
        bus = GenerationEventBus()
        runner = GenerationRunner(store, bus)
        _patch_pipeline(monkeypatch)

        monkeypatch.setattr(settings, "generation_shadow_enabled", True)
        monkeypatch.setattr(settings, "generation_shadow_engine", "presenton")
        monkeypatch.setattr(settings, "generation_shadow_sample_rate", 1.0)

        job = _build_job("job-shadow-fail")
        await store.create_job(job)
        await runner._run_job(job.job_id)  # noqa: SLF001

        loaded = await store.get_job(job.job_id)
        assert loaded is not None
        assert loaded.status == JobStatus.COMPLETED

        record = await store.get_shadow_record(loaded.job_id)
        assert record is not None
        assert record.get("shadow", {}).get("status") in {"failed", "skipped"}
        assert record.get("shadow", {}).get("error_code") in {"ENGINE_UNSUPPORTED", "SKIPPED_OUTLINE_REVIEW"}

    asyncio.run(_case())


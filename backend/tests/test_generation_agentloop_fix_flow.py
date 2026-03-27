from __future__ import annotations

import asyncio

from app.models.generation import GenerationJob, GenerationRequestData, JobStatus, StageStatus
from app.services.generation.event_bus import GenerationEventBus
from app.services.generation.job_store import GenerationJobStore
from app.services.generation.runner import GenerationRunner


def _waiting_fix_job() -> GenerationJob:
    return GenerationJob(
        job_id="job-fix-flow",
        status=JobStatus.WAITING_FIX_REVIEW,
        current_stage=StageStatus.VERIFY,
        outline_accepted=True,
        request=GenerationRequestData(topic="修复测试", resolved_content="修复测试"),
        hard_issue_slide_ids=["slide-2"],
        slides=[
            {
                "slideId": "slide-1",
                "layoutType": "bullet-with-icons",
                "layoutId": "bullet-with-icons",
                "contentData": {"title": "第一页", "items": [{"title": "稳定", "description": "ok"}]},
                "components": [],
            },
            {
                "slideId": "slide-2",
                "layoutType": "metrics-slide",
                "layoutId": "metrics-slide",
                "contentData": {"title": "坏页", "metrics": []},
                "components": [],
            },
        ],
        issues=[
            {
                "slide_id": "slide-2",
                "tier": "hard",
                "severity": "error",
                "message": "metrics slide missing usable metrics",
            }
        ],
        failed_slide_indices=[1],
    )


def test_preview_and_apply_fix_only_updates_selected_slide(tmp_path):
    store = GenerationJobStore(tmp_path / "jobs")
    runner = GenerationRunner(store, GenerationEventBus())

    async def _case():
        job = _waiting_fix_job()
        await store.create_job(job)

        previewed = await runner.preview_fix(job.job_id)
        assert previewed.status == JobStatus.WAITING_FIX_REVIEW
        assert previewed.fix_preview_source_ids == ["slide-2"]
        assert previewed.fix_preview_slides[0]["slideId"] == "slide-2"
        assert previewed.fix_preview_slides[0]["layoutType"] == "bullet-with-icons"

        applied = await runner.apply_fix(job.job_id, slide_ids=["slide-2"])
        assert applied.status == JobStatus.COMPLETED
        assert applied.slides[0]["slideId"] == "slide-1"
        assert applied.slides[0]["layoutType"] == "bullet-with-icons"
        assert applied.slides[1]["slideId"] == "slide-2"
        assert applied.slides[1]["layoutType"] == "bullet-with-icons"
        assert applied.fix_preview_slides == []

    asyncio.run(_case())


def test_skip_fix_keeps_original_slides(tmp_path):
    store = GenerationJobStore(tmp_path / "jobs")
    runner = GenerationRunner(store, GenerationEventBus())

    async def _case():
        job = _waiting_fix_job()
        await store.create_job(job)

        skipped = await runner.skip_fix(job.job_id)
        assert skipped.status == JobStatus.COMPLETED
        assert skipped.slides[1]["layoutType"] == "metrics-slide"
        assert skipped.fix_preview_slides == []

    asyncio.run(_case())

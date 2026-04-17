from __future__ import annotations

import asyncio

from app.core.config import settings
from app.models.generation import GenerationJob, GenerationRequestData, JobStatus, PresentationOutputMode, StageStatus
from app.services.generation.event_bus import GenerationEventBus
from app.services.generation.job_store import GenerationJobStore
from app.services.generation.runner import GenerationRunner


def test_slidev_preview_and_apply_fix_persists_deck_level_preview(monkeypatch, tmp_path):
    store = GenerationJobStore(tmp_path / "jobs")
    runner = GenerationRunner(store, GenerationEventBus())
    monkeypatch.setattr(settings, "uploads_dir", tmp_path / "preview-root")

    preview_payload = {
        "preview_id": "spv-fix-job-slidev",
        "markdown": "---\ntitle: Slidev 修复版\n---\n\n# 修复封面\n",
        "meta": {
            "title": "Slidev 修复版",
            "slide_count": 1,
            "slides": [
                {
                    "index": 0,
                    "slide_id": "slide-1",
                    "title": "修复封面",
                    "role": "cover",
                    "layout": "cover",
                }
            ],
        },
        "selected_style_id": "tech-launch",
    }

    async def _fake_preview(**_kwargs):
        preview_root = settings.uploads_dir / "slidev-previews" / "spv-fix-job-slidev" / "dist"
        preview_root.mkdir(parents=True, exist_ok=True)
        (preview_root / "index.html").write_text("<html></html>", encoding="utf-8")
        return {
            **preview_payload,
            "preview_id": "spv-fix-job-slidev",
        }

    monkeypatch.setattr("app.services.generation.runner.create_slidev_preview", _fake_preview)

    async def _case():
        job = GenerationJob(
            job_id="job-slidev-fix-flow",
            status=JobStatus.WAITING_FIX_REVIEW,
            current_stage=StageStatus.VERIFY,
            outline_accepted=True,
            request=GenerationRequestData(
                topic="Slidev 修复测试",
                resolved_content="Slidev 修复测试",
            ),
            output_mode=PresentationOutputMode.SLIDEV,
            hard_issue_slide_ids=["slide-1"],
            issues=[
                {
                    "slide_id": "slide-1",
                    "tier": "hard",
                    "severity": "error",
                    "message": "deck needs repair",
                }
            ],
            document_metadata={
                "agent_outputs": {
                    "slidev_deck": {
                        "title": "原版",
                        "markdown": "---\ntitle: 原版\n---\n\n# 原封面\n",
                        "meta": {
                            "title": "原版",
                            "slide_count": 1,
                            "slides": [
                                {
                                    "index": 0,
                                    "slide_id": "slide-1",
                                    "title": "原封面",
                                    "role": "cover",
                                    "layout": "cover",
                                }
                            ],
                        },
                        "selected_style_id": "tech-launch",
                    }
                }
            },
        )
        await store.create_job(job)

        previewed = await runner.preview_fix(job.job_id)
        assert previewed.status == JobStatus.WAITING_FIX_REVIEW
        assert previewed.fix_preview_slides == []
        assert previewed.fix_preview_source_ids == ["slide-1"]
        assert previewed.fix_preview_slidev is not None
        assert previewed.fix_preview_slidev["preview_url"] == "/api/v1/slidev-previews/spv-fix-job-slidev"

        applied = await runner.apply_fix(job.job_id, slide_ids=["slide-1"])
        assert applied.status == JobStatus.COMPLETED
        assert applied.fix_preview_slidev is None
        assert applied.fix_preview_source_ids == []
        assert applied.document_metadata["agent_outputs"]["slidev_deck"]["markdown"] == preview_payload["markdown"].strip()
        assert applied.document_metadata["agent_outputs"]["slidev_build"]["build_root"].endswith("/spv-fix-job-slidev/dist")

    asyncio.run(_case())

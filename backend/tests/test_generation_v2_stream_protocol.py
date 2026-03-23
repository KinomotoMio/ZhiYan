import json
import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models.generation import EventType, TERMINAL_EVENTS
from app.models.slide import Slide
from app.services.generation.event_bus import GenerationEventBus
from app.services.generation.job_store import GenerationJobStore
from app.services.generation.runner import GenerationRunner


def _install_runtime(monkeypatch, tmp_path: Path) -> tuple[GenerationJobStore, GenerationRunner]:
    store = GenerationJobStore(tmp_path / "jobs")
    bus = GenerationEventBus()
    runner = GenerationRunner(store, bus)

    from app.api.v2 import generation as generation_api

    monkeypatch.setattr(generation_api, "job_store", store)
    monkeypatch.setattr(generation_api, "event_bus", bus)
    monkeypatch.setattr(generation_api, "generation_runner", runner)
    return store, runner


def _patch_fast_pipeline(monkeypatch):
    from app.services.generation import runner as runner_mod

    async def fake_parse(state, progress=None):
        if progress:
            await progress("parse", 1, 6, "解析文档...")
        state.document_metadata = {"char_count": len(state.raw_content)}

    async def fake_outline(state, progress=None):
        if progress:
            await progress("outline", 2, 6, "生成大纲...")
        state.outline = {
            "items": [
                {
                    "slide_number": 1,
                    "title": "封面",
                    "suggested_slide_role": "cover",
                    "key_points": [],
                },
                {
                    "slide_number": 2,
                    "title": "内容",
                    "suggested_slide_role": "narrative",
                    "key_points": ["要点一", "要点二"],
                },
            ]
        }

    async def fake_layout(state, progress=None):
        if progress:
            await progress("layout", 3, 6, "选择布局...")
        state.layout_selections = [
            {"slide_number": 1, "layout_id": "intro-slide"},
            {"slide_number": 2, "layout_id": "bullet-with-icons"},
        ]

    async def fake_slides(state, per_slide_timeout, progress=None, on_slide=None):  # noqa: ARG001
        if progress:
            await progress("slides", 4, 6, "生成幻灯片...")
        state.slide_contents = [
            {"slide_number": 1, "layout_id": "intro-slide", "content_data": {"title": "封面"}},
            {
                "slide_number": 2,
                "layout_id": "bullet-with-icons",
                "content_data": {"title": "内容", "items": [{"title": "要点一", "description": "说明"}]},
            },
        ]
        state.slides = [
            Slide(
                slideId="slide-1",
                layoutType="intro-slide",
                layoutId="intro-slide",
                contentData={"title": "封面"},
                components=[],
            ),
            Slide(
                slideId="slide-2",
                layoutType="bullet-with-icons",
                layoutId="bullet-with-icons",
                contentData={"title": "内容", "items": [{"title": "要点一", "description": "说明"}]},
                components=[],
            ),
        ]
        if on_slide:
            await on_slide({"slide_index": 0, "slide": state.slides[0].model_dump(mode="json", by_alias=True)})
            await on_slide({"slide_index": 1, "slide": state.slides[1].model_dump(mode="json", by_alias=True)})

    async def fake_assets(state, progress=None):
        if progress:
            await progress("assets", 5, 6, "处理资源...")

    async def fake_verify(state, progress=None, enable_vision=True):  # noqa: ARG001
        if progress:
            await progress("verify", 6, 6, "验证布局质量...")
        state.verification_issues = []

    async def fake_fix(state, per_slide_timeout, progress=None, on_slide=None):  # noqa: ARG001
        if progress:
            await progress("fix", 6, 6, "修复页面...")

    monkeypatch.setattr(runner_mod, "stage_parse_document", fake_parse)
    monkeypatch.setattr(runner_mod, "stage_generate_outline", fake_outline)
    monkeypatch.setattr(runner_mod, "stage_select_layouts", fake_layout)
    monkeypatch.setattr(runner_mod, "stage_generate_slides", fake_slides)
    monkeypatch.setattr(runner_mod, "stage_resolve_assets", fake_assets)
    monkeypatch.setattr(runner_mod, "stage_verify_slides", fake_verify)
    monkeypatch.setattr(runner_mod, "stage_fix_slides_once", fake_fix)


def test_generation_v2_stream_protocol_sequence(monkeypatch, tmp_path):
    _, runner = _install_runtime(monkeypatch, tmp_path)
    _patch_fast_pipeline(monkeypatch)

    async def run_inline(job_id: str, from_stage=None):
        await runner._run_job(job_id, from_stage)  # noqa: SLF001
        return True

    monkeypatch.setattr(runner, "start_job", run_inline)

    client = TestClient(app)
    create_resp = client.post(
        "/api/v2/generation/jobs",
        json={"topic": "测试主题", "content": "测试内容", "num_pages": 2, "mode": "auto"},
    )
    assert create_resp.status_code == 200
    job_id = create_resp.json()["job_id"]

    events: list[dict] = []
    done_count = 0
    with client.stream("GET", f"/api/v2/generation/jobs/{job_id}/events") as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                done_count += 1
                break
            events.append(json.loads(data))

    assert done_count == 1
    assert events

    seqs = [evt["seq"] for evt in events]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)

    types = [evt["type"] for evt in events]
    assert EventType.JOB_STARTED.value in types
    assert EventType.OUTLINE_READY.value in types
    assert EventType.LAYOUT_READY.value in types
    assert EventType.SLIDE_READY.value in types
    terminal = [t for t in types if t in {et.value for et in TERMINAL_EVENTS}]
    assert len(terminal) == 1
    assert terminal[0] == EventType.JOB_COMPLETED.value

    snapshot = client.get(f"/api/v2/generation/jobs/{job_id}")
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["status"] == "completed"
    assert len(body["slides"]) == 2


def test_generation_v2_stream_protocol_heartbeat(monkeypatch, tmp_path):
    store, runner = _install_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "sse_heartbeat_seconds", 0.1)

    async def no_start(job_id: str, from_stage=None):  # noqa: ARG001
        return True

    monkeypatch.setattr(runner, "start_job", no_start)

    from app.api.v2 import generation as generation_api
    from app.models.generation import GenerationJob, GenerationRequestData

    async def _case():
        job = GenerationJob(
            job_id="job-heartbeat",
            request=GenerationRequestData(topic="心跳测试", resolved_content="测试内容"),
            outline_accepted=True,
        )
        await store.create_job(job)
        response = await generation_api.stream_job_events(job.job_id)
        chunk = await asyncio.wait_for(response.body_iterator.__anext__(), timeout=1.0)
        text = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
        await response.body_iterator.aclose()
        return text

    first_chunk = asyncio.run(_case())
    assert EventType.HEARTBEAT.value in first_chunk


def test_generation_v2_stream_after_seq_skips_old_terminal_event(monkeypatch, tmp_path):
    store, _runner = _install_runtime(monkeypatch, tmp_path)

    from app.api.v2 import generation as generation_api
    from app.models.generation import GenerationEvent, GenerationJob, GenerationRequestData, StageStatus

    async def _case():
        job = GenerationJob(
            job_id="job-after-seq",
            request=GenerationRequestData(topic="续流测试", resolved_content="测试内容"),
            outline_accepted=True,
        )
        await store.create_job(job)
        await store.append_event(
            GenerationEvent(seq=1, type=EventType.JOB_FAILED, job_id=job.job_id, message="old failure")
        )

        response = await generation_api.stream_job_events(job.job_id, after_seq=1)

        async def publish_live_events():
            await asyncio.sleep(0.05)
            evt2 = GenerationEvent(
                seq=2,
                type=EventType.STAGE_STARTED,
                job_id=job.job_id,
                stage=StageStatus.VERIFY,
                message="verify retry",
            )
            evt3 = GenerationEvent(
                seq=3,
                type=EventType.JOB_COMPLETED,
                job_id=job.job_id,
                message="done",
            )
            await store.append_event(evt2)
            await store.append_event(evt3)
            await generation_api.event_bus.publish(evt2)
            await generation_api.event_bus.publish(evt3)

        publish_task = asyncio.create_task(publish_live_events())
        chunks: list[str] = []
        try:
            while True:
                chunk = await asyncio.wait_for(response.body_iterator.__anext__(), timeout=1.0)
                text = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
                chunks.append(text)
                if "[DONE]" in text:
                    break
        finally:
            await response.body_iterator.aclose()
            await publish_task

        body = "".join(chunks)
        assert '"type": "job_failed"' not in body
        assert '"type": "stage_started"' in body
        assert '"type": "job_completed"' in body
        assert "[DONE]" in body

    asyncio.run(_case())


def test_generation_v2_stream_waiting_fix_review_is_terminal(monkeypatch, tmp_path):
    store, _runner = _install_runtime(monkeypatch, tmp_path)

    from app.api.v2 import generation as generation_api
    from app.models.generation import GenerationEvent, GenerationJob, GenerationRequestData, StageStatus

    async def _case():
        job = GenerationJob(
            job_id="job-waiting-fix-stream",
            request=GenerationRequestData(topic="待修复", resolved_content="测试内容"),
            outline_accepted=True,
        )
        await store.create_job(job)
        await store.append_event(
            GenerationEvent(
                seq=1,
                type=EventType.STAGE_STARTED,
                job_id=job.job_id,
                stage=StageStatus.VERIFY,
                message="verify",
            )
        )
        await store.append_event(
            GenerationEvent(
                seq=2,
                type=EventType.JOB_WAITING_FIX_REVIEW,
                job_id=job.job_id,
                stage=StageStatus.VERIFY,
                message="waiting review",
                payload={"hard_issue_slide_ids": ["slide-1"], "advisory_issue_count": 1},
            )
        )

        response = await generation_api.stream_job_events(job.job_id)
        chunks: list[str] = []
        try:
            while True:
                chunk = await asyncio.wait_for(response.body_iterator.__anext__(), timeout=1.0)
                text = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
                chunks.append(text)
                if "[DONE]" in text:
                    break
        finally:
            await response.body_iterator.aclose()

        body = "".join(chunks)
        assert '"type": "stage_started"' in body
        assert '"type": "job_waiting_fix_review"' in body
        assert "[DONE]" in body

    asyncio.run(_case())

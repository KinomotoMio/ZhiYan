import asyncio

import httpx

from app.core.config import settings
from app.models.generation import (
    EventType,
    GenerationEvent,
    GenerationJob,
    GenerationRequestData,
    JobStatus,
    StageStatus,
)
from app.services.generation.event_bus import GenerationEventBus
from app.services.generation.job_store import GenerationJobStore
from app.services.generation.runner import GenerationRunner
from app.services.pipeline.graph import PipelineState, stage_generate_slides
from app.services.sessions.store import SessionStore


def _build_job(job_id: str = "job-test") -> GenerationJob:
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


def test_job_store_persists_job_and_events(tmp_path):
    async def _case():
        store = GenerationJobStore(tmp_path / "jobs")
        job = _build_job("job-1")
        await store.create_job(job)

        loaded = await store.get_job("job-1")
        assert loaded is not None
        assert loaded.job_id == "job-1"

        await store.append_event(
            GenerationEvent(seq=2, type=EventType.STAGE_PROGRESS, job_id="job-1", payload={"step": 1})
        )
        await store.append_event(
            GenerationEvent(seq=1, type=EventType.JOB_STARTED, job_id="job-1")
        )
        events = await store.list_events("job-1")
        assert [e.seq for e in events] == [1, 2]

    asyncio.run(_case())


def test_event_bus_broadcasts_to_subscribers():
    async def _case():
        bus = GenerationEventBus()
        q1 = await bus.subscribe("job-1")
        q2 = await bus.subscribe("job-1")

        event = GenerationEvent(seq=1, type=EventType.JOB_STARTED, job_id="job-1")
        await bus.publish(event)

        got1 = await asyncio.wait_for(q1.get(), timeout=0.2)
        got2 = await asyncio.wait_for(q2.get(), timeout=0.2)
        assert got1.seq == 1
        assert got2.seq == 1

        await bus.unsubscribe("job-1", q1)
        await bus.unsubscribe("job-1", q2)

    asyncio.run(_case())


def test_stage_timeout_emits_stage_failed_event(tmp_path):
    async def _case():
        store = GenerationJobStore(tmp_path / "jobs")
        bus = GenerationEventBus()
        runner = GenerationRunner(store, bus)

        job = _build_job("job-timeout")
        await store.create_job(job)

        state = PipelineState(raw_content="x", topic="t", num_pages=3, job_id=job.job_id)

        async def slow_stage():
            await asyncio.sleep(0.05)

        try:
            await runner._run_stage(  # noqa: SLF001
                job,
                state,
                stage=StageStatus.OUTLINE,
                timeout=0.01,
                stage_coro=slow_stage(),
            )
        except TimeoutError:
            pass
        else:
            assert False, "expected timeout"

        reloaded = await store.get_job(job.job_id)
        assert reloaded is not None
        assert reloaded.stage_results
        assert reloaded.stage_results[-1].stage == StageStatus.OUTLINE
        assert reloaded.stage_results[-1].status == "failed"
        assert reloaded.stage_results[-1].error_code == "STAGE_TIMEOUT"
        assert reloaded.stage_results[-1].retriable is True

        events = await store.list_events(job.job_id)
        failed_events = [e for e in events if e.type == EventType.STAGE_FAILED]
        assert failed_events
        payload = failed_events[-1].payload
        assert payload["error_code"] == "STAGE_TIMEOUT"
        assert payload["timeout_seconds"] == 0.01
        assert payload["stage"] == "outline"
        started_events = [e for e in events if e.type == EventType.STAGE_STARTED]
        assert started_events
        assert started_events[-1].payload["stage_timeout_seconds"] == 0.01
        assert isinstance(started_events[-1].payload["started_at"], str)

    asyncio.run(_case())


def test_outline_provider_timeout_classification(monkeypatch, tmp_path):
    async def _case():
        store = GenerationJobStore(tmp_path / "jobs")
        bus = GenerationEventBus()
        runner = GenerationRunner(store, bus)
        job = _build_job("job-provider-timeout")
        await store.create_job(job)

        from app.services.generation import runner as runner_mod

        async def fail_outline(state, progress=None):  # noqa: ARG001
            raise httpx.TimeoutException("provider timeout")

        monkeypatch.setattr(runner_mod, "stage_generate_outline", fail_outline)
        await runner._run_job(job.job_id, from_stage=StageStatus.OUTLINE)  # noqa: SLF001

        loaded = await store.get_job(job.job_id)
        assert loaded is not None
        assert loaded.status == JobStatus.FAILED

        events = await store.list_events(job.job_id)
        job_failed = [evt for evt in events if evt.type == EventType.JOB_FAILED]
        assert job_failed
        assert job_failed[-1].payload["error_code"] == "PROVIDER_TIMEOUT"

    asyncio.run(_case())


def test_outline_provider_network_classification(monkeypatch, tmp_path):
    async def _case():
        store = GenerationJobStore(tmp_path / "jobs")
        bus = GenerationEventBus()
        runner = GenerationRunner(store, bus)
        job = _build_job("job-provider-network")
        await store.create_job(job)

        from app.services.generation import runner as runner_mod

        async def fail_outline(state, progress=None):  # noqa: ARG001
            raise httpx.ConnectError("dns failed")

        monkeypatch.setattr(runner_mod, "stage_generate_outline", fail_outline)
        await runner._run_job(job.job_id, from_stage=StageStatus.OUTLINE)  # noqa: SLF001

        loaded = await store.get_job(job.job_id)
        assert loaded is not None
        assert loaded.status == JobStatus.FAILED

        events = await store.list_events(job.job_id)
        job_failed = [evt for evt in events if evt.type == EventType.JOB_FAILED]
        assert job_failed
        assert job_failed[-1].payload["error_code"] == "PROVIDER_NETWORK"

    asyncio.run(_case())


def test_no_fallback_on_outline_timeout(monkeypatch, tmp_path):
    async def _case():
        store = GenerationJobStore(tmp_path / "jobs")
        bus = GenerationEventBus()
        runner = GenerationRunner(store, bus)
        job = _build_job("job-outline-timeout")
        await store.create_job(job)

        from app.services.generation import runner as runner_mod

        async def slow_outline(state, progress=None):  # noqa: ARG001
            await asyncio.sleep(0.05)

        monkeypatch.setattr(settings, "outline_timeout_seconds", 0.01)
        monkeypatch.setattr(runner_mod, "stage_generate_outline", slow_outline)
        await runner._run_job(job.job_id, from_stage=StageStatus.OUTLINE)  # noqa: SLF001

        loaded = await store.get_job(job.job_id)
        assert loaded is not None
        assert loaded.status == JobStatus.FAILED

        events = await store.list_events(job.job_id)
        stage_started_stages = [
            evt.stage.value
            for evt in events
            if evt.type == EventType.STAGE_STARTED and evt.stage is not None
        ]
        assert stage_started_stages == ["outline"]
        job_failed = [evt for evt in events if evt.type == EventType.JOB_FAILED]
        assert job_failed
        assert job_failed[-1].payload["error_code"] == "STAGE_TIMEOUT"

    asyncio.run(_case())


def test_verify_timeout_persists_partial_presentation_and_emits_payload(monkeypatch, tmp_path):
    async def _case():
        store = GenerationJobStore(tmp_path / "jobs")
        bus = GenerationEventBus()
        runner = GenerationRunner(store, bus)

        session_store = SessionStore(tmp_path / "sessions.db", tmp_path / "uploads")
        await session_store.init()
        await session_store.ensure_workspace("ws-runtime")
        session = await session_store.create_session("ws-runtime", "生成会话")

        from app.services.generation import runner as runner_mod
        import app.services.sessions as sessions_pkg

        async def fake_parse(state, progress=None):  # noqa: ARG001
            state.document_metadata = {"char_count": len(state.raw_content)}

        async def fake_outline(state, progress=None):  # noqa: ARG001
            state.outline = {
                "items": [
                    {
                        "slide_number": 1,
                        "title": "封面",
                        "suggested_layout_category": "intro",
                        "key_points": [],
                    }
                ]
            }

        async def fake_layout(state, progress=None):  # noqa: ARG001
            state.layout_selections = [{"slide_number": 1, "layout_id": "intro-slide"}]

        async def fake_slides(state, per_slide_timeout, progress=None, on_slide=None):  # noqa: ARG001
            state.slide_contents = [
                {"slide_number": 1, "layout_id": "intro-slide", "content_data": {"title": "封面"}}
            ]

        async def fake_assets(state, progress=None):  # noqa: ARG001
            from app.models.slide import Slide

            state.slides = [
                Slide(
                    slideId="slide-1",
                    layoutType="intro-slide",
                    layoutId="intro-slide",
                    contentData={"title": "封面"},
                    components=[],
                )
            ]

        async def slow_verify(state, progress=None, enable_vision=True):  # noqa: ARG001
            await asyncio.sleep(0.05)

        originals = (
            runner_mod.stage_parse_document,
            runner_mod.stage_generate_outline,
            runner_mod.stage_select_layouts,
            runner_mod.stage_generate_slides,
            runner_mod.stage_resolve_assets,
            runner_mod.stage_verify_slides,
            sessions_pkg.session_store,
            settings.verify_timeout_seconds,
        )
        runner_mod.stage_parse_document = fake_parse
        runner_mod.stage_generate_outline = fake_outline
        runner_mod.stage_select_layouts = fake_layout
        runner_mod.stage_generate_slides = fake_slides
        runner_mod.stage_resolve_assets = fake_assets
        runner_mod.stage_verify_slides = slow_verify
        monkeypatch.setattr(sessions_pkg, "session_store", session_store)
        monkeypatch.setattr(settings, "verify_timeout_seconds", 0.01)
        try:
            job = GenerationJob(
                job_id="job-verify-timeout-partial",
                request=GenerationRequestData(
                    topic="测试",
                    content="测试内容",
                    resolved_content="测试内容",
                    num_pages=3,
                    session_id=session["id"],
                    title="测试主题",
                ),
                outline_accepted=True,
            )
            await store.create_job(job)
            await runner._run_job(job.job_id, from_stage=StageStatus.PARSE)  # noqa: SLF001

            loaded = await store.get_job(job.job_id)
            assert loaded is not None
            assert loaded.status == JobStatus.FAILED
            assert loaded.presentation is not None
            assert loaded.presentation.get("slides")

            latest = await session_store.get_latest_presentation("ws-runtime", session["id"])
            assert latest is not None
            assert latest["presentation"]["slides"]

            events = await store.list_events(job.job_id)
            job_failed = [evt for evt in events if evt.type == EventType.JOB_FAILED]
            assert job_failed
            payload = job_failed[-1].payload
            assert payload["partial_saved"] is True
            assert isinstance(payload.get("presentation"), dict)
            assert payload["presentation"].get("slides")
        finally:
            (
                runner_mod.stage_parse_document,
                runner_mod.stage_generate_outline,
                runner_mod.stage_select_layouts,
                runner_mod.stage_generate_slides,
                runner_mod.stage_resolve_assets,
                runner_mod.stage_verify_slides,
                _,
                _,
            ) = originals
            monkeypatch.setattr(sessions_pkg, "session_store", originals[6])
            monkeypatch.setattr(settings, "verify_timeout_seconds", originals[7])

    asyncio.run(_case())


def test_two_column_compare_fallback_shape_on_slide_generation_error(monkeypatch):
    async def _case():
        from app.services.agents import slide_generator

        async def always_fail(**kwargs):  # noqa: ARG001
            raise RuntimeError("mock slide generation failure")

        monkeypatch.setattr(slide_generator, "generate_slide_content", always_fail)

        state = PipelineState(
            raw_content="测试内容",
            topic="测试主题",
            num_pages=3,
            job_id="job-fallback-shape",
            outline={
                "items": [
                    {
                        "slide_number": 1,
                        "title": "对比页",
                        "key_points": ["要点一", "要点二", "要点三", "要点四"],
                    }
                ]
            },
            layout_selections=[{"slide_number": 1, "layout_id": "two-column-compare"}],
        )

        await stage_generate_slides(state, per_slide_timeout=0.2)
        assert state.slide_contents
        content = state.slide_contents[0]["content_data"]
        assert isinstance(content, dict)
        assert "left" in content
        assert "right" in content
        assert isinstance(content["left"], dict)
        assert isinstance(content["right"], dict)
        assert isinstance(content["left"].get("items"), list)
        assert isinstance(content["right"].get("items"), list)

    asyncio.run(_case())


def test_cancel_semantics_sets_terminal_status(tmp_path):
    async def _case():
        store = GenerationJobStore(tmp_path / "jobs")
        bus = GenerationEventBus()
        runner = GenerationRunner(store, bus)

        from app.services.generation import runner as runner_mod

        async def slow_parse(state, progress=None):  # noqa: ARG001
            await asyncio.sleep(0.2)

        async def fake_outline(state, progress=None):  # noqa: ARG001
            state.outline = {"items": []}

        async def fake_layout(state, progress=None):  # noqa: ARG001
            state.layout_selections = []

        async def fake_slides(state, per_slide_timeout, progress=None, on_slide=None):  # noqa: ARG001
            state.slide_contents = []

        async def fake_assets(state, progress=None):  # noqa: ARG001
            state.slides = []

        async def fake_verify(state, progress=None, enable_vision=True):  # noqa: ARG001
            state.verification_issues = []

        async def fake_fix(state, per_slide_timeout, progress=None, on_slide=None):  # noqa: ARG001
            return None

        originals = (
            runner_mod.stage_parse_document,
            runner_mod.stage_generate_outline,
            runner_mod.stage_select_layouts,
            runner_mod.stage_generate_slides,
            runner_mod.stage_resolve_assets,
            runner_mod.stage_verify_slides,
            runner_mod.stage_fix_slides_once,
        )
        runner_mod.stage_parse_document = slow_parse
        runner_mod.stage_generate_outline = fake_outline
        runner_mod.stage_select_layouts = fake_layout
        runner_mod.stage_generate_slides = fake_slides
        runner_mod.stage_resolve_assets = fake_assets
        runner_mod.stage_verify_slides = fake_verify
        runner_mod.stage_fix_slides_once = fake_fix
        try:
            job = _build_job("job-cancel")
            await store.create_job(job)

            started = await runner.start_job(job.job_id, from_stage=StageStatus.PARSE)
            assert started is True
            await asyncio.sleep(0.03)
            await runner.cancel_job(job.job_id)
            await asyncio.sleep(0.05)

            loaded = await store.get_job(job.job_id)
            assert loaded is not None
            assert loaded.status in {JobStatus.CANCELLED, JobStatus.RUNNING}

            # Wait for cancellation to settle
            for _ in range(20):
                loaded = await store.get_job(job.job_id)
                if loaded and loaded.status == JobStatus.CANCELLED:
                    break
                await asyncio.sleep(0.02)

            loaded = await store.get_job(job.job_id)
            assert loaded is not None
            assert loaded.status == JobStatus.CANCELLED

            events = await store.list_events(job.job_id)
            assert any(evt.type == EventType.JOB_CANCELLED for evt in events)
        finally:
            (
                runner_mod.stage_parse_document,
                runner_mod.stage_generate_outline,
                runner_mod.stage_select_layouts,
                runner_mod.stage_generate_slides,
                runner_mod.stage_resolve_assets,
                runner_mod.stage_verify_slides,
                runner_mod.stage_fix_slides_once,
            ) = originals

    asyncio.run(_case())

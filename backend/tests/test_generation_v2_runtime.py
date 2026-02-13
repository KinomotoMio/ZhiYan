import asyncio

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
from app.services.pipeline.graph import PipelineState


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

        events = await store.list_events(job.job_id)
        assert any(e.type == EventType.STAGE_FAILED for e in events)

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

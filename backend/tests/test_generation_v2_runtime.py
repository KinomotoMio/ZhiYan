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
from app.models.slide import Slide
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


def _slide_payload(slide_id: str, title: str) -> dict:
    return {
        "slideId": slide_id,
        "layoutType": "bullet-with-icons",
        "layoutId": "bullet-with-icons",
        "contentData": {
            "title": title,
            "items": [{"title": "要点", "description": "说明"}],
        },
        "components": [],
    }


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
                        "suggested_slide_role": "cover",
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


def test_verify_soft_timeout_completes_job_with_warning(monkeypatch, tmp_path):
    async def _case():
        store = GenerationJobStore(tmp_path / "jobs")
        bus = GenerationEventBus()
        runner = GenerationRunner(store, bus)

        session_store = SessionStore(tmp_path / "sessions.db", tmp_path / "uploads")
        await session_store.init()
        await session_store.ensure_workspace("ws-runtime")
        session = await session_store.create_session("ws-runtime", "生成会话")

        from app.services.agents import layout_verifier
        from app.services.generation import runner as runner_mod
        from app.services.pipeline import graph as graph_mod
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

        async def fake_verify(state, progress=None, enable_vision=True):  # noqa: ARG001
            await graph_mod.stage_verify_slides(
                state,
                progress=progress,
                enable_vision=enable_vision,
                vision_timeout_seconds=0.05,
                aesthetic_timeout_seconds=0.01,
            )

        async def slow_aesthetic(*args, **kwargs):  # noqa: ARG001
            await asyncio.sleep(0.05)
            return None

        monkeypatch.setattr(sessions_pkg, "session_store", session_store)
        monkeypatch.setattr(runner_mod, "stage_parse_document", fake_parse)
        monkeypatch.setattr(runner_mod, "stage_generate_outline", fake_outline)
        monkeypatch.setattr(runner_mod, "stage_select_layouts", fake_layout)
        monkeypatch.setattr(runner_mod, "stage_generate_slides", fake_slides)
        monkeypatch.setattr(runner_mod, "stage_resolve_assets", fake_assets)
        monkeypatch.setattr(runner_mod, "stage_verify_slides", fake_verify)
        monkeypatch.setattr(layout_verifier, "verify_programmatic", lambda slides: [])
        monkeypatch.setattr(layout_verifier, "run_aesthetic_verification", slow_aesthetic)

        job = GenerationJob(
            job_id="job-verify-soft-timeout",
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
        assert loaded.status == JobStatus.COMPLETED
        assert loaded.presentation is not None
        assert any(issue["source"] == "aesthetic_timeout_fallback" for issue in loaded.issues)

        events = await store.list_events(job.job_id)
        job_failed = [evt for evt in events if evt.type == EventType.JOB_FAILED]
        assert job_failed == []
        completed = [evt for evt in events if evt.type == EventType.JOB_COMPLETED]
        assert completed

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


def test_bullet_with_icons_fallback_uses_explicit_status_when_points_are_missing():
    from app.services.pipeline.graph import _fallback_content

    content = _fallback_content(
        {
            "title": "关键结论",
            "key_points": [],
        },
        "bullet-with-icons",
    )

    assert content["title"] == "关键结论"
    assert content["items"] == []
    assert content["status"] == {
        "title": "内容暂未就绪",
        "message": "该页正在生成或已回退，可稍后重试。",
    }


def test_stage_generate_slides_uses_per_slide_context(monkeypatch):
    async def _case():
        from app.services.agents import slide_generator

        captured_source: list[str] = []
        captured_refs: list[list[str]] = []

        async def fake_generate(**kwargs):
            captured_source.append(str(kwargs.get("source_content", "")))
            captured_refs.append(list(kwargs.get("source_references") or []))
            return {"title": kwargs.get("title", ""), "items": [{"title": "要点", "description": "说明"}]}

        monkeypatch.setattr(slide_generator, "generate_slide_content", fake_generate)

        raw_content = (
            "苹果战略：聚焦品牌升级与渠道优化，强调高端客群。\n\n"
            "香蕉供应链：围绕冷链、仓配协同和损耗控制，强调成本效率。\n\n"
            "葡萄营销：针对社媒内容与达人合作，强调转化闭环。"
        )
        state = PipelineState(
            raw_content=raw_content,
            topic="测试主题",
            num_pages=3,
            job_id="job-source-context",
            outline={
                "items": [
                    {
                        "slide_number": 1,
                        "title": "苹果战略",
                        "content_brief": "介绍苹果品牌策略",
                        "key_points": ["苹果", "品牌升级"],
                        "source_references": ["source:apple#1"],
                    },
                    {
                        "slide_number": 2,
                        "title": "香蕉供应链",
                        "content_brief": "介绍香蕉供应链优化",
                        "key_points": ["香蕉", "冷链"],
                        "source_references": ["source:banana#2", "chunk:banana#5"],
                    },
                ]
            },
            layout_selections=[
                {"slide_number": 1, "layout_id": "bullet-with-icons"},
                {"slide_number": 2, "layout_id": "bullet-with-icons"},
            ],
        )

        await stage_generate_slides(state, per_slide_timeout=0.5)
        assert len(captured_source) == 2
        assert len(captured_refs) == 2
        assert captured_source[0] != captured_source[1]
        assert "苹果" in captured_source[0]
        assert "香蕉" in captured_source[1]
        assert captured_refs[0] == ["source:apple#1"]
        assert captured_refs[1] == ["source:banana#2", "chunk:banana#5"]

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


def test_verify_hard_issues_enters_waiting_fix_review(monkeypatch, tmp_path):
    async def _case():
        store = GenerationJobStore(tmp_path / "jobs")
        bus = GenerationEventBus()
        runner = GenerationRunner(store, bus)

        from app.services.generation import runner as runner_mod

        async def fake_parse(state, progress=None):  # noqa: ARG001
            state.document_metadata = {"char_count": len(state.raw_content)}

        async def fake_outline(state, progress=None):  # noqa: ARG001
            state.outline = {
                "items": [
                    {
                        "slide_number": 1,
                        "title": "第一页",
                        "key_points": [],
                    },
                    {
                        "slide_number": 2,
                        "title": "第二页",
                        "key_points": [],
                    },
                ]
            }

        async def fake_layout(state, progress=None):  # noqa: ARG001
            state.layout_selections = [
                {"slide_number": 1, "layout_id": "bullet-with-icons"},
                {"slide_number": 2, "layout_id": "bullet-with-icons"},
            ]

        async def fake_slides(state, per_slide_timeout, progress=None, on_slide=None):  # noqa: ARG001
            state.slide_contents = [
                {"slide_number": 1, "layout_id": "bullet-with-icons", "content_data": {"title": "第一页"}},
                {"slide_number": 2, "layout_id": "bullet-with-icons", "content_data": {"title": "第二页"}},
            ]

        async def fake_assets(state, progress=None):  # noqa: ARG001
            state.slides = [
                Slide.model_validate(_slide_payload("slide-1", "第一页")),
                Slide.model_validate(_slide_payload("slide-2", "第二页")),
            ]

        async def fake_verify(state, progress=None, enable_vision=True):  # noqa: ARG001
            state.verification_issues = [
                {
                    "slide_id": "slide-1",
                    "severity": "error",
                    "category": "bounds",
                    "message": "元素越界",
                    "suggestion": "收缩内容",
                    "source": "programmatic",
                    "tier": "hard",
                },
                {
                    "slide_id": "slide-2",
                    "severity": "warning",
                    "category": "aesthetic",
                    "message": "信息略密",
                    "suggestion": "增加留白",
                    "source": "vision",
                    "tier": "advisory",
                },
            ]

        async def fail_if_fix_called(state, per_slide_timeout, progress=None, on_slide=None):  # noqa: ARG001
            raise AssertionError("auto fix should not run")

        originals = (
            runner_mod.stage_parse_document,
            runner_mod.stage_generate_outline,
            runner_mod.stage_select_layouts,
            runner_mod.stage_generate_slides,
            runner_mod.stage_resolve_assets,
            runner_mod.stage_verify_slides,
            runner_mod.stage_fix_slides_once,
        )
        runner_mod.stage_parse_document = fake_parse
        runner_mod.stage_generate_outline = fake_outline
        runner_mod.stage_select_layouts = fake_layout
        runner_mod.stage_generate_slides = fake_slides
        runner_mod.stage_resolve_assets = fake_assets
        runner_mod.stage_verify_slides = fake_verify
        runner_mod.stage_fix_slides_once = fail_if_fix_called
        try:
            job = _build_job("job-waiting-fix")
            await store.create_job(job)
            await runner._run_job(job.job_id, from_stage=StageStatus.PARSE)  # noqa: SLF001

            loaded = await store.get_job(job.job_id)
            assert loaded is not None
            assert loaded.status == JobStatus.WAITING_FIX_REVIEW
            assert loaded.current_stage == StageStatus.VERIFY
            assert loaded.hard_issue_slide_ids == ["slide-1"]
            assert loaded.advisory_issue_count == 1
            assert loaded.fix_preview_slides == []
            assert loaded.fix_preview_source_ids == []

            events = await store.list_events(job.job_id)
            types = [evt.type for evt in events]
            assert EventType.JOB_WAITING_FIX_REVIEW in types
            assert EventType.JOB_COMPLETED not in types
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


def test_preview_fix_generates_candidates_without_overwriting_slides(monkeypatch, tmp_path):
    async def _case():
        store = GenerationJobStore(tmp_path / "jobs")
        bus = GenerationEventBus()
        runner = GenerationRunner(store, bus)

        from app.services.generation import runner as runner_mod

        async def fake_fix(state, per_slide_timeout, progress=None, on_slide=None, target_slide_ids=None):  # noqa: ARG001
            for idx, slide in enumerate(state.slides):
                if target_slide_ids and slide.slide_id not in target_slide_ids:
                    continue
                patched = slide.model_copy(deep=True)
                content = dict(patched.content_data or {})
                content["title"] = f"{content.get('title', '页面')}（修复）"
                patched.content_data = content
                state.slides[idx] = patched

        original_fix = runner_mod.stage_fix_slides_once
        runner_mod.stage_fix_slides_once = fake_fix
        try:
            job = _build_job("job-preview-fix")
            job.status = JobStatus.WAITING_FIX_REVIEW
            job.slides = [
                _slide_payload("slide-1", "第一页"),
                _slide_payload("slide-2", "第二页"),
            ]
            job.hard_issue_slide_ids = ["slide-1"]
            await store.create_job(job)

            previewed = await runner.preview_fix(job.job_id)
            assert previewed.status == JobStatus.WAITING_FIX_REVIEW
            assert previewed.fix_preview_source_ids == ["slide-1"]
            assert len(previewed.fix_preview_slides) == 1
            assert previewed.fix_preview_slides[0]["slideId"] == "slide-1"
            assert "修复" in str(previewed.fix_preview_slides[0]["contentData"].get("title"))

            loaded = await store.get_job(job.job_id)
            assert loaded is not None
            assert loaded.slides[0]["contentData"]["title"] == "第一页"
            assert loaded.slides[1]["contentData"]["title"] == "第二页"

            events = await store.list_events(job.job_id)
            assert any(evt.type == EventType.FIX_PREVIEW_READY for evt in events)
        finally:
            runner_mod.stage_fix_slides_once = original_fix

    asyncio.run(_case())


def test_apply_fix_replaces_selected_slides_only(tmp_path):
    async def _case():
        store = GenerationJobStore(tmp_path / "jobs")
        bus = GenerationEventBus()
        runner = GenerationRunner(store, bus)

        job = _build_job("job-apply-fix")
        job.status = JobStatus.WAITING_FIX_REVIEW
        job.slides = [
            _slide_payload("slide-1", "第一页"),
            _slide_payload("slide-2", "第二页"),
        ]
        job.fix_preview_slides = [
            _slide_payload("slide-1", "第一页（修复）"),
            _slide_payload("slide-2", "第二页（修复）"),
        ]
        job.fix_preview_source_ids = ["slide-1", "slide-2"]
        await store.create_job(job)

        applied = await runner.apply_fix(job.job_id, slide_ids=["slide-1"])
        assert applied.status == JobStatus.COMPLETED
        assert applied.current_stage == StageStatus.COMPLETE
        assert applied.slides[0]["contentData"]["title"] == "第一页（修复）"
        assert applied.slides[1]["contentData"]["title"] == "第二页"
        assert applied.fix_preview_slides == []
        assert applied.fix_preview_source_ids == []

        events = await store.list_events(job.job_id)
        completed = [evt for evt in events if evt.type == EventType.JOB_COMPLETED]
        assert completed
        assert completed[-1].payload.get("applied_slide_ids") == ["slide-1"]

    asyncio.run(_case())


def test_skip_fix_completes_without_modifying_slides(tmp_path):
    async def _case():
        store = GenerationJobStore(tmp_path / "jobs")
        bus = GenerationEventBus()
        runner = GenerationRunner(store, bus)

        job = _build_job("job-skip-fix")
        job.status = JobStatus.WAITING_FIX_REVIEW
        job.slides = [
            _slide_payload("slide-1", "第一页"),
            _slide_payload("slide-2", "第二页"),
        ]
        job.fix_preview_slides = [_slide_payload("slide-1", "第一页（修复）")]
        job.fix_preview_source_ids = ["slide-1"]
        await store.create_job(job)

        skipped = await runner.skip_fix(job.job_id)
        assert skipped.status == JobStatus.COMPLETED
        assert skipped.current_stage == StageStatus.COMPLETE
        assert skipped.slides[0]["contentData"]["title"] == "第一页"
        assert skipped.fix_preview_slides == []
        assert skipped.fix_preview_source_ids == []

        events = await store.list_events(job.job_id)
        completed = [evt for evt in events if evt.type == EventType.JOB_COMPLETED]
        assert completed
        assert completed[-1].payload.get("fix_skipped") is True

    asyncio.run(_case())


def test_apply_fix_requires_waiting_state_and_preview(tmp_path):
    async def _case():
        store = GenerationJobStore(tmp_path / "jobs")
        bus = GenerationEventBus()
        runner = GenerationRunner(store, bus)

        job = _build_job("job-apply-guard")
        job.status = JobStatus.RUNNING
        job.slides = [_slide_payload("slide-1", "第一页")]
        await store.create_job(job)

        try:
            await runner.apply_fix(job.job_id, slide_ids=["slide-1"])
            assert False, "expected runtime error for non-waiting status"
        except RuntimeError as err:
            assert "当前状态不支持应用修复" in str(err)

        job_waiting = _build_job("job-apply-guard-preview")
        job_waiting.status = JobStatus.WAITING_FIX_REVIEW
        job_waiting.slides = [_slide_payload("slide-1", "第一页")]
        await store.create_job(job_waiting)

        try:
            await runner.apply_fix(job_waiting.job_id, slide_ids=["slide-1"])
            assert False, "expected runtime error when preview is missing"
        except RuntimeError as err:
            assert "先生成修复建议" in str(err)

    asyncio.run(_case())

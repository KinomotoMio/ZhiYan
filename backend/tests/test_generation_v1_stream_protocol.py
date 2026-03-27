import json
import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models.generation import EventType, TERMINAL_EVENTS
from app.services.generation.agent_adapter import AgentDeck, AgentOutline
from app.services.generation.event_bus import GenerationEventBus
from app.services.generation.job_store import GenerationJobStore
from app.services.generation.runner import GenerationRunner
from app.services.sessions.store import SessionStore


class RequestScopeStub:
    def __init__(self, workspace_id: str = "workspace-local-default"):
        self.headers = {"X-Workspace-Id": workspace_id}
        self.state = SimpleNamespace()


def _install_runtime(monkeypatch, tmp_path: Path) -> tuple[GenerationJobStore, GenerationRunner]:
    store = GenerationJobStore(tmp_path / "jobs")
    bus = GenerationEventBus()
    runner = GenerationRunner(store, bus)
    session_store = SessionStore(tmp_path / "stream-test.db", tmp_path / "uploads")
    asyncio.run(session_store.init())
    asyncio.run(session_store.ensure_workspace("workspace-local-default"))

    import app.services.sessions as sessions_pkg
    from app.api.v1 import sessions as sessions_api

    monkeypatch.setattr(sessions_pkg, "session_store", session_store)
    monkeypatch.setattr(sessions_api, "session_store", session_store)
    monkeypatch.setattr(sessions_api, "job_store", store)
    monkeypatch.setattr(sessions_api, "event_bus", bus)
    monkeypatch.setattr(sessions_api, "generation_runner", runner)
    return store, runner


def _patch_fast_agentloop(monkeypatch, runner: GenerationRunner):
    from app.services.generation import runner as runner_mod

    async def fake_outline(_job, _state):
        return AgentOutline.model_validate(
            {
                "title": "测试主题",
                "items": [
                    {"slideNumber": 1, "title": "封面", "role": "cover"},
                    {"slideNumber": 2, "title": "目录", "role": "agenda"},
                    {"slideNumber": 3, "title": "内容", "role": "narrative", "keyPoints": ["要点一", "要点二"]},
                ],
            }
        )

    async def fake_deck(_job, _state):
        return AgentDeck.model_validate(
            {
                "title": "测试主题",
                "slides": [
                    {"slideNumber": 1, "title": "封面", "role": "cover", "layoutHint": "intro-slide"},
                    {
                        "slideNumber": 2,
                        "title": "目录",
                        "role": "agenda",
                        "layoutHint": "outline-slide-rail",
                        "sections": [{"title": "内容", "description": "展开说明"}],
                    },
                    {
                        "slideNumber": 3,
                        "title": "内容",
                        "role": "process",
                        "layoutHint": "numbered-bullets",
                        "steps": [
                            {"title": "读取素材", "description": "读取工作区素材摘要与正文"},
                            {"title": "填充模板", "description": "按 layout-native schema 直接生成页面"},
                            {"title": "适配编辑器", "description": "输出当前 presentation payload"},
                        ],
                    },
                ],
            }
        )

    async def fake_verify(state, progress=None, enable_vision=True):  # noqa: ARG001
        if progress:
            await progress("verify", 1, 1, "验证布局质量...")
        state.verification_issues = []
    monkeypatch.setattr(runner, "_generate_outline_with_agent", fake_outline)
    monkeypatch.setattr(runner, "_generate_deck_with_agent", fake_deck)
    monkeypatch.setattr(runner_mod, "stage_verify_slides", fake_verify)


def test_generation_v1_stream_protocol_sequence(monkeypatch, tmp_path):
    _, runner = _install_runtime(monkeypatch, tmp_path)
    _patch_fast_agentloop(monkeypatch, runner)
    monkeypatch.setattr(settings, "project_root", tmp_path)

    async def run_inline(job_id: str, from_stage=None):
        await runner._run_job(job_id, from_stage)  # noqa: SLF001
        return True

    monkeypatch.setattr(runner, "start_job", run_inline)

    client = TestClient(app)
    session_resp = client.post("/api/v1/sessions", json={"title": "测试主题"})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]
    create_resp = client.post(
        f"/api/v1/sessions/{session_id}/generation/jobs",
        json={"topic": "测试主题", "content": "测试内容", "num_pages": 3, "mode": "auto"},
    )
    assert create_resp.status_code == 200
    job_id = create_resp.json()["job_id"]

    events: list[dict] = []
    done_count = 0
    with client.stream("GET", f"/api/v1/sessions/{session_id}/generation/jobs/{job_id}/events") as resp:
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
    assert EventType.SLIDE_READY.value in types
    terminal = [t for t in types if t in {et.value for et in TERMINAL_EVENTS}]
    assert len(terminal) == 1
    assert terminal[0] == EventType.JOB_COMPLETED.value

    snapshot = client.get(f"/api/v1/sessions/{session_id}/generation/jobs/{job_id}")
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["status"] == "completed"
    assert len(body["slides"]) == 3


def test_generation_v1_stream_protocol_heartbeat(monkeypatch, tmp_path):
    store, runner = _install_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "sse_heartbeat_seconds", 0.1)

    async def no_start(job_id: str, from_stage=None):  # noqa: ARG001
        return True

    monkeypatch.setattr(runner, "start_job", no_start)

    from app.api.v1 import sessions as sessions_api
    from app.models.generation import GenerationJob, GenerationRequestData

    async def _case():
        session = await sessions_api.session_store.create_session("workspace-local-default", "心跳测试")
        session_id = session["id"]
        job = GenerationJob(
            job_id="job-heartbeat",
            request=GenerationRequestData(topic="心跳测试", resolved_content="测试内容", session_id=session_id),
            outline_accepted=True,
        )
        await store.create_job(job)
        response = await sessions_api.stream_session_generation_job_events(
            session_id,
            job.job_id,
            RequestScopeStub(),
            after_seq=0,
        )
        chunk = await asyncio.wait_for(response.body_iterator.__anext__(), timeout=1.0)
        text = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
        await response.body_iterator.aclose()
        return text

    first_chunk = asyncio.run(_case())
    assert EventType.HEARTBEAT.value in first_chunk


def test_generation_v1_stream_after_seq_skips_old_terminal_event(monkeypatch, tmp_path):
    store, _runner = _install_runtime(monkeypatch, tmp_path)

    from app.api.v1 import sessions as sessions_api
    from app.models.generation import GenerationEvent, GenerationJob, GenerationRequestData, StageStatus

    async def _case():
        session = await sessions_api.session_store.create_session("workspace-local-default", "续流测试")
        session_id = session["id"]
        job = GenerationJob(
            job_id="job-after-seq",
            request=GenerationRequestData(topic="续流测试", resolved_content="测试内容", session_id=session_id),
            outline_accepted=True,
        )
        await store.create_job(job)
        await store.append_event(
            GenerationEvent(seq=1, type=EventType.JOB_FAILED, job_id=job.job_id, message="old failure")
        )

        response = await sessions_api.stream_session_generation_job_events(
            session_id,
            job.job_id,
            RequestScopeStub(),
            after_seq=1,
        )

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
            await sessions_api.event_bus.publish(evt2)
            await sessions_api.event_bus.publish(evt3)

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


def test_generation_v1_stream_waiting_fix_review_is_terminal(monkeypatch, tmp_path):
    store, _runner = _install_runtime(monkeypatch, tmp_path)

    from app.api.v1 import sessions as sessions_api
    from app.models.generation import GenerationEvent, GenerationJob, GenerationRequestData, StageStatus

    async def _case():
        session = await sessions_api.session_store.create_session("workspace-local-default", "待修复")
        session_id = session["id"]
        job = GenerationJob(
            job_id="job-waiting-fix-stream",
            request=GenerationRequestData(topic="待修复", resolved_content="测试内容", session_id=session_id),
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

        response = await sessions_api.stream_session_generation_job_events(
            session_id,
            job.job_id,
            RequestScopeStub(),
            after_seq=0,
        )
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

import asyncio
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.v1 import generate
from app.core.config import settings
from app.main import app
from app.services.pipeline.layout import build_slide_from_content


class _FakeState:
    def __init__(self) -> None:
        self.source_ids: list[str] = []
        self.num_pages = 5
        self.progress_callback = None


def _collect_stream(client: TestClient, payload: dict) -> tuple[list[dict], bool, bool]:
    events: list[dict] = []
    saw_done = False
    saw_heartbeat = False
    with client.stream(
        "POST",
        "/api/v1/generate/stream",
        json=payload,
        headers={"X-Request-ID": "req-test"},
    ) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if not line:
                continue
            if line.startswith(": ping"):
                saw_heartbeat = True
                continue
            if not line.startswith("data: "):
                continue

            data = line[6:]
            if data == "[DONE]":
                saw_done = True
                break
            events.append(json.loads(data))
    return events, saw_done, saw_heartbeat


def _patch_generate_prechecks(monkeypatch):
    monkeypatch.setattr(generate, "_check_model_config", lambda: None)
    fake_state = _FakeState()
    monkeypatch.setattr(generate, "_prepare_pipeline", lambda req: ("Demo", fake_state))
    return fake_state


def _result_with_slide():
    slide = build_slide_from_content(
        slide_number=1,
        title="Demo",
        layout_type="title-content",
        body_text="• hello",
    )
    return SimpleNamespace(output=[slide])


def test_generate_stream_unexpected_cancellederror_emits_error_then_done(monkeypatch):
    from app.services.pipeline import graph

    _patch_generate_prechecks(monkeypatch)

    async def fake_run(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(graph.slide_pipeline, "run", fake_run)

    client = TestClient(app)
    events, saw_done, _ = _collect_stream(client, {"topic": "demo"})

    assert saw_done is True
    assert any(evt.get("type") == "error" for evt in events)
    assert not any(evt.get("type") == "result" for evt in events)
    error_evt = next(evt for evt in events if evt.get("type") == "error")
    assert error_evt.get("error_type") == "cancelled_error"
    assert isinstance(error_evt.get("run_id"), str)


def test_generate_stream_client_cancel_does_not_emit_fake_success(monkeypatch):
    from app.services.pipeline import graph

    _patch_generate_prechecks(monkeypatch)

    async def fake_run(*args, **kwargs):
        task = asyncio.current_task()
        assert task is not None
        task.cancel()
        await asyncio.sleep(0)
        return _result_with_slide()

    monkeypatch.setattr(graph.slide_pipeline, "run", fake_run)

    client = TestClient(app)
    events, saw_done, _ = _collect_stream(client, {"topic": "demo"})

    assert saw_done is True
    assert not any(evt.get("type") == "result" for evt in events)
    assert any(evt.get("type") == "error" for evt in events)


def test_generate_stream_heartbeat_ping_emitted_when_idle(monkeypatch, caplog):
    from app.services.pipeline import graph

    _patch_generate_prechecks(monkeypatch)
    monkeypatch.setattr(settings, "sse_heartbeat_seconds", 0.01)
    monkeypatch.setattr(settings, "log_sse_debug", True)

    async def fake_run(*args, **kwargs):
        await asyncio.sleep(0.2)
        return _result_with_slide()

    monkeypatch.setattr(graph.slide_pipeline, "run", fake_run)

    client = TestClient(app)
    with caplog.at_level("DEBUG"):
        events, saw_done, _ = _collect_stream(client, {"topic": "demo"})

    assert saw_done is True
    assert any(evt.get("type") == "result" for evt in events)
    assert any("stream_heartbeat" in rec.message for rec in caplog.records)


def test_generate_stream_events_include_run_id(monkeypatch):
    from app.services.pipeline import graph

    fake_state = _patch_generate_prechecks(monkeypatch)

    async def fake_run(*args, **kwargs):  # noqa: ARG001
        if fake_state.progress_callback:
            fake_state.progress_callback("parse", 1, 7, "解析文档...")
        return _result_with_slide()

    monkeypatch.setattr(graph.slide_pipeline, "run", fake_run)

    client = TestClient(app)
    events, saw_done, _ = _collect_stream(client, {"topic": "demo"})

    assert saw_done is True
    tracked = [evt for evt in events if evt.get("type") in {"progress", "result", "error"}]
    assert tracked
    run_ids = {evt.get("run_id") for evt in tracked}
    assert len(run_ids) == 1
    assert all(isinstance(evt.get("run_id"), str) and evt.get("run_id") for evt in tracked)


def test_generate_stream_timeout_when_pipeline_ignores_cancel(monkeypatch):
    from app.services.pipeline import graph

    _patch_generate_prechecks(monkeypatch)
    monkeypatch.setattr(settings, "generate_timeout_seconds", 0.01)

    async def fake_run(*args, **kwargs):  # noqa: ARG001
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            # Simulate SDK swallowing cancellation and lingering.
            await asyncio.sleep(0.2)
            return _result_with_slide()

    monkeypatch.setattr(graph.slide_pipeline, "run", fake_run)

    client = TestClient(app)
    events, saw_done, _ = _collect_stream(client, {"topic": "demo"})

    assert saw_done is True
    assert not any(evt.get("type") == "result" for evt in events)
    err_evt = next(evt for evt in events if evt.get("type") == "error")
    assert err_evt.get("error_type") == "timeout"

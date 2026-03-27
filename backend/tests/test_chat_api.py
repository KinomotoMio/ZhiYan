import asyncio
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app


def _install_temp_session_store(monkeypatch, tmp_path):
    import app.services.sessions as sessions_pkg
    from app.api.v1 import chat as chat_api
    from app.api.v1 import sessions as sessions_api
    from app.services.sessions.store import SessionStore

    store = SessionStore(tmp_path / "zhiyan-chat-test.db", tmp_path / "uploads")
    asyncio.run(store.init())

    monkeypatch.setattr(sessions_pkg, "session_store", store)
    monkeypatch.setattr(sessions_api, "session_store", store)
    monkeypatch.setattr(chat_api, "session_store", store)
    return store


def _parse_sse(response_text: str) -> list[dict]:
    events: list[dict] = []
    for line in response_text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if not payload or payload == "[DONE]":
            continue
        events.append(json.loads(payload))
    return events


class _FakeStreamResult:
    def __init__(self, chunks: list[str]):
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False

    async def stream_text(self, delta: bool = False):
        if delta:
            for chunk in self._chunks:
                yield chunk
            return

        acc = ""
        for chunk in self._chunks:
            acc += chunk
            yield acc


class _FakeChatAgent:
    def __init__(self, *, stream_chunks: list[str] | None = None, run_outputs: list[str] | None = None):
        self._stream_chunks = stream_chunks or []
        self._run_outputs = list(run_outputs or [])
        self.captured_histories: list[list] = []
        self.captured_prompts: list[str] = []

    def run_stream(self, prompt: str, deps, message_history):  # noqa: ANN001
        self.captured_prompts.append(prompt)
        self.captured_histories.append(message_history)
        return _FakeStreamResult(self._stream_chunks)

    async def run(self, prompt: str, deps, message_history):  # noqa: ANN001
        self.captured_prompts.append(prompt)
        self.captured_histories.append(message_history)
        output = self._run_outputs.pop(0) if self._run_outputs else ""
        return SimpleNamespace(output=output)


class _FakeNotesOnlyAgent:
    def __init__(self):
        self.calls = 0

    async def run(self, prompt: str, deps, message_history):  # noqa: ANN001
        self.calls += 1
        deps.modifications.append(SimpleNamespace(action="update_notes"))
        deps.slides.append({"slideId": f"preview-{self.calls}"})
        return SimpleNamespace(output="已补充演讲者注释")


async def _fake_html_editor(**kwargs):  # noqa: ANN003
    _ = kwargs
    return SimpleNamespace(
        assistant_reply="我已重做当前页的 HTML 表达。",
        should_update=True,
        html=(
            "<!DOCTYPE html><html><head><title>HTML 改稿</title></head><body>"
            '<section data-slide-id="slide-1" data-slide-title="封面">'
            "<div><h1>封面</h1><p>新的视觉样式</p></div>"
            "</section>"
            "</body></html>"
        ),
    )


def test_chat_stream_delta_no_duplication(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)

    import app.services.agents.chat_agent as chat_agent_module

    fake_agent = _FakeChatAgent(stream_chunks=["你", "好"])
    monkeypatch.setitem(chat_agent_module.__dict__, "chat_agent", fake_agent)

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-chat"}
    created = client.post("/api/v1/sessions", headers=headers, json={"title": "chat"})
    assert created.status_code == 200
    session_id = created.json()["id"]

    response = client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "message": "你好",
            "session_id": session_id,
            "messages": [],
            "action_hint": "free_text",
        },
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    text_chunks = [evt["content"] for evt in events if evt.get("type") == "text"]
    assert text_chunks == ["你", "好"]

    chat_list = client.get(f"/api/v1/sessions/{session_id}/chat", headers=headers)
    assert chat_list.status_code == 200
    records = chat_list.json()
    assert records[-1]["role"] == "assistant"
    assert records[-1]["content"] == "你好"


def test_chat_history_tail_dedup(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)

    import app.services.agents.chat_agent as chat_agent_module

    fake_agent = _FakeChatAgent(stream_chunks=["收到"])
    monkeypatch.setitem(chat_agent_module.__dict__, "chat_agent", fake_agent)

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-chat"}
    response = client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "message": "请优化当前页",
            "messages": [
                {"role": "assistant", "content": "前一轮建议"},
                {"role": "user", "content": "请优化当前页"},
            ],
            "action_hint": "free_text",
        },
    )
    assert response.status_code == 200
    assert len(fake_agent.captured_histories) == 1
    assert len(fake_agent.captured_histories[0]) == 1


def test_chat_action_hint_no_modification_emits_no_op(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)

    import app.services.agents.chat_agent as chat_agent_module

    fake_agent = _FakeChatAgent(run_outputs=["我先看下", "仍未修改"])
    monkeypatch.setitem(chat_agent_module.__dict__, "chat_agent", fake_agent)

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-chat"}
    response = client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "message": "请简化当前页",
            "messages": [],
            "action_hint": "simplify",
        },
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    event_types = [evt.get("type") for evt in events]
    assert "no_op" in event_types


def test_chat_action_hint_notes_only_is_no_op(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)

    import app.services.agents.chat_agent as chat_agent_module

    fake_agent = _FakeNotesOnlyAgent()
    monkeypatch.setitem(chat_agent_module.__dict__, "chat_agent", fake_agent)

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-chat"}
    response = client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "message": "请为当前页添加更多细节",
            "messages": [],
            "action_hint": "add_detail",
            "presentation_context": {
                "slides": [
                    {
                        "slideId": "s-1",
                        "layoutId": "two-column-compare",
                        "contentData": {
                            "title": "测试",
                            "left": {"heading": "A", "items": ["a1"]},
                            "right": {"heading": "B", "items": ["b1"]},
                        },
                    }
                ]
            },
        },
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    event_types = [evt.get("type") for evt in events]
    assert "slide_update" not in event_types
    assert "no_op" in event_types
    text_events = [evt.get("content", "") for evt in events if evt.get("type") == "text"]
    assert any("未执行改稿" in content for content in text_events)


def test_chat_html_mode_emits_html_update(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)

    from app.api.v1 import chat as chat_api

    monkeypatch.setattr(chat_api, "edit_html_deck", _fake_html_editor)

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-chat"}
    response = client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "message": "请把当前页做得更有设计感",
            "messages": [],
            "action_hint": "enrich_visual",
            "current_slide_index": 0,
            "presentation_context": {
                "title": "HTML 演示",
                "output_mode": "html",
                "html_content": (
                    "<!DOCTYPE html><html><head><title>HTML 演示</title></head><body>"
                    '<section data-slide-id="slide-1" data-slide-title="封面">'
                    "<div><h1>封面</h1></div>"
                    "</section>"
                    "</body></html>"
                ),
                "slides": [
                    {
                        "slideId": "slide-1",
                        "layoutId": "blank",
                        "contentData": {"title": "封面"},
                    }
                ],
            },
        },
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    text_events = [evt for evt in events if evt.get("type") == "text"]
    assert any("HTML 表达" in evt.get("content", "") for evt in text_events)
    html_updates = [evt for evt in events if evt.get("type") == "html_update"]
    assert len(html_updates) == 1
    html_update = html_updates[0]
    assert html_update["presentation"]["title"] == "HTML 改稿"
    assert html_update["presentation"]["slides"][0]["slideId"] == "slide-1"
    assert "<section data-slide-id=\"slide-1\"" in html_update["html_content"]


def test_put_latest_presentation_persists_non_snapshot(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-chat"}
    created = client.post("/api/v1/sessions", headers=headers, json={"title": "latest"})
    assert created.status_code == 200
    session_id = created.json()["id"]

    presentation = {
        "presentationId": "pres-chat",
        "title": "AI 改稿",
        "slides": [
            {
                "slideId": "s-1",
                "layoutType": "bullet-with-icons",
                "layoutId": "bullet-with-icons",
                "contentData": {"title": "测试", "items": []},
                "components": [],
            }
        ],
    }

    saved1 = client.put(
        f"/api/v1/sessions/{session_id}/presentations/latest",
        headers=headers,
        json={"presentation": presentation, "source": "chat"},
    )
    assert saved1.status_code == 200
    body1 = saved1.json()
    assert body1["is_snapshot"] is False
    assert body1["snapshot_label"] is None
    assert body1["version_no"] == 1

    saved2 = client.put(
        f"/api/v1/sessions/{session_id}/presentations/latest",
        headers=headers,
        json={"presentation": presentation, "source": "chat"},
    )
    assert saved2.status_code == 200
    body2 = saved2.json()
    assert body2["version_no"] == 2

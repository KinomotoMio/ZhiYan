import asyncio
import json

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.agents.chat_agent import SlideModification
from app.services.agents.editor_loop import EditorLoopOutcome, editor_loop_service
from app.services.generation.agentic.models import ModelUsage
from app.services.generation.agentic.types import AssistantMessage, ToolCall
from tests.conftest import FakeModel


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
    monkeypatch.setattr(settings, "project_root", tmp_path)
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


def _install_fake_model(monkeypatch, fake_model: FakeModel) -> None:
    monkeypatch.setattr(editor_loop_service, "_model_client_factory", lambda: fake_model)


def test_chat_free_text_emits_loop_events_and_sanitizes_think(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)
    fake_model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="get_current_slide_info",
                        args={},
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(content="<think>hidden</think>我先看过当前页了，建议保持核心结构。"),
        ],
        usages=[ModelUsage(), ModelUsage()],
    )
    _install_fake_model(monkeypatch, fake_model)

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-chat"}
    created = client.post("/api/v1/sessions", headers=headers, json={"title": "chat"})
    session_id = created.json()["id"]

    response = client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "message": "看看这一页讲得怎么样",
            "session_id": session_id,
            "messages": [],
            "action_hint": "free_text",
            "presentation_context": {
                "title": "演示",
                "output_mode": "structured",
                "slides": [
                    {
                        "slideId": "s-1",
                        "layoutId": "metrics-slide",
                        "layoutType": "metrics-slide",
                        "contentData": {"title": "测试页", "metrics": [{"value": "12%", "label": "增长"}]},
                        "components": [],
                    }
                ],
            },
        },
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert [evt["type"] for evt in events[:4]] == [
        "assistant_status",
        "assistant_status",
        "assistant_status",
        "tool_call",
    ]
    assert any(evt.get("type") == "tool_result" for evt in events)
    text_events = [evt for evt in events if evt.get("type") == "text"]
    assert len(text_events) == 1
    assert "<think>" not in text_events[0]["content"]
    assert "我先看过当前页了" in text_events[0]["content"]

    chat_list = client.get(f"/api/v1/sessions/{session_id}/chat", headers=headers)
    records = chat_list.json()
    assert records[-1]["role"] == "assistant"
    assert "<think>" not in records[-1]["content"]


def test_chat_structured_action_emits_slide_update(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)
    fake_model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="modify_slide_content",
                        args={
                            "slide_index": 0,
                            "field_path": "description",
                            "new_value": "把三项指标都补充成更完整的解释。",
                        },
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(content="我已经补充了当前页说明。"),
        ]
    )
    _install_fake_model(monkeypatch, fake_model)

    client = TestClient(app)
    response = client.post(
        "/api/v1/chat",
        headers={"X-Workspace-Id": "ws-chat"},
        json={
            "message": "请给这一页补充更多细节",
            "messages": [],
            "action_hint": "add_detail",
            "presentation_context": {
                "title": "结构化演示",
                "output_mode": "structured",
                "slides": [
                    {
                        "slideId": "s-1",
                        "layoutId": "metrics-slide",
                        "layoutType": "metrics-slide",
                        "contentData": {
                            "title": "增长指标",
                            "description": "原始说明",
                            "metrics": [{"value": "12%", "label": "增长"}],
                        },
                        "components": [],
                    }
                ],
            },
        },
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    slide_updates = [evt for evt in events if evt.get("type") == "slide_update"]
    assert len(slide_updates) == 1
    assert slide_updates[0]["slides"][0]["contentData"]["description"] == "把三项指标都补充成更完整的解释。"
    assert slide_updates[0]["modifications"][0]["action"] == "update_content_data"


def test_chat_action_hint_notes_only_is_no_op(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)
    fake_model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="modify_slide_speaker_notes",
                        args={"slide_index": 0, "new_notes": "补充一段内部备注"},
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(content="我先给这页加了一点注释。"),
        ]
    )
    _install_fake_model(monkeypatch, fake_model)

    client = TestClient(app)
    response = client.post(
        "/api/v1/chat",
        headers={"X-Workspace-Id": "ws-chat"},
        json={
            "message": "请为当前页添加更多细节",
            "messages": [],
            "action_hint": "add_detail",
            "presentation_context": {
                "title": "结构化演示",
                "output_mode": "structured",
                "slides": [
                    {
                        "slideId": "s-1",
                        "layoutId": "two-column-compare",
                        "layoutType": "two-column-compare",
                        "contentData": {
                            "title": "测试",
                            "left": {"heading": "A", "items": ["a1"]},
                            "right": {"heading": "B", "items": ["b1"]},
                        },
                        "components": [],
                    }
                ],
            },
        },
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert not any(evt.get("type") == "slide_update" for evt in events)
    assert any(evt.get("type") == "no_op" for evt in events)
    text_events = [evt.get("content", "") for evt in events if evt.get("type") == "text"]
    assert any("未执行改稿" in content for content in text_events)


def test_chat_html_mode_emits_html_update(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)
    fake_model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="submit_html_revision",
                        args={
                            "html": (
                                "<!DOCTYPE html><html><head><title>HTML 改稿</title></head><body>"
                                '<section data-slide-id="slide-1" data-slide-title="封面">'
                                "<div><h1>封面</h1><p>新的视觉样式</p></div>"
                                "</section>"
                                "</body></html>"
                            ),
                            "summary": "强化当前页视觉层次",
                        },
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(content="我已重做当前页的 HTML 表达。"),
        ]
    )
    _install_fake_model(monkeypatch, fake_model)

    client = TestClient(app)
    response = client.post(
        "/api/v1/chat",
        headers={"X-Workspace-Id": "ws-chat"},
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
                        "layoutType": "blank",
                        "contentData": {"title": "封面"},
                        "components": [],
                    }
                ],
            },
        },
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    html_updates = [evt for evt in events if evt.get("type") == "html_update"]
    assert len(html_updates) == 1
    assert html_updates[0]["presentation"]["title"] == "HTML 改稿"
    assert html_updates[0]["presentation"]["htmlDeckMeta"]["slideCount"] == 1
    assert html_updates[0]["html_meta"]["slide_count"] == 1
    assert "<section data-slide-id=\"slide-1\"" in html_updates[0]["html_content"]


def test_chat_snapshot_reuses_history_until_base_signature_changes(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)
    fake_model = FakeModel(
        responses=[
            AssistantMessage(content="第一轮完成"),
            AssistantMessage(content="第二轮完成"),
            AssistantMessage(content="第三轮完成"),
        ]
    )
    _install_fake_model(monkeypatch, fake_model)

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-chat"}
    created = client.post("/api/v1/sessions", headers=headers, json={"title": "chat"})
    session_id = created.json()["id"]
    payload = {
        "message": "先看看这一页",
        "session_id": session_id,
        "messages": [],
        "action_hint": "free_text",
        "presentation_context": {
            "title": "结构化演示",
            "output_mode": "structured",
            "slides": [
                {
                    "slideId": "s-1",
                    "layoutId": "metrics-slide",
                    "layoutType": "metrics-slide",
                    "contentData": {"title": "测试页"},
                    "components": [],
                }
            ],
        },
    }

    response_1 = client.post("/api/v1/chat", headers=headers, json=payload)
    assert response_1.status_code == 200

    payload["message"] = "再继续看看"
    response_2 = client.post("/api/v1/chat", headers=headers, json=payload)
    assert response_2.status_code == 200

    payload["presentation_context"]["slides"][0]["contentData"]["title"] = "已经变了"
    payload["message"] = "第三次"
    response_3 = client.post("/api/v1/chat", headers=headers, json=payload)
    assert response_3.status_code == 200

    assert len(fake_model.seen_messages) == 3
    assert len(fake_model.seen_messages[1]) > len(fake_model.seen_messages[0])
    assert len(fake_model.seen_messages[2]) <= len(fake_model.seen_messages[1])


def test_chat_slidev_mode_emits_slidev_update(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)

    async def _fake_run(request):  # noqa: ANN001
        assert request.output_mode == "slidev"
        return EditorLoopOutcome(
            assistant_reply="我已把这一页改成更适合 Slidev 播放的结构。",
            events=[
                {"type": "assistant_status", "assistant_status": "thinking"},
                {
                    "type": "tool_call",
                    "tool_name": "edit_slidev_deck",
                    "call_id": "slidev-edit",
                    "summary": "改写整份 Slidev deck",
                },
                {
                    "type": "tool_result",
                    "tool_name": "build_slidev_preview",
                    "call_id": "slidev-build",
                    "ok": True,
                    "summary": "已生成可预览的 Slidev deck",
                },
                {"type": "assistant_status", "assistant_status": "ready"},
            ],
            modifications=[
                SlideModification(
                    slide_index=0,
                    action="update_slidev_deck",
                    data={"selected_style_id": "tech-launch"},
                )
            ],
            slides=[
                {
                    "slideId": "slide-1",
                    "layoutType": "blank",
                    "layoutId": "blank",
                    "contentData": {"title": "新封面"},
                    "components": [],
                },
                {
                    "slideId": "slide-2",
                    "layoutType": "blank",
                    "layoutId": "blank",
                    "contentData": {"title": "新结尾"},
                    "components": [],
                },
            ],
            normalized_presentation={
                "presentationId": "pres-slidev-chat",
                "title": "Slidev 改稿",
                "slides": [
                    {
                        "slideId": "slide-1",
                        "layoutType": "blank",
                        "layoutId": "blank",
                        "contentData": {"title": "新封面"},
                        "components": [],
                    },
                    {
                        "slideId": "slide-2",
                        "layoutType": "blank",
                        "layoutId": "blank",
                        "contentData": {"title": "新结尾"},
                        "components": [],
                    },
                ],
            },
            slidev_markdown="---\ntitle: Slidev 改稿\n---\n\n# 新封面\n\n---\n\n# 新结尾\n",
            slidev_meta={
                "title": "Slidev 改稿",
                "slide_count": 2,
                "slides": [
                    {"index": 0, "slide_id": "slide-1", "title": "新封面", "role": "cover"},
                    {"index": 1, "slide_id": "slide-2", "title": "新结尾", "role": "closing"},
                ],
            },
            slidev_preview_url="/api/v1/slidev-previews/spv-test-1",
            selected_style_id="tech-launch",
        )

    monkeypatch.setattr(editor_loop_service, "run", _fake_run)

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-chat"}
    response = client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "message": "把第 1 页做得更像产品发布会开场",
            "messages": [],
            "session_id": "sess-slidev-chat",
            "action_hint": "enrich_visual",
            "current_slide_index": 0,
            "presentation_context": {
                "title": "Slidev 演示",
                "output_mode": "slidev",
                "slidev_markdown": "---\ntitle: Slidev 演示\n---\n\n# 封面\n",
                "slidev_meta": {
                    "slides": [
                        {"index": 0, "slide_id": "slide-1", "title": "封面", "role": "cover"},
                    ]
                },
                "selected_style_id": "tech-launch",
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
    assert any("Slidev" in evt.get("content", "") for evt in text_events)
    slidev_updates = [evt for evt in events if evt.get("type") == "slidev_update"]
    assert len(slidev_updates) == 1
    slidev_update = slidev_updates[0]
    assert slidev_update["presentation"]["title"] == "Slidev 改稿"
    assert slidev_update["meta"]["slides"][0]["title"] == "新封面"
    assert slidev_update["selected_style_id"] == "tech-launch"
    assert slidev_update["preview_url"] == "/api/v1/slidev-previews/spv-test-1"


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

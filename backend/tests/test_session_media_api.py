import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.generation.agentic.types import AssistantMessage, ToolCall
from app.services.sessions.store import SessionStore
from tests.conftest import FakeModel


def _install_temp_session_store(monkeypatch, tmp_path: Path) -> SessionStore:
    import app.services.sessions as sessions_pkg
    from app.api.v1 import chat as chat_api
    from app.api.v1 import sessions as sessions_api
    from app.api.v1 import workspaces as workspaces_api
    from app.api.v1 import workspace_sources as workspace_sources_api

    store = SessionStore(tmp_path / "zhiyan-test.db", tmp_path / "uploads")
    asyncio.run(store.init())

    monkeypatch.setattr(sessions_pkg, "session_store", store)
    monkeypatch.setattr(sessions_api, "session_store", store)
    monkeypatch.setattr(chat_api, "session_store", store)
    monkeypatch.setattr(workspace_sources_api, "session_store", store)
    monkeypatch.setattr(workspaces_api, "session_store", store)
    monkeypatch.setattr(settings, "project_root", tmp_path)
    return store


def _create_session(client: TestClient, headers: dict[str, str], title: str) -> str:
    response = client.post("/api/v1/sessions", headers=headers, json={"title": title})
    assert response.status_code == 200
    return response.json()["id"]


def _sample_presentation() -> dict:
    return {
        "presentationId": "pres-1",
        "title": "Agent Loop Speaker Notes",
        "slides": [
            {
                "slideId": "slide-1",
                "layoutType": "intro-slide",
                "layoutId": "intro-slide",
                "contentData": {"title": "封面"},
                "speakerNotes": "旧封面注解",
            },
            {
                "slideId": "slide-2",
                "layoutType": "summary-section-title",
                "layoutId": "summary-section-title",
                "contentData": {"title": "关键发现"},
                "speakerNotes": "旧内容页注解",
                "speakerAudio": {
                    "provider": "minimax",
                    "model": "speech-2.8-hd",
                    "voiceId": "male-qn-qingse",
                    "textHash": "stale-hash",
                    "storagePath": "/tmp/stale.mp3",
                    "mimeType": "audio/mpeg",
                    "generatedAt": "2026-03-27T12:00:00Z",
                },
            },
        ],
    }


def _save_latest_presentation(store: SessionStore, session_id: str, payload: dict) -> None:
    asyncio.run(
        store.save_presentation(
            session_id=session_id,
            payload=payload,
            is_snapshot=False,
            snapshot_label=None,
        )
    )


def test_generate_speaker_notes_current_persists_and_writes_workspace(monkeypatch, tmp_path):
    store = _install_temp_session_store(monkeypatch, tmp_path)
    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-speaker-notes"}
    session_id = _create_session(client, headers, "speaker notes")

    asyncio.run(
        store.create_source(
            session_id=session_id,
            source_type="text",
            name="会议纪要",
            file_category="notes",
            size=10,
            status="ready",
            preview_snippet="增长 20%",
            storage_path=None,
            parsed_content="本季度重点是把表面效率转成真实产出，增长目标 20%。",
        )
    )
    _save_latest_presentation(store, session_id, _sample_presentation())

    fake_model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="read_file",
                        args={"path": "artifacts/current-presentation.md"},
                        tool_call_id="call-read-presentation",
                    )
                ]
            ),
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="read_file",
                        args={"path": "sources/manifest.json"},
                        tool_call_id="call-read-manifest",
                    )
                ]
            ),
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="submit_speaker_notes",
                        args={
                            "notes": [
                                {
                                    "slideId": "slide-2",
                                    "notes": "这一页不要只看表面效率，我们更要强调真实产出的改善，以及增长目标已经被重新量化。"
                                }
                            ]
                        },
                        tool_call_id="call-submit-notes",
                    )
                ]
            ),
            AssistantMessage(content="notes submitted"),
        ]
    )
    monkeypatch.setattr("app.services.speaker_notes._create_agent_model_client", lambda: fake_model)

    response = client.post(
        f"/api/v1/sessions/{session_id}/speaker-notes/generate",
        headers=headers,
        json={
            "presentation": _sample_presentation(),
            "scope": "current",
            "currentSlideIndex": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["updatedSlideIds"] == ["slide-2"]
    updated_slide = payload["presentation"]["slides"][1]
    assert updated_slide["speakerNotes"].startswith("这一页不要只看表面效率")
    assert "speakerAudio" not in updated_slide

    workspace_root = Path(payload["workspaceRoot"])
    assert workspace_root.exists()
    assert (workspace_root / "artifacts" / "current-presentation.json").exists()
    assert (workspace_root / "artifacts" / "current-presentation.md").exists()
    assert (workspace_root / "sources" / "manifest.json").exists()
    assert any("read_file" == tool["name"] for tool in fake_model.seen_tools[0])
    assert any("submit_speaker_notes" == tool["name"] for tool in fake_model.seen_tools[0])

    latest = asyncio.run(store.get_latest_presentation(headers["X-Workspace-Id"], session_id))
    assert latest is not None
    assert latest["presentation"]["slides"][1]["speakerNotes"].startswith("这一页不要只看表面效率")


def test_generate_speaker_notes_rejects_mismatched_submission(monkeypatch, tmp_path):
    store = _install_temp_session_store(monkeypatch, tmp_path)
    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-speaker-notes"}
    session_id = _create_session(client, headers, "speaker notes")
    _save_latest_presentation(store, session_id, _sample_presentation())

    fake_model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="submit_speaker_notes",
                        args={
                            "notes": [
                                {
                                    "slideId": "slide-1",
                                    "notes": "错误地提交到了别的页面。"
                                }
                            ]
                        },
                        tool_call_id="call-submit-notes",
                    )
                ]
            ),
            AssistantMessage(content="notes submitted"),
        ]
    )
    monkeypatch.setattr("app.services.speaker_notes._create_agent_model_client", lambda: fake_model)

    response = client.post(
        f"/api/v1/sessions/{session_id}/speaker-notes/generate",
        headers=headers,
        json={
            "presentation": _sample_presentation(),
            "scope": "current",
            "currentSlideIndex": 1,
        },
    )

    assert response.status_code == 422
    assert "slideId" in response.json()["detail"]


def test_speaker_audio_reuses_cached_file_and_regenerates_when_notes_change(monkeypatch, tmp_path):
    store = _install_temp_session_store(monkeypatch, tmp_path)
    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-speaker-audio"}
    session_id = _create_session(client, headers, "speaker audio")

    original_provider = settings.tts_provider
    original_key = settings.tts_api_key
    original_base_url = settings.tts_base_url
    original_model = settings.tts_model
    original_voice_id = settings.tts_voice_id
    settings.tts_provider = "minimax"
    settings.tts_api_key = "tts-secret-key"
    settings.tts_base_url = "https://api.minimaxi.com"
    settings.tts_model = "speech-2.8-hd"
    settings.tts_voice_id = "male-qn-qingse"

    calls: list[str] = []

    async def fake_request(notes: str) -> bytes:
        calls.append(notes)
        return b"fake-mp3"

    monkeypatch.setattr("app.services.speaker_audio._request_minimax_tts", fake_request)

    try:
        presentation = _sample_presentation()
        presentation["slides"][1]["speakerNotes"] = "第一版注解"
        presentation["slides"][1].pop("speakerAudio", None)
        _save_latest_presentation(store, session_id, presentation)

        first = client.post(
            f"/api/v1/sessions/{session_id}/slides/slide-2/speaker-audio",
            headers=headers,
        )
        assert first.status_code == 200
        first_payload = first.json()
        assert first_payload["speakerAudio"]["model"] == "speech-2.8-hd"
        assert first_payload["playbackPath"] == f"/api/v1/sessions/{session_id}/slides/slide-2/speaker-audio"
        assert len(calls) == 1

        second = client.post(
            f"/api/v1/sessions/{session_id}/slides/slide-2/speaker-audio",
            headers=headers,
        )
        assert second.status_code == 200
        assert len(calls) == 1
        assert second.json()["speakerAudio"]["textHash"] == first_payload["speakerAudio"]["textHash"]

        latest = asyncio.run(store.get_latest_presentation(headers["X-Workspace-Id"], session_id))
        latest["presentation"]["slides"][1]["speakerNotes"] = "第二版注解"
        latest["presentation"]["slides"][1].pop("speakerAudio", None)
        _save_latest_presentation(store, session_id, latest["presentation"])

        third = client.post(
            f"/api/v1/sessions/{session_id}/slides/slide-2/speaker-audio",
            headers=headers,
        )
        assert third.status_code == 200
        assert len(calls) == 2
        assert third.json()["speakerAudio"]["textHash"] != first_payload["speakerAudio"]["textHash"]

        playback = client.get(
            f"/api/v1/sessions/{session_id}/slides/slide-2/speaker-audio",
            headers=headers,
        )
        assert playback.status_code == 200
        assert playback.content == b"fake-mp3"
        assert playback.headers["content-type"].startswith("audio/mpeg")
    finally:
        settings.tts_provider = original_provider
        settings.tts_api_key = original_key
        settings.tts_base_url = original_base_url
        settings.tts_model = original_model
        settings.tts_voice_id = original_voice_id

import asyncio
import json
import sqlite3

from fastapi.testclient import TestClient

from app.main import app


def _install_temp_session_store(monkeypatch, tmp_path):
    import app.services.sessions as sessions_pkg
    from app.api.v1 import chat as chat_api
    from app.api.v1 import sessions as sessions_api
    from app.api.v2 import generation as generation_api
    from app.services.sessions.store import SessionStore

    store = SessionStore(tmp_path / "zhiyan-test.db", tmp_path / "uploads")
    asyncio.run(store.init())

    monkeypatch.setattr(sessions_pkg, "session_store", store)
    monkeypatch.setattr(sessions_api, "session_store", store)
    monkeypatch.setattr(chat_api, "session_store", store)
    monkeypatch.setattr(generation_api, "session_store", store)
    return store


def test_sessions_workspace_isolation_and_chat_persistence(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)

    client = TestClient(app)
    h1 = {"X-Workspace-Id": "ws-a"}
    h2 = {"X-Workspace-Id": "ws-b"}

    created = client.post("/api/v1/sessions", headers=h1, json={"title": "会话A"})
    assert created.status_code == 200
    session_id = created.json()["id"]

    list_a = client.get("/api/v1/sessions", headers=h1)
    list_b = client.get("/api/v1/sessions", headers=h2)
    assert list_a.status_code == 200
    assert list_b.status_code == 200
    assert len(list_a.json()) == 1
    assert list_b.json() == []

    denied = client.get(f"/api/v1/sessions/{session_id}", headers=h2)
    assert denied.status_code == 404

    write_user = client.post(
        f"/api/v1/sessions/{session_id}/chat",
        headers=h1,
        json={"role": "user", "content": "你好", "model_meta": {}},
    )
    write_assistant = client.post(
        f"/api/v1/sessions/{session_id}/chat",
        headers=h1,
        json={"role": "assistant", "content": "您好", "model_meta": {}},
    )
    assert write_user.status_code == 200
    assert write_assistant.status_code == 200

    chat_list = client.get(f"/api/v1/sessions/{session_id}/chat", headers=h1)
    assert chat_list.status_code == 200
    records = chat_list.json()
    assert [r["role"] for r in records] == ["user", "assistant"]

    delete_resp = client.delete(f"/api/v1/sessions/{session_id}", headers=h1)
    assert delete_resp.status_code == 200

    after_delete = client.get(f"/api/v1/sessions/{session_id}", headers=h1)
    assert after_delete.status_code == 404


def test_generation_job_session_binding(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)

    from app.api.v2 import generation as generation_api
    from app.services.generation.job_store import GenerationJobStore

    class _NoopRunner:
        async def start_job(self, job_id: str, from_stage=None):  # noqa: ARG002
            return True

    monkeypatch.setattr(generation_api, "job_store", GenerationJobStore(tmp_path / "jobs"))
    monkeypatch.setattr(generation_api, "generation_runner", _NoopRunner())

    client = TestClient(app)
    h1 = {"X-Workspace-Id": "ws-a"}
    h2 = {"X-Workspace-Id": "ws-b"}

    created = client.post("/api/v1/sessions", headers=h1, json={"title": "生成会话"})
    assert created.status_code == 200
    session_id = created.json()["id"]

    source_resp = client.post(
        f"/api/v1/sessions/{session_id}/sources/text",
        headers=h1,
        json={"name": "素材", "content": "测试内容"},
    )
    assert source_resp.status_code == 200
    source_id = source_resp.json()["id"]

    create_ok = client.post(
        "/api/v2/generation/jobs",
        headers=h1,
        json={
            "topic": "测试主题",
            "session_id": session_id,
            "source_ids": [source_id],
            "num_pages": 3,
            "mode": "auto",
        },
    )
    assert create_ok.status_code == 200
    assert create_ok.json()["session_id"] == session_id

    create_denied = client.post(
        "/api/v2/generation/jobs",
        headers=h2,
        json={
            "topic": "测试主题",
            "session_id": session_id,
            "source_ids": [source_id],
            "num_pages": 3,
            "mode": "auto",
        },
    )
    assert create_denied.status_code == 404

    create_auto = client.post(
        "/api/v2/generation/jobs",
        headers=h1,
        json={
            "topic": "自动创建会话",
            "num_pages": 3,
            "mode": "auto",
        },
    )
    assert create_auto.status_code == 200
    assert create_auto.json()["session_id"]


def test_latest_presentation_read_repair_and_write_back(monkeypatch, tmp_path):
    store = _install_temp_session_store(monkeypatch, tmp_path)

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-repair"}
    created = client.post("/api/v1/sessions", headers=headers, json={"title": "修复测试"})
    assert created.status_code == 200
    session_id = created.json()["id"]

    bad_presentation = {
        "presentationId": "pres-bad",
        "title": "坏结构演示稿",
        "slides": [
            {
                "slideId": "slide-1",
                "layoutType": "two-column-compare",
                "layoutId": "two-column-compare",
                "contentData": {
                    "title": "核心框架",
                    "items": [
                        {"title": "要点一", "description": "描述一"},
                        {"title": "要点二", "description": "描述二"},
                        {"title": "要点三", "description": "描述三"},
                    ],
                },
                "components": [],
            }
        ],
    }
    asyncio.run(store.save_presentation(session_id=session_id, payload=bad_presentation))

    latest = client.get(f"/api/v1/sessions/{session_id}/presentations/latest", headers=headers)
    assert latest.status_code == 200
    body = latest.json()
    repaired_content = body["presentation"]["slides"][0]["contentData"]
    assert "left" in repaired_content
    assert "right" in repaired_content
    assert isinstance(repaired_content["left"]["items"], list)
    assert isinstance(repaired_content["right"]["items"], list)

    with sqlite3.connect(store._db_path) as conn:  # noqa: SLF001
        row = conn.execute(
            """
            SELECT payload_json
            FROM session_presentations
            WHERE session_id=?
            ORDER BY version_no DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
    assert row is not None
    persisted = json.loads(row[0])
    persisted_content = persisted["slides"][0]["contentData"]
    assert "left" in persisted_content
    assert "right" in persisted_content

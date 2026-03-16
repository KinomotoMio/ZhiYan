import asyncio
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app.main import app


def _install_temp_session_store(monkeypatch, tmp_path):
    import app.services.sessions as sessions_pkg
    from app.api.v1 import chat as chat_api
    from app.api.v1 import sessions as sessions_api
    from app.api.v1 import workspaces as workspaces_api
    from app.api.v1 import workspace_sources as workspace_sources_api
    from app.api.v2 import generation as generation_api
    from app.services.sessions.store import SessionStore

    store = SessionStore(tmp_path / "zhiyan-test.db", tmp_path / "uploads")
    asyncio.run(store.init())

    monkeypatch.setattr(sessions_pkg, "session_store", store)
    monkeypatch.setattr(sessions_api, "session_store", store)
    monkeypatch.setattr(chat_api, "session_store", store)
    monkeypatch.setattr(workspace_sources_api, "session_store", store)
    monkeypatch.setattr(workspaces_api, "session_store", store)
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
        "/api/v1/workspace/sources/text",
        headers=h1,
        json={"name": "素材", "content": "测试内容"},
    )
    assert source_resp.status_code == 200
    source_id = source_resp.json()["id"]
    link_resp = client.post(
        f"/api/v1/sessions/{session_id}/sources/link",
        headers=h1,
        json={"source_ids": [source_id]},
    )
    assert link_resp.status_code == 200

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
    created_job_id = create_ok.json()["job_id"]
    job_detail = client.get(f"/api/v2/generation/jobs/{created_job_id}", headers=h1)
    assert job_detail.status_code == 200
    hints = job_detail.json()["request"]["source_hints"]
    assert hints["total_count"] == 1
    assert hints["text_count"] == 1
    assert hints["image_count"] == 0
    assert hints["data_file_count"] == 0

    detail = client.get(f"/api/v1/sessions/{session_id}", headers=h1)
    assert detail.status_code == 200
    latest_generation_job = detail.json().get("latest_generation_job")
    assert latest_generation_job is not None
    assert latest_generation_job["job_id"] == created_job_id
    assert latest_generation_job["status"] == "pending"

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

    presentation = {
        "presentationId": "pres-ready",
        "title": "已有稿件",
        "slides": [
            {
                "slideId": "slide-1",
                "layoutType": "bullet-with-icons",
                "layoutId": "bullet-with-icons",
                "contentData": {"title": "测试", "items": []},
                "components": [],
            }
        ],
    }
    saved = client.put(
        f"/api/v1/sessions/{session_id}/presentations/latest",
        headers=h1,
        json={"presentation": presentation, "source": "chat"},
    )
    assert saved.status_code == 200

    create_conflict = client.post(
        "/api/v2/generation/jobs",
        headers=h1,
        json={
            "topic": "禁止在已有稿件会话生成",
            "session_id": session_id,
            "source_ids": [source_id],
            "num_pages": 3,
            "mode": "auto",
        },
    )
    assert create_conflict.status_code == 409


def test_workspace_source_link_acl_and_content_acl(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)

    client = TestClient(app)
    h1 = {"X-Workspace-Id": "ws-a"}
    h2 = {"X-Workspace-Id": "ws-b"}

    sess_a = client.post("/api/v1/sessions", headers=h1, json={"title": "A"}).json()["id"]
    sess_b = client.post("/api/v1/sessions", headers=h2, json={"title": "B"}).json()["id"]

    source_resp = client.post(
        "/api/v1/workspace/sources/text",
        headers=h1,
        json={"name": "跨空间素材", "content": "only ws-a can use"},
    )
    assert source_resp.status_code == 200
    source_id = source_resp.json()["id"]

    denied_link = client.post(
        f"/api/v1/sessions/{sess_b}/sources/link",
        headers=h2,
        json={"source_ids": [source_id]},
    )
    assert denied_link.status_code == 409

    fake_link = client.post(
        f"/api/v1/sessions/{sess_b}/sources/link",
        headers=h2,
        json={"source_ids": ["src-does-not-exist"]},
    )
    assert fake_link.status_code == 404

    link_ok = client.post(
        f"/api/v1/sessions/{sess_a}/sources/link",
        headers=h1,
        json={"source_ids": [source_id]},
    )
    assert link_ok.status_code == 200

    content_ok = client.get(
        f"/api/v1/sessions/{sess_a}/sources/{source_id}/content",
        headers=h1,
    )
    assert content_ok.status_code == 200
    assert "only ws-a can use" in content_ok.json()["content"]

    content_denied = client.get(
        f"/api/v1/sessions/{sess_b}/sources/{source_id}/content",
        headers=h2,
    )
    assert content_denied.status_code == 404


def test_unlink_source_is_idempotent(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-a"}

    session_resp = client.post("/api/v1/sessions", headers=headers, json={"title": "S1"})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]

    source_resp = client.post(
        "/api/v1/workspace/sources/text",
        headers=headers,
        json={"name": "待取消素材", "content": "unlink me"},
    )
    assert source_resp.status_code == 200
    source_id = source_resp.json()["id"]

    linked = client.post(
        f"/api/v1/sessions/{session_id}/sources/link",
        headers=headers,
        json={"source_ids": [source_id]},
    )
    assert linked.status_code == 200

    first_unlink = client.delete(
        f"/api/v1/sessions/{session_id}/sources/{source_id}/link",
        headers=headers,
    )
    assert first_unlink.status_code == 200
    assert first_unlink.json()["ok"] is True

    second_unlink = client.delete(
        f"/api/v1/sessions/{session_id}/sources/{source_id}/link",
        headers=headers,
    )
    assert second_unlink.status_code == 200
    assert second_unlink.json()["ok"] is True

    sources = client.get(f"/api/v1/sessions/{session_id}/sources", headers=headers)
    assert sources.status_code == 200
    assert sources.json() == []


def test_put_latest_presentation_workspace_isolation(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)

    client = TestClient(app)
    h1 = {"X-Workspace-Id": "ws-a"}
    h2 = {"X-Workspace-Id": "ws-b"}

    created = client.post("/api/v1/sessions", headers=h1, json={"title": "latest"})
    assert created.status_code == 200
    session_id = created.json()["id"]

    presentation = {
        "presentationId": "pres-1",
        "title": "测试稿",
        "slides": [
            {
                "slideId": "slide-1",
                "layoutType": "bullet-with-icons",
                "layoutId": "bullet-with-icons",
                "contentData": {"title": "测试", "items": []},
                "components": [],
            }
        ],
    }

    ok = client.put(
        f"/api/v1/sessions/{session_id}/presentations/latest",
        headers=h1,
        json={"presentation": presentation, "source": "chat"},
    )
    assert ok.status_code == 200
    assert ok.json()["is_snapshot"] is False

    denied = client.put(
        f"/api/v1/sessions/{session_id}/presentations/latest",
        headers=h2,
        json={"presentation": presentation, "source": "chat"},
    )
    assert denied.status_code == 404


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


def test_workspace_source_dedup_and_cross_workspace_isolation(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)
    client = TestClient(app)
    h1 = {"X-Workspace-Id": "ws-a"}
    h2 = {"X-Workspace-Id": "ws-b"}

    first = client.post(
        "/api/v1/workspace/sources/text",
        headers=h1,
        json={"name": "文档A", "content": "same-content"},
    )
    assert first.status_code == 200
    first_payload = first.json()

    second = client.post(
        "/api/v1/workspace/sources/text",
        headers=h1,
        json={"name": "文档A-重复", "content": "same-content"},
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["id"] == first_payload["id"]
    assert second_payload["deduped"] is True

    cross = client.post(
        "/api/v1/workspace/sources/text",
        headers=h2,
        json={"name": "文档B", "content": "same-content"},
    )
    assert cross.status_code == 200
    cross_payload = cross.json()
    assert cross_payload["id"] != first_payload["id"]
    assert not cross_payload.get("deduped", False)


def test_workspace_sources_link_count_and_bulk_delete_cascade(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)
    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-a"}

    session_resp = client.post("/api/v1/sessions", headers=headers, json={"title": "S1"})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]

    source_resp = client.post(
        "/api/v1/workspace/sources/text",
        headers=headers,
        json={"name": "可删除素材", "content": "delete me"},
    )
    assert source_resp.status_code == 200
    source_id = source_resp.json()["id"]

    link_resp = client.post(
        f"/api/v1/sessions/{session_id}/sources/link",
        headers=headers,
        json={"source_ids": [source_id]},
    )
    assert link_resp.status_code == 200

    listed = client.get(
        "/api/v1/workspace/sources",
        headers=headers,
        params={"sort": "linked_desc"},
    )
    assert listed.status_code == 200
    rows = listed.json()
    row = next(item for item in rows if item["id"] == source_id)
    assert row["linked_session_count"] == 1

    deleted = client.post(
        "/api/v1/workspace/sources/bulk-delete",
        headers=headers,
        json={"source_ids": [source_id]},
    )
    assert deleted.status_code == 200
    assert source_id in deleted.json()["deleted_ids"]

    session_sources = client.get(f"/api/v1/sessions/{session_id}/sources", headers=headers)
    assert session_sources.status_code == 200
    assert session_sources.json() == []


def test_workspaces_current_and_owner_unique_index(monkeypatch, tmp_path):
    store = _install_temp_session_store(monkeypatch, tmp_path)
    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-current"}

    current = client.get("/api/v1/workspaces/current", headers=headers)
    assert current.status_code == 200
    payload = current.json()
    assert payload["id"] == "ws-current"

    with sqlite3.connect(store._db_path) as conn:  # noqa: SLF001
        conn.execute(
            """
            UPDATE workspaces
            SET owner_type='user', owner_id='u-1'
            WHERE id=?
            """,
            ("ws-current",),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO workspaces(id, owner_type, owner_id, created_at, last_seen_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                ("ws-other", "user", "u-1", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
            )

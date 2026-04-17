import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models.generation import GenerationJob, GenerationRequestData, StageStatus
from app.services.generation.event_bus import GenerationEventBus
from app.services.generation.job_store import GenerationJobStore
from app.services.generation.runner import GenerationRunner
from app.services.sessions.store import SessionStore
from app.services.generation.agentic.types import AssistantMessage, ToolCall
from tests.conftest import FakeModel


def _install_temp_session_store(monkeypatch, tmp_path: Path):
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
    return store


def _install_runtime(monkeypatch, tmp_path: Path) -> GenerationRunner:
    from app.api.v1 import sessions as sessions_api

    store = GenerationJobStore(tmp_path / "jobs")
    bus = GenerationEventBus()
    runner = GenerationRunner(store, bus)
    monkeypatch.setattr(sessions_api, "job_store", store)
    monkeypatch.setattr(sessions_api, "event_bus", bus)
    monkeypatch.setattr(sessions_api, "generation_runner", runner)
    return runner


def _create_session(client: TestClient, headers: dict[str, str], title: str) -> str:
    response = client.post("/api/v1/sessions", headers=headers, json={"title": title})
    assert response.status_code == 200
    return response.json()["id"]


def _slidev_deck_payload(page_count: int) -> dict:
    slides = ["# AI Agent Runtime 架构演进"]
    for slide_number in range(2, page_count + 1):
        slides.append(f"# 第 {slide_number} 页\n\n- 这是第 {slide_number} 页的 Slidev 内容")
    return {
        "title": "AI Agent Runtime 架构演进",
        "selectedStyleId": "tech-launch",
        "markdown": "---\ntitle: AI Agent Runtime 架构演进\n---\n\n" + "\n\n---\n\n".join(slides) + "\n",
    }


def _slidev_deck_model(page_count: int) -> FakeModel:
    payload = _slidev_deck_payload(page_count)
    return FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="submit_slidev_deck",
                        args=payload,
                        tool_call_id="call-submit-slidev-deck",
                    )
                ]
            ),
            AssistantMessage(content="slidev deck submitted"),
        ]
    )


def test_create_generation_job_builds_agent_workspace(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)

    from app.api.v1 import sessions as sessions_api

    class _NoopRunner:
        async def start_job(self, job_id: str, from_stage=None):  # noqa: ARG002
            return True

    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(sessions_api, "job_store", GenerationJobStore(tmp_path / "jobs"))
    monkeypatch.setattr(sessions_api, "generation_runner", _NoopRunner())

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-workspace"}
    session_id = _create_session(client, headers, "workspace")

    source_resp = client.post(
        "/api/v1/workspace/sources/text",
        headers=headers,
        json={"name": "素材一", "content": "这是一段关于 agent runtime 的解析文本。"},
    )
    assert source_resp.status_code == 200
    source_id = source_resp.json()["id"]

    create_resp = client.post(
        f"/api/v1/sessions/{session_id}/generation/jobs",
        headers=headers,
        json={
            "topic": "生成一个关于 AgentLoop 集成 ZhiYan 的演示稿",
            "source_ids": [source_id],
            "num_pages": 4,
            "mode": "auto",
            "output_mode": "slidev",
        },
    )
    assert create_resp.status_code == 200
    job_id = create_resp.json()["job_id"]

    job_detail = client.get(f"/api/v1/sessions/{session_id}/generation/jobs/{job_id}", headers=headers)
    assert job_detail.status_code == 200
    workspace_meta = job_detail.json()["document_metadata"]["agent_workspace"]
    workspace_root = Path(workspace_meta["root"])
    assert workspace_root.exists()
    assert (workspace_root / "request.json").exists()
    assert (workspace_root / "sources" / "manifest.json").exists()
    assert (workspace_root / "sources" / "combined.md").exists()

    manifest = json.loads((workspace_root / "sources" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_count"] == 1
    assert manifest["sources"][0]["id"] == source_id
    assert manifest["sources"][0]["parsed_content_available"] is True


def test_agentic_auto_job_generates_slidev_deck(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)
    runner = _install_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "strong_model", "openai:gpt-4o")
    monkeypatch.setattr(settings, "openai_api_key", "token")

    from app.services.generation import runner as runner_mod

    async def fake_verify(state, progress=None, enable_vision=True):  # noqa: ARG001
        if progress:
            await progress("verify", 1, 1, "验证完成")
        state.verification_issues = []

    async def fake_prepare_slidev_deck_artifact(**kwargs):  # noqa: ANN003
        markdown = str(kwargs["markdown"])
        slides = [
            {
                "index": index,
                "slide_id": f"slide-{index + 1}",
                "title": "AI Agent Runtime 架构演进" if index == 0 else f"第 {index + 1} 页",
                "role": "cover" if index == 0 else "narrative",
                "layout": "default",
            }
            for index in range(4)
        ]
        return {
            "title": "AI Agent Runtime 架构演进",
            "markdown": markdown,
            "meta": {
                "title": "AI Agent Runtime 架构演进",
                "slide_count": 4,
                "slides": slides,
                "selected_style_id": "tech-launch",
                "validation": {"ok": True, "issues": []},
                "review": {"issues": []},
            },
            "presentation": {
                "presentationId": "pres-slidev-agent",
                "title": "AI Agent Runtime 架构演进",
                "slides": [
                    {
                        "slideId": slide["slide_id"],
                        "layoutType": "blank",
                        "layoutId": "blank",
                        "contentData": {"title": slide["title"]},
                        "components": [],
                    }
                    for slide in slides
                ],
            },
            "selected_style_id": "tech-launch",
            "selected_style": {"name": "tech-launch", "theme": "seriph"},
            "selected_theme": {"theme": "seriph"},
        }

    async def fake_build_slidev_spa(*, out_dir, **kwargs):  # noqa: ANN003
        build_out_dir = Path(out_dir)
        build_out_dir.mkdir(parents=True, exist_ok=True)
        (build_out_dir / "index.html").write_text("<html><body>slidev build</body></html>", encoding="utf-8")
        assets_dir = build_out_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        (assets_dir / "entry.js").write_text("console.log('slidev-build');", encoding="utf-8")

    monkeypatch.setattr(runner_mod, "stage_verify_slides", fake_verify)
    monkeypatch.setattr(runner_mod, "prepare_slidev_deck_artifact", fake_prepare_slidev_deck_artifact)
    monkeypatch.setattr(runner_mod, "build_slidev_spa", fake_build_slidev_spa)

    slidev_model = _slidev_deck_model(4)
    models = [slidev_model]

    def fake_model_factory():
        return models.pop(0)

    monkeypatch.setattr(runner, "_create_agent_model_client", fake_model_factory)

    async def run_inline(job_id: str, from_stage=None):
        await runner._run_job(job_id, from_stage)  # noqa: SLF001
        return True

    monkeypatch.setattr(runner, "start_job", run_inline)

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-agent-slidev"}
    session_id = _create_session(client, headers, "agent-slidev")

    source_resp = client.post(
        "/api/v1/workspace/sources/text",
        headers=headers,
        json={"name": "背景材料", "content": "AgentLoop 会直接产出 Slidev markdown deck。"},
    )
    assert source_resp.status_code == 200

    create_resp = client.post(
        f"/api/v1/sessions/{session_id}/generation/jobs",
        headers=headers,
        json={
            "topic": "生成一个适合产品发布会的 Slidev 演示稿",
            "source_ids": [source_resp.json()["id"]],
            "num_pages": 4,
            "mode": "auto",
            "output_mode": "slidev",
        },
    )
    assert create_resp.status_code == 200

    job_detail = client.get(
        f"/api/v1/sessions/{session_id}/generation/jobs/{create_resp.json()['job_id']}",
        headers=headers,
    )
    assert job_detail.status_code == 200
    body = job_detail.json()
    assert body["status"] == "completed"
    assert body["output_mode"] == "slidev"
    assert len(body["slides"]) == 4
    assert body["presentation"] is not None
    workspace_root = Path(body["document_metadata"]["agent_workspace"]["root"])
    assert (workspace_root / "artifacts" / "slides.md").exists()
    assert (workspace_root / "artifacts" / "slidev-build" / "index.html").exists()
    slidev_payload = body["document_metadata"]["agent_outputs"]["slidev_deck"]
    assert slidev_payload["markdown"].startswith("---")
    assert slidev_payload["meta"]["slide_count"] == 4
    assert body["document_metadata"]["agent_outputs"]["slidev_build"]["slide_count"] == 4

    latest = client.get(f"/api/v1/sessions/{session_id}/presentations/latest", headers=headers)
    assert latest.status_code == 200
    latest_payload = latest.json()
    assert latest_payload["output_mode"] == "slidev"
    assert latest_payload["artifacts"]["slidev_deck"]["selected_style_id"] == "tech-launch"

    latest_slidev = client.get(
        f"/api/v1/sessions/{session_id}/presentations/latest/slidev",
        headers=headers,
    )
    assert latest_slidev.status_code == 200
    assert latest_slidev.json()["meta"]["slide_count"] == 4

    latest_build = client.get(
        f"/api/v1/sessions/{session_id}/presentations/latest/slidev/build",
        headers=headers,
    )
    assert latest_build.status_code == 200
    assert "slidev build" in latest_build.text
    assert set(tool["name"] for tool in slidev_model.seen_tools[0]) == {
        "read_file",
        "read_skill_resource",
        "load_skill",
        "submit_slidev_deck",
    }


def test_agentic_auto_job_accepts_slidev_page_count_mismatch_as_soft_signal(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)
    runner = _install_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "strong_model", "openai:gpt-4o")
    monkeypatch.setattr(settings, "openai_api_key", "token")

    from app.services.generation import runner as runner_mod

    async def fake_verify(state, progress=None, enable_vision=True):  # noqa: ARG001
        if progress:
            await progress("verify", 1, 1, "验证完成")
        state.verification_issues = []

    async def fake_prepare_slidev_deck_artifact(**kwargs):  # noqa: ANN003
        markdown = str(kwargs["markdown"])
        slide_count = markdown.count("\n\n---\n\n") + 1
        slides = [
            {
                "index": index,
                "slide_id": f"slide-{index + 1}",
                "title": "AI Agent Runtime 架构演进" if index == 0 else f"第 {index + 1} 页",
                "role": "cover" if index == 0 else "narrative",
                "layout": "default",
            }
            for index in range(slide_count)
        ]
        return {
            "title": "AI Agent Runtime 架构演进",
            "markdown": markdown,
            "meta": {
                "title": "AI Agent Runtime 架构演进",
                "slide_count": slide_count,
                "slides": slides,
                "selected_style_id": "tech-launch",
                "page_count_check": {
                    "expected_slide_count": int(kwargs["expected_pages"]),
                    "submitted_slide_count": slide_count,
                    "matches_expected": slide_count == int(kwargs["expected_pages"]),
                    "mode": "soft",
                },
            },
            "selected_style_id": "tech-launch",
        }

    async def fake_build_slidev_spa(*, out_dir, **kwargs):  # noqa: ANN003
        build_out_dir = Path(out_dir)
        build_out_dir.mkdir(parents=True, exist_ok=True)
        (build_out_dir / "index.html").write_text("<html><body>slidev build</body></html>", encoding="utf-8")

    monkeypatch.setattr(runner_mod, "stage_verify_slides", fake_verify)
    monkeypatch.setattr(runner_mod, "prepare_slidev_deck_artifact", fake_prepare_slidev_deck_artifact)
    monkeypatch.setattr(runner_mod, "build_slidev_spa", fake_build_slidev_spa)

    slidev_model = _slidev_deck_model(5)
    models = [slidev_model]

    def fake_model_factory():
        return models.pop(0)

    monkeypatch.setattr(runner, "_create_agent_model_client", fake_model_factory)

    async def run_inline(job_id: str, from_stage=None):
        await runner._run_job(job_id, from_stage)  # noqa: SLF001
        return True

    monkeypatch.setattr(runner, "start_job", run_inline)

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-agent-slidev-retry"}
    session_id = _create_session(client, headers, "agent-slidev-retry")

    source_resp = client.post(
        "/api/v1/workspace/sources/text",
        headers=headers,
        json={"name": "背景材料", "content": "AgentLoop 会直接产出 Slidev markdown deck。"},
    )
    assert source_resp.status_code == 200

    create_resp = client.post(
        f"/api/v1/sessions/{session_id}/generation/jobs",
        headers=headers,
        json={
            "topic": "生成一个适合产品发布会的 Slidev 演示稿",
            "source_ids": [source_resp.json()["id"]],
            "num_pages": 4,
            "mode": "auto",
            "output_mode": "slidev",
        },
    )
    assert create_resp.status_code == 200

    job_detail = client.get(
        f"/api/v1/sessions/{session_id}/generation/jobs/{create_resp.json()['job_id']}",
        headers=headers,
    )
    assert job_detail.status_code == 200
    body = job_detail.json()
    assert body["status"] == "completed"
    assert len(body["slides"]) == 5
    tool_events = list((body.get("run_metadata") or {}).get("tool_events") or [])
    slidev_submits = [
        event
        for event in tool_events
        if (event.get("result") or {}).get("tool_name") == "submit_slidev_deck"
    ]
    assert slidev_submits
    assert all(not (event.get("result") or {}).get("is_error") for event in slidev_submits)
    submit_content = slidev_submits[0]["result"]["content"]
    assert submit_content["expected_slide_count"] == 4
    assert submit_content["submitted_slide_count_normalized"] == 5
    assert submit_content["matches_expected"] is False
    slidev_meta = body["document_metadata"]["agent_outputs"]["slidev_deck"]["meta"]
    assert slidev_meta["page_count_check"]["expected_slide_count"] == 4
    assert slidev_meta["page_count_check"]["submitted_slide_count"] == 5
    assert slidev_meta["page_count_check"]["matches_expected"] is False


def test_agentic_auto_job_exposes_artifact_when_slidev_render_fails(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)
    runner = _install_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "strong_model", "openai:gpt-4o")
    monkeypatch.setattr(settings, "openai_api_key", "token")

    from app.services.generation import runner as runner_mod

    async def fake_verify(state, progress=None, enable_vision=True):  # noqa: ARG001
        if progress:
            await progress("verify", 1, 1, "验证完成")
        state.verification_issues = []

    async def fake_prepare_slidev_deck_artifact(**kwargs):  # noqa: ANN003
        markdown = str(kwargs["markdown"])
        slides = [
            {
                "index": index,
                "slide_id": f"slide-{index + 1}",
                "title": "AI Agent Runtime 架构演进" if index == 0 else f"第 {index + 1} 页",
                "role": "cover" if index == 0 else "narrative",
                "layout": "default",
            }
            for index in range(4)
        ]
        return {
            "title": "AI Agent Runtime 架构演进",
            "markdown": markdown,
            "meta": {
                "title": "AI Agent Runtime 架构演进",
                "slide_count": 4,
                "slides": slides,
                "selected_style_id": "tech-launch",
                "validation": {"ok": True, "issues": []},
                "review": {"issues": []},
            },
            "presentation": {
                "presentationId": "pres-slidev-agent",
                "title": "AI Agent Runtime 架构演进",
                "slides": [
                    {
                        "slideId": slide["slide_id"],
                        "layoutType": "blank",
                        "layoutId": "blank",
                        "contentData": {"title": slide["title"]},
                        "components": [],
                    }
                    for slide in slides
                ],
            },
            "selected_style_id": "tech-launch",
            "selected_style": {"name": "tech-launch", "theme": "seriph"},
            "selected_theme": {"theme": "seriph"},
        }

    async def fake_build_slidev_spa(**kwargs):  # noqa: ANN003
        raise RuntimeError(
            "Slidev build failed: Slide 2 starts with `layout:`/`class:` lines but does not wrap them in a Slidev frontmatter fence."
        )

    monkeypatch.setattr(runner_mod, "stage_verify_slides", fake_verify)
    monkeypatch.setattr(runner_mod, "prepare_slidev_deck_artifact", fake_prepare_slidev_deck_artifact)
    monkeypatch.setattr(runner_mod, "build_slidev_spa", fake_build_slidev_spa)

    slidev_model = _slidev_deck_model(4)
    models = [slidev_model]

    def fake_model_factory():
        return models.pop(0)

    monkeypatch.setattr(runner, "_create_agent_model_client", fake_model_factory)

    async def run_inline(job_id: str, from_stage=None):
        await runner._run_job(job_id, from_stage)  # noqa: SLF001
        return True

    monkeypatch.setattr(runner, "start_job", run_inline)

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-agent-slidev-render-fail"}
    session_id = _create_session(client, headers, "agent-slidev-render-fail")

    source_resp = client.post(
        "/api/v1/workspace/sources/text",
        headers=headers,
        json={"name": "背景材料", "content": "AgentLoop 会直接产出 Slidev markdown deck。"},
    )
    assert source_resp.status_code == 200

    create_resp = client.post(
        f"/api/v1/sessions/{session_id}/generation/jobs",
        headers=headers,
        json={
            "topic": "生成一个适合产品发布会的 Slidev 演示稿",
            "source_ids": [source_resp.json()["id"]],
            "num_pages": 4,
            "mode": "auto",
            "output_mode": "slidev",
        },
    )
    assert create_resp.status_code == 200

    job_detail = client.get(
        f"/api/v1/sessions/{session_id}/generation/jobs/{create_resp.json()['job_id']}",
        headers=headers,
    )
    assert job_detail.status_code == 200
    body = job_detail.json()
    assert body["status"] == "render_failed"
    assert body["artifact_status"] == "ready"
    assert body["render_status"] == "failed"
    assert body["artifact_available"] is True
    assert body["render_available"] is False
    assert "frontmatter fence" in body["render_error"]

    latest = client.get(f"/api/v1/sessions/{session_id}/presentations/latest", headers=headers)
    assert latest.status_code == 200
    latest_payload = latest.json()
    assert latest_payload["artifact_status"] == "ready"
    assert latest_payload["render_status"] == "failed"
    assert latest_payload["render_available"] is False
    assert latest_payload["artifacts"]["slidev_deck"]["selected_style_id"] == "tech-launch"
    assert "slidev_build" not in latest_payload["artifacts"]

    latest_slidev = client.get(
        f"/api/v1/sessions/{session_id}/presentations/latest/slidev",
        headers=headers,
    )
    assert latest_slidev.status_code == 200
    assert latest_slidev.json()["build_url"] is None
    assert latest_slidev.json()["render_status"] == "failed"

    latest_build = client.get(
        f"/api/v1/sessions/{session_id}/presentations/latest/slidev/build",
        headers=headers,
    )
    assert latest_build.status_code == 404


def test_runner_stage_does_not_use_asyncio_wait_for(monkeypatch, tmp_path):
    store = GenerationJobStore(tmp_path / "jobs")
    bus = GenerationEventBus()
    runner = GenerationRunner(store, bus)
    workspace_root = tmp_path / "workspace"
    (workspace_root / "artifacts").mkdir(parents=True, exist_ok=True)

    job = GenerationJob(
        job_id="job-no-stage-timeout",
        request=GenerationRequestData(topic="去掉 stage timeout", resolved_content="测试内容"),
        document_metadata={"agent_workspace": {"root": str(workspace_root)}},
    )
    asyncio.run(store.create_job(job))

    from app.services.generation import runner as runner_mod

    async def _fail_if_called(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("GenerationRunner should not call asyncio.wait_for for stage execution")

    monkeypatch.setattr(runner_mod.asyncio, "wait_for", _fail_if_called)

    async def _case():
        state = runner._build_state(job)  # noqa: SLF001

        async def stage_coro():
            await asyncio.sleep(0)

        await runner._run_stage(job, state, stage=StageStatus.OUTLINE, stage_coro=stage_coro())  # noqa: SLF001

    asyncio.run(_case())

    saved = asyncio.run(store.get_job(job.job_id))
    assert saved is not None
    assert saved.stage_results[-1].stage == StageStatus.OUTLINE
    assert saved.stage_results[-1].status == "completed"
    assert saved.stage_results[-1].timeout_seconds is None

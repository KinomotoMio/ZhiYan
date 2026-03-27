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


def _outline_payload(page_count: int) -> dict:
    items = [
        {"slideNumber": 1, "title": "封面", "role": "cover", "objective": "设置主题"},
        {"slideNumber": 2, "title": "目录", "role": "agenda", "objective": "说明结构"},
    ]
    for slide_number in range(3, page_count):
        items.append(
            {
                "slideNumber": slide_number,
                "title": f"核心内容 {slide_number - 2}",
                "role": "narrative",
                "objective": "展开核心论点",
                "keyPoints": [f"要点 {slide_number - 2}A", f"要点 {slide_number - 2}B"],
            }
        )
    items.append({"slideNumber": page_count, "title": "结尾", "role": "closing", "objective": "收束"})
    return {
        "title": "AI Agent Runtime 架构演进",
        "subtitle": "From Workflow to Runtime",
        "storyline": "用 runtime 视角解释从简单调用到 agent 工作区的演进。",
        "items": items,
    }


def _presentation_payload(page_count: int) -> dict:
    slides = [
        {
            "slideId": "slide-1",
            "layoutType": "intro-slide",
            "layoutId": "intro-slide",
            "contentData": {
                "title": "AI Agent Runtime 架构演进",
                "subtitle": "从简单调用，到可控工作区，再到长期演进内核",
            },
        },
        {
            "slideId": "slide-2",
            "layoutType": "outline-slide-rail",
            "layoutId": "outline-slide-rail",
            "contentData": {
                "title": "这次迁移先解决什么",
                "sections": [
                    {"title": "复用创建页入口", "description": "不改现有按钮和 editor 壳"},
                    {"title": "给 job 建 workspace", "description": "把 source manifest 和文本素材落盘"},
                    {"title": "单阶段生成", "description": "auto 模式直接进 presentation，不再先出 outline"},
                    {"title": "强模板适配", "description": "直接按最终 schema 填充页面"},
                ],
            },
        },
    ]
    for slide_number in range(3, page_count):
        slides.append(
            {
                "slideId": f"slide-{slide_number}",
                "layoutType": "bullet-with-icons-cards",
                "layoutId": "bullet-with-icons-cards",
                "contentData": {
                    "title": f"核心阶段 {slide_number - 2}",
                    "items": [
                        {"title": "工作区可读", "description": "Agent 通过文件工具读素材而不是只吃拼接文本"},
                        {"title": "模板直填", "description": "直接按最终 schema 产出可展示内容"},
                        {"title": "状态机兼容", "description": "继续复用 job、SSE、editor hydrate"},
                        {"title": "输出可替换", "description": "当前 presentation 只是前端适配层"},
                    ],
                },
                "speakerNotes": "强调这是临时适配，不是最终表示。",
            }
        )
    slides.append(
        {
            "slideId": f"slide-{page_count}",
            "layoutType": "thank-you",
            "layoutId": "thank-you",
            "contentData": {
                "title": "谢谢",
                "subtitle": "第一步先把创建页按钮打通，后面再继续升级生成表示。",
            },
        }
    )
    return {
        "title": "AI Agent Runtime 架构演进",
        "theme": {"primaryColor": "#5B8CFF"},
        "slides": slides,
    }


def _outline_model(page_count: int) -> FakeModel:
    payload = _outline_payload(page_count)
    return FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="submit_outline",
                        args=payload,
                        tool_call_id="call-submit-outline",
                    )
                ]
            ),
            AssistantMessage(content="outline submitted"),
        ]
    )


def _presentation_model(page_count: int) -> FakeModel:
    payload = _presentation_payload(page_count)
    return FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="submit_presentation",
                        args=payload,
                        tool_call_id="call-submit-presentation",
                    )
                ]
            ),
            AssistantMessage(content="presentation submitted"),
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


def test_agentic_auto_job_generates_presentation(monkeypatch, tmp_path):
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

    monkeypatch.setattr(runner_mod, "stage_verify_slides", fake_verify)

    presentation_model = _presentation_model(4)
    models = [presentation_model]

    def fake_model_factory():
        return models.pop(0)

    monkeypatch.setattr(runner, "_create_agent_model_client", fake_model_factory)

    async def run_inline(job_id: str, from_stage=None):
        await runner._run_job(job_id, from_stage)  # noqa: SLF001
        return True

    monkeypatch.setattr(runner, "start_job", run_inline)

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-agent-auto"}
    session_id = _create_session(client, headers, "agent-auto")

    source_resp = client.post(
        "/api/v1/workspace/sources/text",
        headers=headers,
        json={"name": "背景材料", "content": "AgentLoop 将每个 job 变成一个带 workspace 的运行单元。"},
    )
    assert source_resp.status_code == 200

    create_resp = client.post(
        f"/api/v1/sessions/{session_id}/generation/jobs",
        headers=headers,
        json={
            "topic": "讲清楚 AgentLoop 集成到 ZhiYan 创建页的价值",
            "source_ids": [source_resp.json()["id"]],
            "num_pages": 4,
            "mode": "auto",
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
    assert len(body["slides"]) == 4
    assert body["presentation"] is not None
    assert body["presentation"]["slides"][0]["layoutType"] == "intro-slide"
    workspace_root = Path(body["document_metadata"]["agent_workspace"]["root"])
    assert (workspace_root / "artifacts" / "presentation.json").exists()

    agent_debug = body["document_metadata"]["agent_debug"]
    assert Path(agent_debug["root"]).exists()
    assert sorted(agent_debug["files"]) == [
        "model-presentation-request.json",
        "model-presentation-response.json",
        "runner-trace.json",
        "session-presentation.json",
        "tool-trace.ndjson",
    ]
    assert agent_debug["runs"]["presentation"]["stop_reason"] == "completed"
    assert "deck_metadata" not in body["document_metadata"]["agent_outputs"]
    assert "presentation" in body["document_metadata"]["agent_outputs"]
    assert (workspace_root / "artifacts" / "debug" / "session-presentation.json").exists()
    assert (workspace_root / "artifacts" / "debug" / "runner-trace.json").exists()
    assert set(tool["name"] for tool in presentation_model.seen_tools[0]) == {"read_file", "submit_presentation"}


def test_agentic_review_outline_job_waits_and_then_completes(monkeypatch, tmp_path):
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

    monkeypatch.setattr(runner_mod, "stage_verify_slides", fake_verify)

    models = [_outline_model(4), _presentation_model(4)]

    def fake_model_factory():
        return models.pop(0)

    monkeypatch.setattr(runner, "_create_agent_model_client", fake_model_factory)

    async def run_inline(job_id: str, from_stage=None):
        await runner._run_job(job_id, from_stage)  # noqa: SLF001
        return True

    monkeypatch.setattr(runner, "start_job", run_inline)

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-agent-review"}
    session_id = _create_session(client, headers, "agent-review")

    source_resp = client.post(
        "/api/v1/workspace/sources/text",
        headers=headers,
        json={"name": "资料", "content": "先审大纲，再继续生成 deck。"},
    )
    assert source_resp.status_code == 200

    create_resp = client.post(
        f"/api/v1/sessions/{session_id}/generation/jobs",
        headers=headers,
        json={
            "topic": "需要 review_outline 的演示稿",
            "source_ids": [source_resp.json()["id"]],
            "num_pages": 4,
            "mode": "review_outline",
        },
    )
    assert create_resp.status_code == 200
    job_id = create_resp.json()["job_id"]

    first_detail = client.get(f"/api/v1/sessions/{session_id}/generation/jobs/{job_id}", headers=headers)
    assert first_detail.status_code == 200
    assert first_detail.json()["status"] == "waiting_outline_review"
    assert len(first_detail.json()["outline"]["items"]) == 4

    accept_resp = client.post(
        f"/api/v1/sessions/{session_id}/generation/jobs/{job_id}/outline/accept",
        headers=headers,
        json={},
    )
    assert accept_resp.status_code == 200

    final_detail = client.get(f"/api/v1/sessions/{session_id}/generation/jobs/{job_id}", headers=headers)
    assert final_detail.status_code == 200
    assert final_detail.json()["status"] == "completed"
    assert len(final_detail.json()["presentation"]["slides"]) == 4


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

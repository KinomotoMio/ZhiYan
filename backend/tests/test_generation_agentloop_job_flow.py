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


def _html_deck_payload(page_count: int) -> dict:
    slides: list[dict[str, object]] = []
    slide_css = (
        ".slide-shell{display:grid;place-items:center;height:100%;"
        "background:linear-gradient(135deg,#f8fafc,#dbeafe);color:#0f172a;}"
    )
    for slide_number in range(1, page_count + 1):
        title = "AI Agent Runtime 架构演进" if slide_number == 1 else f"第 {slide_number} 页"
        slides.append(
            {
                "slideId": f"slide-{slide_number}",
                "title": title,
                "bodyHtml": (
                    "<div class='slide-shell'>"
                    f"<h2>{title}</h2>"
                    f"<p>这是第 {slide_number} 页的 HTML 演示内容。</p>"
                    "</div>"
                ),
                "scopedCss": slide_css,
            }
        )
    return {
        "title": "AI Agent Runtime 架构演进",
        "slides": slides,
    }


def _html_deck_model(page_count: int) -> FakeModel:
    payload = _html_deck_payload(page_count)
    return FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="submit_html_runtime_deck",
                        args=payload,
                        tool_call_id="call-submit-html-runtime-deck",
                    )
                ]
            ),
            AssistantMessage(content="html deck submitted"),
        ]
    )


def _slidev_deck_payload(page_count: int) -> dict:
    slides = ["# AI Agent Runtime 架构演进"]
    for slide_number in range(2, page_count + 1):
        slides.append(f"# 第 {slide_number} 页\n\n- 这是第 {slide_number} 页的 Slidev 内容")
    return {
        "title": "AI Agent Runtime 架构演进",
        "selectedStyleId": "tech-launch",
        "markdown": "---\ntitle: AI Agent Runtime 架构演进\n---\n\n" + "\n\n---\n\n".join(slides) + "\n",
    }


def _slidev_frontmatter_deck_payload(page_count: int) -> dict:
    slides = [
        "---\nlayout: cover\nclass: theme-tech-launch\n---\n\n# AI Agent Runtime 架构演进\n\n副标题",
    ]
    for slide_number in range(2, page_count + 1):
        slides.append(
            "---\n"
            "layout: default\n"
            "class: theme-tech-launch\n"
            "---\n\n"
            f"# 第 {slide_number} 页\n\n- 这是第 {slide_number} 页的 Slidev 内容"
        )
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


def _slidev_retrying_model(first_page_count: int, second_page_count: int) -> FakeModel:
    invalid_payload = _slidev_frontmatter_deck_payload(first_page_count)
    valid_payload = _slidev_deck_payload(second_page_count)
    return FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="submit_slidev_deck",
                        args=invalid_payload,
                        tool_call_id="call-submit-slidev-deck-invalid",
                    )
                ]
            ),
            AssistantMessage(content="第一次提交失败后等待重试"),
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="submit_slidev_deck",
                        args=valid_payload,
                        tool_call_id="call-submit-slidev-deck-valid",
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
    assert set(tool["name"] for tool in presentation_model.seen_tools[0]) == {
        "read_file",
        "read_skill_resource",
        "load_skill",
        "submit_presentation",
    }


def test_agentic_auto_job_generates_html_deck(monkeypatch, tmp_path):
    _install_temp_session_store(monkeypatch, tmp_path)
    runner = _install_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "strong_model", "openai:gpt-4o")
    monkeypatch.setattr(settings, "openai_api_key", "token")

    from app.services.generation import runner as runner_mod

    verify_called = False

    async def fake_verify(state, progress=None, enable_vision=True):  # noqa: ARG001
        nonlocal verify_called
        verify_called = True
        if progress:
            await progress("verify", 1, 1, "验证完成")
        state.verification_issues = []

    monkeypatch.setattr(runner_mod, "stage_verify_slides", fake_verify)

    html_model = _html_deck_model(4)
    models = [html_model]

    def fake_model_factory():
        return models.pop(0)

    monkeypatch.setattr(runner, "_create_agent_model_client", fake_model_factory)

    async def run_inline(job_id: str, from_stage=None):
        await runner._run_job(job_id, from_stage)  # noqa: SLF001
        return True

    monkeypatch.setattr(runner, "start_job", run_inline)

    client = TestClient(app)
    headers = {"X-Workspace-Id": "ws-agent-html"}
    session_id = _create_session(client, headers, "agent-html")

    source_resp = client.post(
        "/api/v1/workspace/sources/text",
        headers=headers,
        json={"name": "背景材料", "content": "AgentLoop 会直接产出 HTML 演示文件。"},
    )
    assert source_resp.status_code == 200

    create_resp = client.post(
        f"/api/v1/sessions/{session_id}/generation/jobs",
        headers=headers,
        json={
            "topic": "生成一个高美观 HTML 演示稿",
            "source_ids": [source_resp.json()["id"]],
            "num_pages": 4,
            "mode": "auto",
            "output_mode": "html",
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
    assert body["output_mode"] == "html"
    assert len(body["slides"]) == 4
    assert body["presentation"] is not None
    workspace_root = Path(body["document_metadata"]["agent_workspace"]["root"])
    assert (workspace_root / "artifacts" / "presentation.html").exists()
    assert (workspace_root / "artifacts" / "presentation.meta.json").exists()
    html_payload = body["document_metadata"]["agent_outputs"]["html_deck"]
    assert html_payload["html"].startswith("<!DOCTYPE html>")
    assert html_payload["meta"]["slide_count"] == 4

    latest = client.get(f"/api/v1/sessions/{session_id}/presentations/latest", headers=headers)
    assert latest.status_code == 200
    latest_payload = latest.json()
    assert latest_payload["output_mode"] == "html"
    assert latest_payload["artifacts"]["html_deck"]["slide_count"] == 4

    latest_html = client.get(f"/api/v1/sessions/{session_id}/presentations/latest/html", headers=headers)
    assert latest_html.status_code == 200
    assert "<section data-slide-id=" in latest_html.text

    latest_meta = client.get(
        f"/api/v1/sessions/{session_id}/presentations/latest/html/meta",
        headers=headers,
    )
    assert latest_meta.status_code == 200
    assert latest_meta.json()["slide_count"] == 4
    assert verify_called is False
    assert "source_brief" not in body["document_metadata"]
    assert set(tool["name"] for tool in html_model.seen_tools[0]) == {
        "read_file",
        "submit_html_runtime_deck",
    }


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


def test_agentic_auto_job_retries_slidev_submit_on_page_count_mismatch(monkeypatch, tmp_path):
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

    monkeypatch.setattr(runner_mod, "stage_verify_slides", fake_verify)
    monkeypatch.setattr(runner_mod, "prepare_slidev_deck_artifact", fake_prepare_slidev_deck_artifact)
    monkeypatch.setattr(runner_mod, "build_slidev_spa", fake_build_slidev_spa)

    slidev_model = _slidev_retrying_model(5, 4)
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
    tool_events = list((body.get("run_metadata") or {}).get("tool_events") or [])
    slidev_errors = [
        event
        for event in tool_events
        if (event.get("result") or {}).get("tool_name") == "submit_slidev_deck"
        and (event.get("result") or {}).get("is_error")
    ]
    assert slidev_errors
    first_error = slidev_errors[0]["result"]["content"]
    assert first_error["expected_slide_count"] == 4
    assert first_error["submitted_slide_count_raw"] > first_error["submitted_slide_count_normalized"]
    assert first_error["submitted_slide_count_normalized"] == 5
    assert first_error["page_count_check_stage"] == "submit_tool"
    retry_user_messages = [
        message.content
        for seen in slidev_model.seen_messages[1:]
        for message in seen
        if getattr(message, "role", "") == "user"
    ]
    assert any("raw=" in message and "normalized=" in message for message in retry_user_messages)


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
        raise RuntimeError("Slidev build failed: broken scaffold css")

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
    assert "broken scaffold css" in body["render_error"]

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

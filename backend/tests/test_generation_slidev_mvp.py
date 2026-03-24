from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelHTTPError

from app.core.config import settings
from app.main import app
from app.services.generation.agentic.types import AgenticMessage, AgenticModelClient, AssistantMessage, ToolCall, ToolResult, UserMessage
from app.services.generation.slidev_mvp import (
    SlidevMvpArtifacts,
    SlidevMvpService,
    SlidevMvpValidationError,
)
from app.services.skill_runtime.executor import execute_skill
from app.services.skill_runtime.registry import SkillRegistry


@dataclass
class StubModel(AgenticModelClient):
    responses: list[AssistantMessage]
    seen_messages: list[list[AgenticMessage]] | None = None

    async def complete(self, messages, tools) -> AssistantMessage:
        if self.seen_messages is not None:
            self.seen_messages.append(list(messages))
        return self.responses.pop(0)


class FakeSessionStore:
    def __init__(
        self,
        *,
        session_exists: bool = True,
        source_metas: list[dict] | None = None,
        source_content: str = "",
    ) -> None:
        self.session_exists = session_exists
        self.source_metas = source_metas or []
        self.source_content = source_content
        self.ensure_workspace_calls: list[str] = []
        self.session_calls: list[tuple[str, str]] = []
        self.source_lookup_calls: list[tuple[str, list[str]]] = []
        self.source_content_calls: list[tuple[str, str, list[str]]] = []

    async def ensure_workspace(self, workspace_id: str) -> None:
        self.ensure_workspace_calls.append(workspace_id)

    async def get_session(self, workspace_id: str, session_id: str) -> dict:
        self.session_calls.append((workspace_id, session_id))
        if not self.session_exists:
            raise ValueError("session not found")
        return {"id": session_id}

    async def get_workspace_sources_by_ids(self, workspace_id: str, source_ids: list[str]) -> list[dict]:
        self.source_lookup_calls.append((workspace_id, list(source_ids)))
        return list(self.source_metas)

    async def get_combined_source_content(self, workspace_id: str, session_id: str, source_ids: list[str]) -> str:
        self.source_content_calls.append((workspace_id, session_id, list(source_ids)))
        return self.source_content


def _slidev_markdown() -> str:
    return """---
theme: default
title: AI Product Architecture Evolution
---

# AI Product Architecture Evolution

---

## Why This Matters

- Cost pressure
- UX pressure

---

## Harness Layers

- loop
- tools
- context

---

## MVP Path

```mermaid
graph TD
  A[Input] --> B[Harness]
  B --> C[Slidev]
```

---

## Next Step

- Validate locally
- Decide migration boundary
"""


def _simple_markdown() -> str:
    return """---
theme: default
title: Mini Deck
---

# Cover

---

## Closing

- done
"""


def _comparison_mismatch_markdown() -> str:
    return """---
theme: default
title: Contract Drift
---

# Contract Drift

---

## Supposed Comparison

- option A
- option B
- option C

---

## Next Step

- decide
"""


def _quality_outline_items() -> list[dict[str, str | int]]:
    return [
        {"slide_number": 1, "title": "封面", "slide_role": "cover", "content_shape": "title-subtitle", "goal": "建立主题定位"},
        {"slide_number": 2, "title": "为什么现在要做", "slide_role": "context", "content_shape": "problem-bullets", "goal": "说明问题背景"},
        {"slide_number": 3, "title": "Harness 分层", "slide_role": "framework", "content_shape": "two-column-framework", "goal": "解释分层职责"},
        {"slide_number": 4, "title": "Slidev MVP 闭环", "slide_role": "detail", "content_shape": "diagram-callout", "goal": "说明实现闭环"},
        {"slide_number": 5, "title": "迁移边界", "slide_role": "comparison", "content_shape": "compare-grid", "goal": "澄清保留与迁移"},
        {"slide_number": 6, "title": "下一步", "slide_role": "closing", "content_shape": "next-step", "goal": "总结行动方向"},
    ]


def _quality_outline_items_five() -> list[dict[str, str | int]]:
    return [
        {"slide_number": 1, "title": "封面", "slide_role": "cover", "content_shape": "title-subtitle", "goal": "建立主题定位"},
        {"slide_number": 2, "title": "为什么现在要做", "slide_role": "context", "content_shape": "problem-bullets", "goal": "说明问题背景"},
        {"slide_number": 3, "title": "Harness 分层", "slide_role": "framework", "content_shape": "two-column-framework", "goal": "解释分层职责"},
        {"slide_number": 4, "title": "Slidev MVP 闭环", "slide_role": "detail", "content_shape": "diagram-callout", "goal": "说明实现闭环"},
        {"slide_number": 5, "title": "下一步", "slide_role": "closing", "content_shape": "next-step", "goal": "总结行动方向"},
    ]


def _copy_slidev_skills(tmp_path, monkeypatch) -> SkillRegistry:
    skills_dir = tmp_path / "skills"
    for skill_name in ("slidev-syntax", "slidev-deck-quality"):
        source_skill_dir = settings.project_root / "skills" / skill_name
        target_dir = skills_dir / skill_name / "scripts"
        target_dir.mkdir(parents=True, exist_ok=True)
        (skills_dir / skill_name / "SKILL.md").write_text(
            (source_skill_dir / "SKILL.md").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        for script_path in (source_skill_dir / "scripts").glob("*.py"):
            (target_dir / script_path.name).write_text(script_path.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(settings, "skills_dir", skills_dir)
    return SkillRegistry(skills_dir)


def test_slidev_mvp_service_generates_artifact_with_visible_harness(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    fake_store = FakeSessionStore()
    monkeypatch.setattr(slidev_mvp_mod, "session_store", fake_store)

    markdown = _slidev_markdown()
    seen_messages: list[list[AgenticMessage]] = []
    model = StubModel(
        responses=[
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="update_todo",
                        args={
                            "items": [
                                {"id": 1, "task": "规划 deck", "status": "in_progress"},
                                {"id": 2, "task": "校验并保存", "status": "pending"},
                            ]
                        },
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(
                parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-syntax"}, tool_call_id="call-2")]
            ),
            AssistantMessage(
                parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-deck-quality"}, tool_call_id="call-3")]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="set_slidev_outline",
                        args={"items": _quality_outline_items_five()},
                        tool_call_id="call-4",
                    )
                ]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="dispatch_subagent",
                        args={"task": "起草第 3-4 页的关键 bullet，保持每页 2-3 个要点。"},
                        tool_call_id="call-5",
                    )
                ]
            ),
            AssistantMessage(parts=["第 3-4 页建议聚焦分层职责与 MVP 路径。"]),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="review_slidev_outline",
                        args={},
                        tool_call_id="call-6",
                    )
                ]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="review_slidev_deck",
                        args={"markdown": markdown},
                        tool_call_id="call-7",
                    )
                ]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="validate_slidev_deck",
                        args={"markdown": markdown},
                        tool_call_id="call-8",
                    )
                ]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="save_slidev_artifact",
                        args={"title": "AI Product Architecture Evolution", "markdown": markdown},
                        tool_call_id="call-9",
                    )
                ]
            ),
        ],
        seen_messages=seen_messages,
    )
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
        model=model,
    )

    artifact = asyncio.run(
        service.generate_deck(
            topic="AI 产品架构演进",
            content="围绕 harness 如何驱动 Slidev 生成离线 deck。",
            num_pages=5,
            build=False,
        )
    )

    assert artifact.slides_path.exists()
    assert artifact.validation["ok"] is True
    assert artifact.quality["outline_review"]["ok"] is True
    assert artifact.quality["deck_review"]["ok"] is True
    assert artifact.agentic["used_subagent"] is True
    assert artifact.agentic["loaded_skills"] == ["slidev-deck-quality", "slidev-syntax"]
    assert "大纲已生成：5 页 - 封面(cover)；为什么现在要做(context)；Harness 分层(framework)" in artifact.agentic["final_state_summary"]
    assert "大纲审查：通过" in artifact.agentic["final_state_summary"]
    assert service.last_loop_result is not None
    assert service.last_loop_result.stop_reason == "slidev-artifact-saved"
    first_assistant = service.last_loop_result.messages[1]
    assert isinstance(first_assistant, AssistantMessage)
    assert isinstance(first_assistant.parts[0], ToolCall)
    assert first_assistant.parts[0].tool_name == "update_todo"
    state_summary_seen = False
    for message in service.last_loop_result.messages:
        if not isinstance(message, UserMessage):
            continue
        for part in message.parts:
            if isinstance(part, ToolResult) and "大纲已生成：5 页" in str(part.metadata.get("state_summary") or ""):
                state_summary_seen = True
                break
    assert state_summary_seen is True
    assert fake_store.ensure_workspace_calls == ["workspace-slidev"]


def test_slidev_mvp_service_combines_sources_and_runs_build(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    fake_store = FakeSessionStore(
        source_metas=[{"id": "src-1", "fileCategory": "pdf"}],
        source_content="Source content from uploaded material.",
    )
    monkeypatch.setattr(slidev_mvp_mod, "session_store", fake_store)

    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    (sandbox_dir / "package.json").write_text('{"name":"slidev-mvp"}', encoding="utf-8")

    commands: list[tuple[list[str], Path]] = []

    async def fake_shell_runner(command, cwd):
        commands.append((list(command), cwd))
        return subprocess.CompletedProcess(list(command), 0, stdout="ok", stderr="")

    markdown = _simple_markdown()
    model = StubModel(
        responses=[
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="update_todo",
                        args={"items": [{"id": 1, "task": "生成 deck", "status": "done"}]},
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(
                parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-syntax"}, tool_call_id="call-2")]
            ),
            AssistantMessage(
                parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-deck-quality"}, tool_call_id="call-3")]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="set_slidev_outline",
                        args={
                            "items": [
                                {"slide_number": 1, "title": "封面", "slide_role": "cover", "content_shape": "title-subtitle", "goal": "开场"},
                                {"slide_number": 2, "title": "收尾", "slide_role": "closing", "content_shape": "next-step", "goal": "收尾"},
                            ]
                        },
                        tool_call_id="call-4",
                    )
                ]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="review_slidev_outline",
                        args={},
                        tool_call_id="call-5",
                    )
                ]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="review_slidev_deck",
                        args={"markdown": markdown},
                        tool_call_id="call-6",
                    )
                ]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="validate_slidev_deck",
                        args={"markdown": markdown},
                        tool_call_id="call-7",
                    )
                ]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="save_slidev_artifact",
                        args={"title": "Mini Deck", "markdown": markdown},
                        tool_call_id="call-8",
                    )
                ]
            ),
        ]
    )
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=sandbox_dir,
        shell_runner=fake_shell_runner,
        model=model,
    )

    artifact = asyncio.run(
        service.generate_deck(
            topic="",
            content="Operator notes.",
            session_id="session-1",
            source_ids=["src-1"],
            num_pages=2,
            build=True,
        )
    )

    assert service.last_state is not None
    assert "Source content from uploaded material." in service.last_state.raw_content
    assert "Operator notes." in service.last_state.raw_content
    assert artifact.build_output_dir == artifact.artifact_dir / "dist"
    assert (artifact.artifact_dir / "node_modules").is_symlink()
    assert commands == [
        (["pnpm", "install"], sandbox_dir),
        (
            [
                "./node_modules/.bin/slidev",
                "build",
                artifact.slides_path.name,
                "--out",
                artifact.build_output_dir.name,
            ],
            artifact.artifact_dir,
        ),
    ]
    assert fake_store.session_calls == [("workspace-slidev", "session-1")]
    assert fake_store.source_lookup_calls == [("workspace-slidev", ["src-1"])]
    assert fake_store.source_content_calls == [("workspace-slidev", "session-1", ["src-1"])]


def test_slidev_mvp_service_rejects_missing_inputs(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
    )

    try:
        asyncio.run(service.generate_deck(topic="", content="", source_ids=[], num_pages=3))
    except SlidevMvpValidationError as exc:
        assert "请提供 topic、content 或 source_ids" in str(exc)
    else:
        raise AssertionError("expected SlidevMvpValidationError")


def test_slidev_syntax_validate_deck_returns_structured_results(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    valid = asyncio.run(
        execute_skill(
            "slidev-syntax",
            "validate_deck.py",
            {"slides": [], "parameters": {"markdown": _simple_markdown(), "expected_pages": 2}},
        )
    )
    invalid = asyncio.run(
        execute_skill(
            "slidev-syntax",
            "validate_deck.py",
            {"slides": [], "parameters": {"markdown": "# only one slide", "expected_pages": 2}},
        )
    )

    assert valid["ok"] is True
    assert valid["slide_count"] == 2
    assert invalid["ok"] is False
    assert {issue["code"] for issue in invalid["issues"]} >= {
        "missing_frontmatter",
        "missing_separator",
        "too_few_slides",
    }


def test_slidev_syntax_validate_deck_warns_when_native_layouts_are_missing(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)
    flat_markdown = """---
theme: default
title: Flat Deck
---

# Flat Deck

---

## Page 2

- one
- two
- three

---

## Page 3

- one
- two
- three

---

## Closing

- wrap
- up
- now
"""

    result = asyncio.run(
        execute_skill(
            "slidev-syntax",
            "validate_deck.py",
            {"slides": [], "parameters": {"markdown": flat_markdown, "expected_pages": 4}},
        )
    )

    assert result["ok"] is True
    warning_codes = {warning["code"] for warning in result["warnings"]}
    assert "low_slidev_native_usage" in warning_codes


def test_slidev_deck_quality_scripts_return_structured_results(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    outline_review = asyncio.run(
        execute_skill(
            "slidev-deck-quality",
            "review_outline.py",
            {"slides": [], "parameters": {"outline_items": _quality_outline_items()[:4], "expected_pages": 4}},
        )
    )
    deck_review = asyncio.run(
        execute_skill(
            "slidev-deck-quality",
            "review_deck.py",
            {"slides": [], "parameters": {"markdown": _simple_markdown(), "outline_items": _quality_outline_items()[:2]}},
        )
    )

    assert outline_review["ok"] is False
    assert {issue["code"] for issue in outline_review["issues"]} >= {"missing_closing"}
    assert deck_review["ok"] is True
    assert isinstance(deck_review["warnings"], list)


def test_slidev_outline_review_enforces_contract_boundaries(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    outline_review = asyncio.run(
        execute_skill(
            "slidev-deck-quality",
            "review_outline.py",
            {
                "slides": [],
                "parameters": {
                    "outline_items": [
                        {
                            "slide_number": 1,
                            "title": "背景",
                            "slide_role": "context",
                            "content_shape": "problem-bullets",
                            "goal": "说明问题",
                        },
                        {
                            "slide_number": 2,
                            "title": "建议",
                            "slide_role": "recommendation",
                            "content_shape": "decision",
                            "goal": "提出动作",
                        },
                        {
                            "slide_number": 3,
                            "title": "结尾",
                            "slide_role": "closing",
                            "content_shape": "next-step",
                            "goal": "收束",
                        },
                    ],
                    "expected_pages": 5,
                },
            },
        )
    )

    assert outline_review["ok"] is False
    assert {issue["code"] for issue in outline_review["issues"]} >= {
        "missing_cover",
        "first_slide_not_cover",
        "outline_page_budget_mismatch",
    }
    assert outline_review["contract_summary"]["expected_pages"] == 5
    assert outline_review["contract_summary"]["actual_pages"] == 3
    assert outline_review["contract_summary"]["first_role"] == "context"
    assert outline_review["contract_summary"]["last_role"] == "closing"


def test_slidev_deck_review_returns_slide_reports_and_blocks_contract_mismatches(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    outline_items = [
        {"slide_number": 1, "title": "封面", "slide_role": "cover", "content_shape": "title-subtitle", "goal": "开场"},
        {"slide_number": 2, "title": "方案对比", "slide_role": "comparison", "content_shape": "compare-grid", "goal": "对比路径"},
        {"slide_number": 3, "title": "下一步", "slide_role": "closing", "content_shape": "next-step", "goal": "收束"},
    ]
    deck_review = asyncio.run(
        execute_skill(
            "slidev-deck-quality",
            "review_deck.py",
            {"slides": [], "parameters": {"markdown": _comparison_mismatch_markdown(), "outline_items": outline_items}},
        )
    )

    assert deck_review["ok"] is False
    assert {issue["code"] for issue in deck_review["issues"]} >= {"comparison_role_mismatch"}
    assert deck_review["contract_summary"]["expected_slide_count"] == 3
    assert deck_review["contract_summary"]["actual_slide_count"] == 3
    assert deck_review["slide_reports"][1]["role"] == "comparison"
    assert deck_review["slide_reports"][1]["status"] == "failed"
    assert {finding["code"] for finding in deck_review["slide_reports"][1]["findings"]} == {"comparison_role_mismatch"}


def test_slidev_mvp_service_requires_quality_review_before_save(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod
    from app.services.generation.agentic.todo import TodoManager
    from app.services.pipeline.graph import PipelineState

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    markdown = _simple_markdown()
    outline_items = [
        {"slide_number": 1, "title": "封面", "slide_role": "cover", "content_shape": "title-subtitle", "goal": "开场"},
        {"slide_number": 2, "title": "收尾", "slide_role": "closing", "content_shape": "next-step", "goal": "收尾"},
    ]
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
    )
    state = PipelineState(topic="demo", raw_content="demo", num_pages=2)
    runtime = slidev_mvp_mod._RuntimeContext(
        deck_id="deck-test",
        artifact_dir=tmp_path / "artifacts" / "deck-test",
        slides_path=tmp_path / "artifacts" / "deck-test" / "slides.md",
        requested_pages=2,
    )
    registry = service._build_registry(state=state, runtime=runtime, todo_manager=TodoManager())
    outline_result = asyncio.run(registry.get("set_slidev_outline").handler({"items": outline_items}))
    assert "Recorded Slidev outline" in outline_result
    runtime.validation = {"ok": True, "slide_count": 2, "issues": [], "warnings": []}
    runtime.validation_hash = slidev_mvp_mod._text_hash(markdown)

    try:
        asyncio.run(registry.get("save_slidev_artifact").handler({"title": "Mini Deck", "markdown": markdown}))
    except SlidevMvpValidationError as exc:
        assert exc.reason_code == "outline_review_missing"
    else:
        raise AssertionError("expected SlidevMvpValidationError")


def test_slidev_mvp_service_allows_save_when_only_warnings_remain(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod
    from app.services.generation.agentic.todo import TodoManager
    from app.services.pipeline.graph import PipelineState

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    markdown = _slidev_markdown()
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
    )
    state = PipelineState(topic="demo", raw_content="demo", num_pages=5)
    runtime = slidev_mvp_mod._RuntimeContext(
        deck_id="deck-test",
        artifact_dir=tmp_path / "artifacts" / "deck-test",
        slides_path=tmp_path / "artifacts" / "deck-test" / "slides.md",
        requested_pages=5,
    )
    registry = service._build_registry(state=state, runtime=runtime, todo_manager=TodoManager())
    asyncio.run(registry.get("set_slidev_outline").handler({"items": _quality_outline_items_five()}))
    runtime.outline_review = {
        "ok": True,
        "issues": [],
        "warnings": [{"code": "outline_role_run_repetition", "message": "warn"}],
        "roles": [item["slide_role"] for item in _quality_outline_items_five()],
        "contract_summary": {"hard_issue_count": 0, "warning_count": 1},
    }
    runtime.outline_review_hash = slidev_mvp_mod._outline_hash(state.outline)
    runtime.deck_review = {
        "ok": True,
        "issues": [],
        "warnings": [{"code": "framework_role_weakened", "message": "warn"}],
        "signatures": [],
        "slide_reports": [],
        "contract_summary": {"hard_issue_count": 0, "warning_count": 1},
    }
    runtime.deck_review_hash = slidev_mvp_mod._text_hash(markdown)
    runtime.validation = {"ok": True, "slide_count": 5, "issues": [], "warnings": [{"code": "weak_cover", "message": "warn"}]}
    runtime.validation_hash = slidev_mvp_mod._text_hash(markdown)

    result = asyncio.run(registry.get("save_slidev_artifact").handler({"title": "Warning Deck", "markdown": markdown}))

    assert result.stop_loop is True
    assert runtime.saved_artifact is not None
    assert runtime.saved_artifact.quality["outline_review"]["ok"] is True
    assert runtime.saved_artifact.quality["deck_review"]["ok"] is True
    assert runtime.saved_artifact.quality["structure_warnings"]


def test_slidev_review_tools_pull_context_from_state(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod
    from app.services.generation.agentic.todo import TodoManager
    from app.services.pipeline.graph import PipelineState

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
    )
    state = PipelineState(topic="demo", raw_content="demo", num_pages=5)
    runtime = slidev_mvp_mod._RuntimeContext(
        deck_id="deck-test",
        artifact_dir=tmp_path / "artifacts" / "deck-test",
        slides_path=tmp_path / "artifacts" / "deck-test" / "slides.md",
        requested_pages=5,
    )
    registry = service._build_registry(state=state, runtime=runtime, todo_manager=TodoManager())
    asyncio.run(registry.get("set_slidev_outline").handler({"items": _quality_outline_items_five()}))
    markdown = _slidev_markdown()

    outline_review = asyncio.run(registry.get("review_slidev_outline").handler({}))
    deck_review = asyncio.run(registry.get("review_slidev_deck").handler({"markdown": markdown}))
    validation = asyncio.run(registry.get("validate_slidev_deck").handler({"markdown": markdown}))

    assert outline_review["ok"] is True
    assert deck_review["ok"] is True
    assert validation["ok"] is True
    assert runtime.outline_review == outline_review
    assert runtime.deck_review == deck_review
    assert runtime.validation == validation


def test_slidev_mvp_service_reports_failed_outline_review_reason_after_max_turns(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    model = StubModel(
        responses=[
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="update_todo",
                        args={"items": [{"id": 1, "task": "规划 deck", "status": "in_progress"}]},
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(
                parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-syntax"}, tool_call_id="call-2")]
            ),
            AssistantMessage(
                parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-deck-quality"}, tool_call_id="call-3")]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="set_slidev_outline",
                        args={
                            "items": [
                                {"slide_number": 1, "title": "封面", "slide_role": "cover", "content_shape": "title-subtitle", "goal": "开场"},
                                {"slide_number": 2, "title": "框架", "slide_role": "framework", "content_shape": "framework-grid", "goal": "解释结构"},
                            ]
                        },
                        tool_call_id="call-4",
                    )
                ]
            ),
            AssistantMessage(parts=["done"]),
        ]
    )
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
        model=model,
    )

    try:
        asyncio.run(service.generate_deck(topic="demo", content="demo", num_pages=2, build=False))
    except SlidevMvpValidationError as exc:
        assert exc.reason_code == "outline_review_missing"
        assert "review_slidev_outline" in str(exc)
    else:
        raise AssertionError("expected SlidevMvpValidationError")


def test_set_slidev_outline_requires_continuous_unique_numbers(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod
    from app.services.generation.agentic.todo import TodoManager
    from app.services.pipeline.graph import PipelineState

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
    )
    state = PipelineState(topic="demo", raw_content="demo", num_pages=2)
    runtime = slidev_mvp_mod._RuntimeContext(
        deck_id="deck-test",
        artifact_dir=tmp_path / "artifacts" / "deck-test",
        slides_path=tmp_path / "artifacts" / "deck-test" / "slides.md",
        requested_pages=2,
    )
    registry = service._build_registry(state=state, runtime=runtime, todo_manager=TodoManager())

    try:
        asyncio.run(
            registry.get("set_slidev_outline").handler(
                {
                    "items": [
                        {
                            "slide_number": 1,
                            "title": "封面",
                            "slide_role": "cover",
                            "content_shape": "title-subtitle",
                            "goal": "开场",
                        },
                        {
                            "slide_number": 3,
                            "title": "收尾",
                            "slide_role": "closing",
                            "content_shape": "next-step",
                            "goal": "收尾",
                        },
                    ]
                }
            )
        )
    except ValueError as exc:
        assert "continuous 1..N sequence" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_slidev_mvp_api_returns_artifact_metadata(monkeypatch):
    from app.api.v2 import generation as generation_api

    class FakeService:
        def __init__(self, *, workspace_id: str):
            self.workspace_id = workspace_id

        async def generate_deck(self, **kwargs):
            assert self.workspace_id == "workspace-api"
            assert kwargs["build"] is False
            return SlidevMvpArtifacts(
                deck_id="deck-api-1",
                title="API Deck",
                markdown=_simple_markdown(),
                artifact_dir=Path("/tmp/api-artifact"),
                slides_path=Path("/tmp/api-artifact/slides.md"),
                build_output_dir=None,
                dev_command="pnpm exec slidev /tmp/api-artifact/slides.md",
                build_command="pnpm exec slidev build /tmp/api-artifact/slides.md --out /tmp/api-artifact/dist",
                validation={"ok": True, "slide_count": 2, "issues": [], "warnings": []},
                quality={"outline_review": {"ok": True}, "deck_review": {"ok": True}, "structure_warnings": []},
                agentic={"turns": 4, "stop_reason": "slidev-artifact-saved"},
            )

    monkeypatch.setattr(generation_api, "SlidevMvpService", FakeService)
    client = TestClient(app)

    response = client.post(
        "/api/v2/generation/slidev-mvp",
        headers={"X-Workspace-Id": "workspace-api"},
        json={
            "topic": "API Deck",
            "content": "offline slidev",
            "num_pages": 2,
            "build": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deck_id"] == "deck-api-1"
    assert payload["validation"]["ok"] is True
    assert payload["quality"]["outline_review"]["ok"] is True
    assert payload["agentic"]["stop_reason"] == "slidev-artifact-saved"


def test_slidev_mvp_api_maps_validation_errors(monkeypatch):
    from app.api.v2 import generation as generation_api

    class FakeService:
        def __init__(self, *, workspace_id: str):
            self.workspace_id = workspace_id

        async def generate_deck(self, **kwargs):
            raise SlidevMvpValidationError(
                "Deck 大纲结构审查未通过，不能保存 artifact。",
                reason_code="outline_review_failed",
                next_action="修正大纲后重新调用 review_slidev_outline()",
            )

    monkeypatch.setattr(generation_api, "SlidevMvpService", FakeService)
    client = TestClient(app)

    response = client.post(
        "/api/v2/generation/slidev-mvp",
        headers={"X-Workspace-Id": "workspace-api"},
        json={},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "Deck 大纲结构审查未通过" in detail
    assert "reason=outline_review_failed" in detail


def test_slidev_mvp_api_maps_model_http_errors(monkeypatch):
    from app.api.v2 import generation as generation_api

    class FakeService:
        def __init__(self, *, workspace_id: str):
            self.workspace_id = workspace_id

        async def generate_deck(self, **kwargs):
            raise ModelHTTPError(429, "minimax/minimax-m2.5", {"message": "rate limited"})

    monkeypatch.setattr(generation_api, "SlidevMvpService", FakeService)
    client = TestClient(app)

    response = client.post(
        "/api/v2/generation/slidev-mvp",
        headers={"X-Workspace-Id": "workspace-api"},
        json={
            "topic": "API Deck",
            "content": "offline slidev",
            "num_pages": 2,
        },
    )

    assert response.status_code == 503
    assert "上游模型请求失败 (429)" in response.json()["detail"]

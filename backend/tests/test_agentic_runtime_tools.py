from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.services.generation.agentic.background import BackgroundManager
from app.services.generation.agentic.skills import SkillCatalog, SkillRecord
from app.services.generation.agentic.tasks import TaskManager
from app.services.generation.agentic.todo import TodoManager
from app.services.generation.agentic.tools import ToolRegistry, bash, default_tool_context, edit_file, load_skill, read_file, todo, tool, write_file
from app.services.generation.agentic.types import ToolCall


class EchoArgs(BaseModel):
    text: str


@tool(description="Echo the provided text.")
def echo(args: EchoArgs) -> dict[str, str]:
    return {"text": args.text}


def test_tool_registry_exports_json_schema() -> None:
    registry = ToolRegistry()
    registry.register(echo)

    tools = registry.to_model_tools()

    assert tools[0]["name"] == "echo"
    assert tools[0]["input_schema"]["properties"]["text"]["type"] == "string"


@pytest.mark.asyncio
async def test_read_file_reads_file(tmp_path: Path) -> None:
    target = tmp_path / "hello.txt"
    target.write_text("hello", encoding="utf-8")

    result = read_file(type("Args", (), {"path": "hello.txt", "limit": None})(), default_tool_context(tmp_path))

    assert result["content"] == "hello"
    assert result["truncated"] is False


def test_read_file_truncates_by_line_limit(tmp_path: Path) -> None:
    target = tmp_path / "hello.txt"
    target.write_text("a\nb\nc\n", encoding="utf-8")

    result = read_file(type("Args", (), {"path": "hello.txt", "limit": 2})(), default_tool_context(tmp_path))

    assert result["content"] == "a\nb"
    assert result["truncated"] is True


def test_write_file_creates_and_overwrites_file(tmp_path: Path) -> None:
    context = default_tool_context(tmp_path)

    created = write_file(type("Args", (), {"path": "nested/hello.txt", "content": "hello"})(), context)
    overwritten = write_file(type("Args", (), {"path": "nested/hello.txt", "content": "world"})(), context)

    assert (tmp_path / "nested" / "hello.txt").read_text(encoding="utf-8") == "world"
    assert created["chars_written"] == 5
    assert overwritten["bytes_written"] == 5


def test_edit_file_replaces_exactly_one_match(tmp_path: Path) -> None:
    target = tmp_path / "hello.txt"
    target.write_text("hello world", encoding="utf-8")

    result = edit_file(
        type("Args", (), {"path": "hello.txt", "old_text": "world", "new_text": "agent"})(),
        default_tool_context(tmp_path),
    )

    assert target.read_text(encoding="utf-8") == "hello agent"
    assert result["replacements"] == 1


def test_edit_file_errors_when_text_missing_or_ambiguous(tmp_path: Path) -> None:
    target = tmp_path / "hello.txt"
    target.write_text("world world", encoding="utf-8")
    context = default_tool_context(tmp_path)

    with pytest.raises(ValueError, match="multiple"):
        edit_file(type("Args", (), {"path": "hello.txt", "old_text": "world", "new_text": "agent"})(), context)

    target.write_text("hello there", encoding="utf-8")
    with pytest.raises(ValueError, match="not found"):
        edit_file(type("Args", (), {"path": "hello.txt", "old_text": "world", "new_text": "agent"})(), context)


def test_file_tools_reject_paths_outside_workspace(tmp_path: Path) -> None:
    context = default_tool_context(tmp_path)

    with pytest.raises(ValueError, match="escapes workspace"):
        read_file(type("Args", (), {"path": "../escape.txt", "limit": None})(), context)
    with pytest.raises(ValueError, match="escapes workspace"):
        write_file(type("Args", (), {"path": "../escape.txt", "content": "hello"})(), context)
    with pytest.raises(ValueError, match="escapes workspace"):
        edit_file(type("Args", (), {"path": "../escape.txt", "old_text": "a", "new_text": "b"})(), context)


def test_todo_tool_updates_session_scoped_todo_manager(tmp_path: Path) -> None:
    context = default_tool_context(tmp_path)
    context.todo_manager = TodoManager()

    result = todo(
        type(
            "Args",
            (),
            {
                "items": [
                    type("Item", (), {"model_dump": lambda self, mode="python": {"id": 1, "text": "Plan", "status": "pending"}})()
                ]
            },
        )(),
        context,
    )

    assert result["counts"]["total"] == 1
    assert context.todo_manager.items[0].text == "Plan"


def test_load_skill_returns_structured_skill_content(tmp_path: Path) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    record = SkillRecord(
        name="example-skill",
        description="Example skill",
        location=skill_dir / "SKILL.md",
        skill_dir=skill_dir,
        body="Follow these steps.",
    )
    context = default_tool_context(tmp_path)
    context.skill_catalog = SkillCatalog(records={"example-skill": record})

    result = load_skill(type("Args", (), {"name": "example-skill"})(), context)

    assert result["name"] == "example-skill"
    assert "<skill_content name=\"example-skill\">" in result["content"]


def test_load_skill_errors_for_unknown_skill(tmp_path: Path) -> None:
    context = default_tool_context(tmp_path)
    context.skill_catalog = SkillCatalog()

    with pytest.raises(ValueError, match="Unknown skill"):
        load_skill(type("Args", (), {"name": "missing"})(), context)


def test_task_tools_create_update_use_and_list(tmp_path: Path) -> None:
    from app.services.generation.agentic.tools import task_create, task_list, task_update, task_use

    context = default_tool_context(tmp_path)
    context.task_manager = TaskManager.from_project(tmp_path, create_if_missing=True)

    created = task_create(
        type("Args", (), {"title": "Build task support", "task_id": None, "dependencies": [], "summary": "Initial"})(),
        context,
    )
    created_id = created["task"]["id"]
    updated = task_update(
        type(
            "Args",
            (),
            {
                "task_id": created_id,
                "title": None,
                "status": "in_progress",
                "dependencies": None,
                "summary": "Updated summary",
                "note": "Started work",
                "replace_notes": False,
            },
        )(),
        context,
    )
    listed = task_list(type("Args", (), {"include_notes": True})(), context)
    selected = task_use(type("Args", (), {"task_id": created_id})(), context)

    assert created["current_task_id"] == created_id
    assert updated["task"]["status"] == "in_progress"
    assert listed["tasks"][0]["summary"] == "Updated summary"
    assert listed["tasks"][0]["notes"] == ["Started work"]
    assert selected["current_task_id"] == created_id


@pytest.mark.asyncio
async def test_subagent_and_background_tools_use_context_managers(tmp_path: Path) -> None:
    from app.services.generation.agentic.tools import background_check, background_subagent, subagent_run

    class FakeSubagentManager:
        async def run(self, *, task: str, context: str | None = None, allowed_tools=None, max_turns=None):
            return {
                "task": task,
                "output_text": f"done: {task}",
                "stop_reason": "completed",
                "turns": 1,
                "error": None,
                "tool_results": [],
            }

    context = default_tool_context(tmp_path)
    context.task_manager = TaskManager.from_project(tmp_path, create_if_missing=True)
    context.subagent_manager = FakeSubagentManager()  # type: ignore[assignment]
    context.background_manager = BackgroundManager(
        bash_policy=context.bash_policy,
        subagent_manager=context.subagent_manager,  # type: ignore[arg-type]
    )

    delegated = await subagent_run(
        type("Args", (), {"task": "write slide", "context": "slide 1", "allowed_tools": None, "max_turns": None})(),
        context,
    )
    started = background_subagent(
        type("Args", (), {"task": "write slide 2", "context": None, "allowed_tools": None, "max_turns": None})(),
        context,
    )

    for _ in range(100):
        status = background_check(type("Args", (), {"task_id": started["task_id"]})(), context)["tasks"][0]["status"]
        if status != "running":
            break
        await asyncio.sleep(0.01)
    checked = background_check(type("Args", (), {"task_id": started["task_id"]})(), context)

    assert delegated["output_text"] == "done: write slide"
    assert started["status"] == "running"
    assert checked["tasks"][0]["status"] == "completed"


@pytest.mark.asyncio
async def test_bash_tool_restricts_unapproved_commands(tmp_path: Path) -> None:
    context = default_tool_context(tmp_path)

    with pytest.raises(ValueError):
        await bash(
            type(
                "Args",
                (),
                {"command": "rm -rf /tmp/demo", "working_directory": None, "timeout_seconds": 1.0},
            )(),
            context,
        )


@pytest.mark.asyncio
async def test_registry_wraps_unknown_tool_and_validation_errors(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register(echo)

    results = await registry.dispatch(
        [
            ToolCall(tool_name="missing", args={}, tool_call_id="call-1"),
            ToolCall(tool_name="echo", args={}, tool_call_id="call-2"),
        ],
        default_tool_context(tmp_path),
    )

    assert results[0].is_error is True
    assert "Unknown tool" in results[0].content["error"]
    assert results[1].is_error is True
    assert "Invalid arguments" in results[1].content["error"]

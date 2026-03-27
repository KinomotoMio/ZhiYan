from __future__ import annotations

import asyncio
import json
import sys
import types
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.generation.agentic import cli
from app.services.generation.agentic.builder import AgentBuilder
from app.services.generation.agentic.models import ModelClient, ModelResponse, ModelUsage
from app.services.generation.agentic.types import AssistantMessage, ToolCall
from tests.conftest import FakeModel


def _builder_with_fake_model(project_root: Path, model) -> AgentBuilder:
    builder = AgentBuilder.from_project(project_root)
    builder.with_model_client(model)
    builder.discover_skills()
    builder.load_mcp_config()
    return builder


@dataclass
class LoopTrackingModel(ModelClient):
    responses: list[AssistantMessage]
    seen_loop_ids: list[int] = field(default_factory=list)

    async def complete(self, messages: list[Any], tools: list[dict[str, Any]]) -> ModelResponse:
        self.seen_loop_ids.append(id(asyncio.get_running_loop()))
        return ModelResponse(message=self.responses.pop(0))


class FakeLiteLLMLoggingWorker:
    def __init__(self) -> None:
        self.bound_loop: asyncio.AbstractEventLoop | None = None
        self.pending: list[Any] = []
        self.awaited_calls: list[int] = []
        self.seen_loop_ids: list[int] = []
        self.flush_calls = 0
        self.stop_calls = 0

    def ensure_initialized_and_enqueue(self, coroutine) -> None:
        loop = asyncio.get_running_loop()
        self.seen_loop_ids.append(id(loop))
        if self.bound_loop is not None and self.bound_loop is not loop:
            self.pending.clear()
        self.bound_loop = loop
        self.pending.append(coroutine)

    async def flush(self) -> None:
        self.flush_calls += 1
        while self.pending:
            coroutine = self.pending.pop(0)
            await coroutine

    async def stop(self) -> None:
        self.stop_calls += 1


@dataclass
class LiteLLMStyleModel(ModelClient):
    responses: list[AssistantMessage]
    worker: FakeLiteLLMLoggingWorker
    completed_calls: list[int] = field(default_factory=list)
    issued_calls: int = 0

    async def complete(self, messages: list[Any], tools: list[dict[str, Any]]) -> ModelResponse:
        call_index = self.issued_calls
        self.issued_calls += 1

        async def async_success_handler() -> None:
            await asyncio.sleep(0)
            self.completed_calls.append(call_index)

        self.worker.ensure_initialized_and_enqueue(async_success_handler())
        return ModelResponse(message=self.responses.pop(0))


def test_cli_inspect_outputs_tools_skills_and_mcp(tmp_path: Path, capsys, skill_file_contents: str) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")
    (tmp_path / ".agents" / "mcp.json").write_text('{"mcpServers":{}}', encoding="utf-8")

    exit_code = cli.main(["--project-root", str(tmp_path), "inspect"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert any(tool["name"] == "read_file" for tool in output["tools"])
    assert output["skills"][0]["name"] == "example-skill"
    assert output["skills"][0]["argument_hint"] == "Optional task selector or target identifier."
    assert output["mcp"]["path"].endswith(".agents/mcp.json")
    assert output["tasks"] == []
    assert output["current_task_id"] is None


def test_cli_run_executes_one_shot_flow(tmp_path: Path, monkeypatch, capsys) -> None:
    builder = _builder_with_fake_model(tmp_path, FakeModel(responses=[AssistantMessage(content="done")]))
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "run", "--prompt", "hello"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["output_text"] == "done"


def test_cli_chat_repl_happy_path(tmp_path: Path, monkeypatch, capsys) -> None:
    builder = _builder_with_fake_model(tmp_path, FakeModel(responses=[AssistantMessage(content="pong")]))
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["ping", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert any("pong" == line for line in lines)


def test_cli_chat_json_mode_preserves_json_output(tmp_path: Path, monkeypatch, capsys) -> None:
    builder = _builder_with_fake_model(tmp_path, FakeModel(responses=[AssistantMessage(content="pong")]))
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["ping", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat", "--json"])

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert any('"output_text": "pong"' in line for line in lines)


def test_cli_chat_shows_tool_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    target = tmp_path / "note.txt"
    target.write_text("hello", encoding="utf-8")
    builder = _builder_with_fake_model(
        tmp_path,
        FakeModel(
            responses=[
                AssistantMessage(
                    tool_calls=[ToolCall(tool_name="read_file", args={"path": "note.txt"}, tool_call_id="call-1")]
                ),
                AssistantMessage(content="done"),
            ]
        ),
    )
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["read the file", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "[tool:read_file] ok" in output
    assert "path=" in output
    assert "done" in output


def test_cli_chat_shows_write_file_and_edit_file_summaries(tmp_path: Path, monkeypatch, capsys) -> None:
    builder = _builder_with_fake_model(
        tmp_path,
        FakeModel(
            responses=[
                AssistantMessage(
                    tool_calls=[
                        ToolCall(
                            tool_name="write_file",
                            args={"path": "note.txt", "content": "hello"},
                            tool_call_id="call-1",
                        )
                    ]
                ),
                AssistantMessage(
                    tool_calls=[
                        ToolCall(
                            tool_name="edit_file",
                            args={"path": "note.txt", "old_text": "hello", "new_text": "world"},
                            tool_call_id="call-2",
                        )
                    ]
                ),
                AssistantMessage(content="done"),
            ]
        ),
    )
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["write file", "edit file", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "[tool:write_file] ok" in output
    assert "[tool:edit_file] ok" in output


def test_cli_chat_help_and_skills_commands(tmp_path: Path, monkeypatch, capsys, skill_file_contents: str) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")
    builder = _builder_with_fake_model(tmp_path, FakeModel(responses=[]))
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["/help", "/skills", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Commands:" in output
    assert "/plan <prompt>" in output
    assert "/tasks" in output
    assert "/task use <id>" in output
    assert "Args override the current target" in output
    assert "Available skills:" in output
    assert "example-skill" in output
    assert "args: Optional task selector or target identifier." in output


def test_cli_chat_tasks_and_task_use_commands(tmp_path: Path, monkeypatch, capsys) -> None:
    from app.services.generation.agentic.tasks import TaskManager

    manager = TaskManager.from_project(tmp_path, create_if_missing=True)
    first = manager.create_task(title="First task")
    second = manager.create_task(title="Second task")

    builder = _builder_with_fake_model(tmp_path, FakeModel(responses=[]))
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["/tasks", f"/task use {second.id}", "/tasks", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert f"* {first.id}:" in output
    assert f"[task] current={second.id}" in output
    assert f"* {second.id}:" in output


def test_cli_chat_skill_invocation_is_human_readable(tmp_path: Path, monkeypatch, capsys) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "mock-echo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: mock-echo
description: Output a fixed string when invoked.
---

# Mock Echo

Reply with exactly: I am Skill mock-echo.
""",
        encoding="utf-8",
    )
    builder = _builder_with_fake_model(
        tmp_path,
        FakeModel(
            responses=[
                AssistantMessage(content="I am Skill mock-echo."),
            ]
        ),
    )
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["/mock-echo", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "I am Skill mock-echo." in output
    assert "[tool:load_skill] ok" not in output


def test_cli_chat_skill_invocation_with_args_passes_current_task(tmp_path: Path, monkeypatch, capsys) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: example-skill
description: Use the provided task.
---

# Example Skill

Use the current task.
""",
        encoding="utf-8",
    )
    model = FakeModel(responses=[AssistantMessage(content="handled")])
    builder = _builder_with_fake_model(tmp_path, model)
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["/example-skill review PR 4", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "handled" in output
    latest_user_messages = [message.content for message in model.seen_messages[0] if getattr(message, "role", "") == "user"]
    assert "<skill_invocation>" in latest_user_messages[-1]
    assert "<explicit_args>review PR 4</explicit_args>" in latest_user_messages[-1]
    assert "explicit_args_override_context_but_context_remains_available" in latest_user_messages[-1]


def test_cli_chat_follow_up_turn_does_not_receive_persisted_skill_invocation_template(
    tmp_path: Path, monkeypatch, capsys, skill_file_contents: str
) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")
    model = FakeModel(
        responses=[
            AssistantMessage(content="handled"),
            AssistantMessage(content="follow-up"),
        ]
    )
    builder = _builder_with_fake_model(tmp_path, model)
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["/example-skill review PR 4", "what did you just do?", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    assert all(
        "<skill_invocation>" not in getattr(message, "content", "")
        and "explicit_args_override_context_but_context_remains_available" not in getattr(message, "content", "")
        for message in model.seen_messages[1]
    )


def test_cli_chat_reuses_loaded_skill_without_duplicate_load_tool_result_in_debug_mode(
    tmp_path: Path, monkeypatch, capsys, skill_file_contents: str
) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")
    builder = _builder_with_fake_model(
        tmp_path,
        FakeModel(
            responses=[
                AssistantMessage(content="first use"),
                AssistantMessage(content="second use"),
            ]
        ),
    )
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["/example-skill", "/example-skill review PR 4", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat", "--debug"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert output.count("[tool:load_skill] ok - name=example-skill") == 1
    assert output.count("[debug] context_marker=") == 2


def test_cli_chat_accumulates_context_across_turns(tmp_path: Path, monkeypatch, capsys) -> None:
    model = FakeModel(
        responses=[
            AssistantMessage(content="first"),
            AssistantMessage(content="second"),
        ]
    )
    builder = _builder_with_fake_model(tmp_path, model)
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["hello", "again", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    assert len(model.seen_messages[1]) > len(model.seen_messages[0])
    assert any(getattr(message, "content", "") == "hello" for message in model.seen_messages[1])


def test_cli_chat_reuses_same_event_loop_across_turns(tmp_path: Path, monkeypatch) -> None:
    model = LoopTrackingModel(
        responses=[
            AssistantMessage(content="first"),
            AssistantMessage(content="second"),
        ]
    )
    builder = _builder_with_fake_model(tmp_path, model)
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    monkeypatch.setattr(cli, "_drain_litellm_logging_worker", lambda: _async_noop())
    inputs = iter(["hello", "again", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    assert len(model.seen_loop_ids) == 2
    assert model.seen_loop_ids[0] == model.seen_loop_ids[1]


def test_cli_chat_reset_clears_context_and_active_skills(tmp_path: Path, monkeypatch, capsys, skill_file_contents: str) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")
    model = FakeModel(
        responses=[
            AssistantMessage(content="after skill"),
            AssistantMessage(content="after reset"),
        ]
    )
    builder = _builder_with_fake_model(tmp_path, model)
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["/example-skill", "/reset", "again", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "[session] reset" in output
    assert any(
        getattr(message, "role", "") == "tool"
        and any("skill_content" in str(result.content) for result in message.results)
        for message in model.seen_messages[0]
        if hasattr(message, "results")
    )
    assert all(
        not (
            getattr(message, "role", "") == "tool"
            and any("skill_content" in str(result.content) for result in message.results)
        )
        for message in model.seen_messages[1]
        if hasattr(message, "results")
    )


def test_cli_chat_json_reset_and_unknown_skill_are_reported(tmp_path: Path, monkeypatch, capsys) -> None:
    builder = _builder_with_fake_model(tmp_path, FakeModel(responses=[]))
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["/missing", "/reset", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat", "--json"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"stop_reason": "invalid-skill"' in output
    assert '"reset": true' in output


def test_cli_chat_plan_command_updates_todos_and_prints_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="todo",
                        args={"items": [{"id": 1, "text": "Plan work", "status": "pending"}]},
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(content="Plan ready."),
        ]
    )
    builder = _builder_with_fake_model(tmp_path, model)
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["/plan refactor project", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "[tool:todo] ok" in output
    assert "Current plan:" in output
    assert "Plan ready." in output


def test_cli_chat_shows_subagent_and_background_tool_summaries(tmp_path: Path, monkeypatch, capsys) -> None:
    model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="subagent_run",
                        args={"task": "write slide 1", "context": "cover page"},
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(content="subagent result"),
            AssistantMessage(content="parent done"),
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="background_run",
                        args={"command": "python3 -c \"print('bg done')\""},
                        tool_call_id="call-2",
                    )
                ]
            ),
            AssistantMessage(content="background started"),
        ]
    )
    builder = _builder_with_fake_model(tmp_path, model)
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["delegate this", "start background work", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "[delegate] subagent task=" in output
    assert "tools=none" in output
    assert "[tool:subagent_run] ok" in output
    assert "[tool:background_run] ok" in output


def test_cli_chat_delegated_writing_task_stays_tootless_by_default(tmp_path: Path, monkeypatch, capsys) -> None:
    model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="subagent_run",
                        args={"task": "write a title and subtitle", "context": "cover slide"},
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(content="Title: Future Vision\nSubtitle: A concise subtitle"),
            AssistantMessage(content="Title: Future Vision\nSubtitle: A concise subtitle"),
        ]
    )
    builder = _builder_with_fake_model(tmp_path, model)
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["delegate writing", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "[delegate] subagent task=" in output
    assert "[tool:bash]" not in output
    assert "[tool:read_file]" not in output


def test_cli_chat_compact_command_reports_success(tmp_path: Path, monkeypatch, capsys) -> None:
    model = FakeModel(
        responses=[
            AssistantMessage(content="hello"),
            AssistantMessage(content="summary block"),
        ]
    )
    builder = _builder_with_fake_model(tmp_path, model)
    builder.with_auto_compact(False)
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["hello", "/compact", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "[compact] generation=1" in output


def test_cli_chat_compact_command_json_mode(tmp_path: Path, monkeypatch, capsys) -> None:
    model = FakeModel(
        responses=[
            AssistantMessage(content="hello"),
            AssistantMessage(content="summary block"),
        ]
    )
    builder = _builder_with_fake_model(tmp_path, model)
    builder.with_auto_compact(False)
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["hello", "/compact", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat", "--json"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"generation": 1' in output
    assert '"trigger": "manual"' in output


def test_cli_reset_clears_todo_state(tmp_path: Path, monkeypatch, capsys) -> None:
    model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="todo",
                        args={"items": [{"id": 1, "text": "Plan work", "status": "pending"}]},
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(content="Plan ready."),
            AssistantMessage(content="after reset"),
        ]
    )
    builder = _builder_with_fake_model(tmp_path, model)
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["/plan refactor project", "/reset", "hello", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "[session] reset" in output
    assert "Current plan:" in output


def test_cli_chat_debug_mode_prints_extra_details(tmp_path: Path, monkeypatch, capsys) -> None:
    target = tmp_path / "note.txt"
    target.write_text("hello", encoding="utf-8")
    builder = _builder_with_fake_model(
        tmp_path,
        FakeModel(
            responses=[
                AssistantMessage(
                    tool_calls=[ToolCall(tool_name="read_file", args={"path": "note.txt"}, tool_call_id="call-1")]
                ),
                AssistantMessage(content="done"),
            ]
        ),
    )
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["read the file", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat", "--debug"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "[debug] turns=" in output
    assert "[debug] tool_result=" in output


def test_cli_chat_debug_mode_prints_auto_compact_event(tmp_path: Path, monkeypatch, capsys) -> None:
    model = FakeModel(
        responses=[
            AssistantMessage(content="first"),
            AssistantMessage(content="summary block"),
            AssistantMessage(content="second"),
        ],
        usages=[
            ModelUsage(prompt_tokens=6500, completion_tokens=10, total_tokens=6510),
            ModelUsage(),
            ModelUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        ],
    )
    builder = _builder_with_fake_model(tmp_path, model)
    builder.with_compact_token_threshold(6000)
    builder.with_compact_tail_turns(0)
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["hello", "again", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat", "--debug"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "[debug] compact_event=" in output


def test_cli_chat_drains_litellm_style_worker_without_runtime_warning(tmp_path: Path, monkeypatch) -> None:
    worker = FakeLiteLLMLoggingWorker()
    model = LiteLLMStyleModel(
        responses=[
            AssistantMessage(content="first"),
            AssistantMessage(content="second"),
        ],
        worker=worker,
    )
    builder = _builder_with_fake_model(tmp_path, model)
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    monkeypatch.setattr(cli, "_drain_litellm_logging_worker", _make_worker_cleanup(worker))
    inputs = iter(["hello", "again", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    assert model.completed_calls == [0, 1]
    assert worker.seen_loop_ids[0] == worker.seen_loop_ids[1]
    assert worker.flush_calls == 1
    assert worker.stop_calls == 1
    assert not [
        warning for warning in captured if issubclass(warning.category, RuntimeWarning) and "never awaited" in str(warning.message)
    ]


def test_drain_litellm_logging_worker_waits_for_inflight_tasks(monkeypatch) -> None:
    completed: list[str] = []

    async def _exercise() -> None:
        queue: asyncio.Queue[str] = asyncio.Queue()
        await queue.put("pending")
        await queue.get()

        async def inflight() -> None:
            await asyncio.sleep(0)
            completed.append("done")
            queue.task_done()

        running_task = asyncio.create_task(inflight())
        worker_task = asyncio.create_task(asyncio.sleep(3600))

        class FakeWorker:
            def __init__(self) -> None:
                self._queue = queue
                self._running_tasks = {running_task}
                self._worker_task = worker_task
                self.stop_calls = 0

            async def flush(self) -> None:
                return None

            async def clear_queue(self) -> None:
                return None

            async def stop(self) -> None:
                self.stop_calls += 1
                self._worker_task.cancel()
                await asyncio.gather(self._worker_task, return_exceptions=True)

        worker = FakeWorker()
        module = types.ModuleType("litellm.litellm_core_utils.logging_worker")
        module.GLOBAL_LOGGING_WORKER = worker
        monkeypatch.setitem(sys.modules, "litellm", types.ModuleType("litellm"))
        monkeypatch.setitem(sys.modules, "litellm.litellm_core_utils", types.ModuleType("litellm.litellm_core_utils"))
        monkeypatch.setitem(sys.modules, "litellm.litellm_core_utils.logging_worker", module)

        await cli._drain_litellm_logging_worker()

        assert completed == ["done"]
        assert worker.stop_calls == 1

    asyncio.run(_exercise())


def test_cli_chat_tool_error_is_human_readable(tmp_path: Path, monkeypatch, capsys) -> None:
    builder = _builder_with_fake_model(
        tmp_path,
        FakeModel(
            responses=[
                AssistantMessage(
                    tool_calls=[ToolCall(tool_name="read_file", args={"path": "missing.txt"}, tool_call_id="call-1")]
                ),
                AssistantMessage(content="done"),
            ]
        ),
    )
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    inputs = iter(["read the missing file", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "[tool:read_file] error" in output


def test_cli_chat_shutdown_cleanup_runs_once_on_quit(tmp_path: Path, monkeypatch) -> None:
    builder = _builder_with_fake_model(tmp_path, FakeModel(responses=[]))
    cleanup_calls: list[str] = []
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    monkeypatch.setattr(cli, "_drain_litellm_logging_worker", _record_cleanup(cleanup_calls))
    monkeypatch.setattr("builtins.input", lambda _: "quit")

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    assert cleanup_calls == ["cleanup"]


def test_cli_chat_shutdown_cleanup_runs_once_on_eof(tmp_path: Path, monkeypatch) -> None:
    builder = _builder_with_fake_model(tmp_path, FakeModel(responses=[]))
    cleanup_calls: list[str] = []
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    monkeypatch.setattr(cli, "_drain_litellm_logging_worker", _record_cleanup(cleanup_calls))

    def raise_eof(_: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    assert cleanup_calls == ["cleanup"]


def test_cli_chat_shutdown_cleanup_runs_once_on_keyboard_interrupt(tmp_path: Path, monkeypatch, capsys) -> None:
    builder = _builder_with_fake_model(tmp_path, FakeModel(responses=[]))
    cleanup_calls: list[str] = []
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)
    monkeypatch.setattr(cli, "_drain_litellm_logging_worker", _record_cleanup(cleanup_calls))

    def raise_keyboard_interrupt(_: str) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", raise_keyboard_interrupt)

    exit_code = cli.main(["--project-root", str(tmp_path), "--model", "fake/model", "chat"])

    assert exit_code == 0
    assert cleanup_calls == ["cleanup"]
    assert capsys.readouterr().out.endswith("\n\n")


def test_cli_run_supports_explicit_skill_activation(tmp_path: Path, monkeypatch, capsys, skill_file_contents: str) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")
    builder = _builder_with_fake_model(
        tmp_path,
        FakeModel(
            responses=[
                AssistantMessage(
                    tool_calls=[ToolCall(tool_name="load_skill", args={"name": "example-skill"}, tool_call_id="call-1")]
                ),
                AssistantMessage(content="loaded"),
                AssistantMessage(content="done"),
            ]
        ),
    )
    monkeypatch.setattr(cli, "_builder_from_args", lambda args: builder)

    exit_code = cli.main(
        [
            "--project-root",
            str(tmp_path),
            "--model",
            "fake/model",
            "run",
            "--prompt",
            "hello",
            "--skill",
            "example-skill",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["stop_reason"] == "completed"
    assert any(tool_result["tool_name"] == "load_skill" for tool_result in output["tool_results"])


def test_skill_catalog_is_exposed_for_model_driven_load_skill(tmp_path: Path, skill_file_contents: str) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")

    model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="load_skill",
                        args={"name": "example-skill"},
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(content="used catalog"),
        ]
    )
    builder = _builder_with_fake_model(tmp_path, model)
    agent = builder.build()

    result = asyncio.run(agent.run("Need example workflow"))

    assert result.stop_reason == "completed"
    assert result.tool_results[0].tool_name == "load_skill"
    assert "example-skill" in model.seen_messages[0][0].content
    assert "load_skill tool" in model.seen_messages[0][0].content
    assert "read tool" not in model.seen_messages[0][0].content


async def _async_noop() -> None:
    return None


def _make_worker_cleanup(worker: FakeLiteLLMLoggingWorker):
    async def _cleanup() -> None:
        await worker.flush()
        await worker.stop()

    return _cleanup


def _record_cleanup(calls: list[str]):
    async def _cleanup() -> None:
        calls.append("cleanup")

    return _cleanup

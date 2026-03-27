from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.services.generation.agentic.agent import Agent
from app.services.generation.agentic.models import ModelUsage
from app.services.generation.agentic.skills import SkillCatalog
from app.services.generation.agentic.tasks import TaskManager
from app.services.generation.agentic.tools import ToolRegistry, default_tool_context
from app.services.generation.agentic.types import AssistantMessage, ToolCall
from tests.conftest import FakeModel


@pytest.mark.asyncio
async def test_agent_returns_text_without_tools(tmp_path: Path) -> None:
    model = FakeModel(responses=[AssistantMessage(content="world")])
    agent = Agent(
        model=model,
        tool_registry=ToolRegistry(),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=SkillCatalog(),
        system_prompt="Be helpful.",
    )

    result = await agent.run("hello")

    assert result.output_text == "world"
    assert result.turns == 1
    assert result.stop_reason == "completed"


@pytest.mark.asyncio
async def test_agent_dispatches_tool_calls(tmp_path: Path) -> None:
    readme = tmp_path / "note.txt"
    readme.write_text("done", encoding="utf-8")
    from app.services.generation.agentic.tools import create_builtin_registry

    model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[ToolCall(tool_name="read_file", args={"path": "note.txt"}, tool_call_id="call-1")]
            ),
            AssistantMessage(content="finished"),
        ]
    )
    registry = create_builtin_registry(tmp_path)
    agent = Agent(
        model=model,
        tool_registry=registry,
        tool_context=default_tool_context(tmp_path),
        skill_catalog=SkillCatalog(),
        system_prompt="Be helpful.",
    )

    result = await agent.run("read the file")

    assert result.stop_reason == "completed"
    assert result.output_text == "finished"
    assert result.tool_results[0].tool_name == "read_file"
    assert result.tool_results[0].content["content"] == "done"


@pytest.mark.asyncio
async def test_agent_stops_after_max_turns(tmp_path: Path) -> None:
    model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[ToolCall(tool_name="missing", args={}, tool_call_id="call-1")]
            )
        ]
    )
    agent = Agent(
        model=model,
        tool_registry=ToolRegistry(),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=SkillCatalog(),
        system_prompt="Be helpful.",
        max_turns=1,
    )

    result = await agent.run("keep going")

    assert result.stop_reason == "max-turns"
    assert result.turns == 1


@pytest.mark.asyncio
async def test_agent_explicit_skill_activation(tmp_path: Path, skill_file_contents: str) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(skill_file_contents, encoding="utf-8")
    from app.services.generation.agentic.skills import SkillDiscovery
    from app.services.generation.agentic.tools import create_builtin_registry

    catalog = SkillDiscovery(tmp_path).discover()
    model = FakeModel(
        responses=[
            AssistantMessage(content="used skill"),
        ]
    )
    agent = Agent(
        model=model,
        tool_registry=create_builtin_registry(tmp_path),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=catalog,
        system_prompt="Be helpful.",
    )

    result = await agent.run("do the workflow", activate_skills=["example-skill"])

    assert result.stop_reason == "completed"
    assert any(tool_result.tool_name == "load_skill" for tool_result in result.tool_results)


@pytest.mark.asyncio
async def test_agent_session_preserves_history_across_turns(tmp_path: Path) -> None:
    model = FakeModel(
        responses=[
            AssistantMessage(content="first"),
            AssistantMessage(content="second"),
        ]
    )
    agent = Agent(
        model=model,
        tool_registry=ToolRegistry(),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=SkillCatalog(),
        system_prompt="Be helpful.",
    )

    session = agent.start_session()
    first = await session.send("hello")
    second = await session.send("again")

    assert first.output_text == "first"
    assert second.output_text == "second"
    assert len(model.seen_messages[1]) > len(model.seen_messages[0])
    assert any(getattr(message, "content", "") == "hello" for message in model.seen_messages[1])


@pytest.mark.asyncio
async def test_agent_session_snapshot_roundtrip_restores_history(tmp_path: Path) -> None:
    model = FakeModel(
        responses=[
            AssistantMessage(content="first"),
            AssistantMessage(content="second"),
        ]
    )
    agent = Agent(
        model=model,
        tool_registry=ToolRegistry(),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=SkillCatalog(),
        system_prompt="Be helpful.",
    )

    session = agent.start_session()
    await session.send("hello")
    snapshot = session.to_snapshot()

    restored = agent.start_session(snapshot=snapshot)
    result = await restored.send("again")

    assert result.output_text == "second"
    assert any(getattr(message, "content", "") == "hello" for message in restored.messages)
    assert any(getattr(message, "content", "") == "again" for message in restored.messages)


@pytest.mark.asyncio
async def test_agent_session_skill_persists_until_reset(tmp_path: Path, skill_file_contents: str) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")
    from app.services.generation.agentic.skills import SkillDiscovery

    catalog = SkillDiscovery(tmp_path).discover()
    model = FakeModel(
        responses=[
            AssistantMessage(content="first"),
            AssistantMessage(content="second"),
        ]
    )
    from app.services.generation.agentic.tools import create_builtin_registry
    agent = Agent(
        model=model,
        tool_registry=create_builtin_registry(tmp_path),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=catalog,
        system_prompt="Be helpful.",
    )

    session = agent.start_session()
    await session.load_skill("example-skill")
    await session.send("hello")
    assert "example-skill" in session.active_skills
    assert any(
        getattr(message, "role", "") == "tool"
        and any("skill_content" in str(result.content) for result in message.results)
        for message in session.messages
        if hasattr(message, "results")
    )

    session.reset()
    await session.send("again")
    assert session.active_skills == []
    assert all(
        not (
            getattr(message, "role", "") == "tool"
            and any("skill_content" in str(result.content) for result in message.results)
        )
        for message in session.messages
        if hasattr(message, "results")
    )


@pytest.mark.asyncio
async def test_agent_session_invalid_skill_activation_fails_cleanly(tmp_path: Path) -> None:
    model = FakeModel(responses=[AssistantMessage(content="unused")])
    agent = Agent(
        model=model,
        tool_registry=ToolRegistry(),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=SkillCatalog(),
        system_prompt="Be helpful.",
    )

    session = agent.start_session()

    result = await session.load_skill("missing")

    assert result.stop_reason == "invalid-skill"
    assert result.error == "Unknown skill: missing"


@pytest.mark.asyncio
async def test_agent_session_invoke_skill_loads_then_executes(tmp_path: Path, skill_file_contents: str) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")
    from app.services.generation.agentic.skills import SkillDiscovery
    from app.services.generation.agentic.tools import create_builtin_registry

    catalog = SkillDiscovery(tmp_path).discover()
    model = FakeModel(responses=[AssistantMessage(content="used skill")])
    agent = Agent(
        model=model,
        tool_registry=create_builtin_registry(tmp_path),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=catalog,
        system_prompt="Be helpful.",
    )

    session = agent.start_session()
    result = await session.invoke_skill("example-skill")

    assert result.stop_reason == "completed"
    assert result.output_text == "used skill"
    assert result.tool_results[0].tool_name == "load_skill"
    assert any(
        getattr(message, "role", "") == "tool"
        and any("skill_content" in str(tool_result.content) for tool_result in message.results)
        for message in model.seen_messages[0]
        if hasattr(message, "results")
    )
    latest_user_messages = [message.content for message in model.seen_messages[0] if getattr(message, "role", "") == "user"]
    assert "<skill_invocation>" in latest_user_messages[-1]
    assert "<skill_name>example-skill</skill_name>" in latest_user_messages[-1]
    assert "<explicit_args></explicit_args>" in latest_user_messages[-1]
    assert all("<skill_invocation>" not in getattr(message, "content", "") for message in session.messages)
    assert result.context_markers == [
        {
            "kind": "skill_invocation",
            "summary": "skill=example-skill args_present=false",
            "retention": "persistent_marker",
            "metadata": {"skill_name": "example-skill", "args_present": False},
        }
    ]


@pytest.mark.asyncio
async def test_agent_session_invoke_skill_with_prompt_uses_prompt_as_current_task(
    tmp_path: Path, skill_file_contents: str
) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")
    from app.services.generation.agentic.skills import SkillDiscovery
    from app.services.generation.agentic.tools import create_builtin_registry

    catalog = SkillDiscovery(tmp_path).discover()
    model = FakeModel(responses=[AssistantMessage(content="used skill")])
    agent = Agent(
        model=model,
        tool_registry=create_builtin_registry(tmp_path),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=catalog,
        system_prompt="Be helpful.",
    )

    session = agent.start_session()
    await session.invoke_skill("example-skill", prompt="handle task 42")

    latest_user_messages = [message.content for message in model.seen_messages[0] if getattr(message, "role", "") == "user"]
    assert "<explicit_args>handle task 42</explicit_args>" in latest_user_messages[-1]
    assert "<argument_hint>Optional task selector or target identifier.</argument_hint>" in latest_user_messages[-1]
    assert all("<skill_invocation>" not in getattr(message, "content", "") for message in session.messages)


@pytest.mark.asyncio
async def test_agent_session_invoke_skill_reuses_loaded_skill_without_duplicate_tool_result(
    tmp_path: Path, skill_file_contents: str
) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")
    from app.services.generation.agentic.skills import SkillDiscovery
    from app.services.generation.agentic.tools import create_builtin_registry

    catalog = SkillDiscovery(tmp_path).discover()
    model = FakeModel(
        responses=[
            AssistantMessage(content="first use"),
            AssistantMessage(content="second use"),
        ]
    )
    agent = Agent(
        model=model,
        tool_registry=create_builtin_registry(tmp_path),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=catalog,
        system_prompt="Be helpful.",
    )

    session = agent.start_session()
    first = await session.invoke_skill("example-skill")
    second = await session.invoke_skill("example-skill", prompt="focus here")

    assert [tool_result.tool_name for tool_result in first.tool_results] == ["load_skill"]
    assert second.tool_results == []
    tool_messages = [message for message in session.messages if hasattr(message, "results")]
    assert sum(
        1
        for message in tool_messages
        for tool_result in message.results
        if tool_result.tool_name == "load_skill"
    ) == 1
    assert session.context_markers[-1].summary == "skill=example-skill args_present=true"


@pytest.mark.asyncio
async def test_agent_session_plan_updates_todos_and_uses_plan_only_toolset(tmp_path: Path) -> None:
    model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="todo",
                        args={"items": [{"id": 1, "text": "Inspect files", "status": "pending"}]},
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(content="Plan ready."),
        ]
    )
    from app.services.generation.agentic.tools import create_builtin_registry

    agent = Agent(
        model=model,
        tool_registry=create_builtin_registry(tmp_path),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=SkillCatalog(),
        system_prompt="Be helpful.",
    )

    session = agent.start_session()
    result = await session.plan("Refactor the project")

    assert result.stop_reason == "completed"
    assert session.todo_items[0]["text"] == "Inspect files"
    assert [tool["name"] for tool in model.seen_tools[0]] == ["todo"]
    assert all("Planning mode:" not in getattr(message, "content", "") for message in session.messages)


@pytest.mark.asyncio
async def test_agent_session_plan_uses_existing_context(tmp_path: Path) -> None:
    model = FakeModel(
        responses=[
            AssistantMessage(content="hello"),
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="todo",
                        args={"items": [{"id": 1, "text": "Use prior context", "status": "pending"}]},
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(content="Plan ready."),
        ]
    )
    from app.services.generation.agentic.tools import create_builtin_registry

    agent = Agent(
        model=model,
        tool_registry=create_builtin_registry(tmp_path),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=SkillCatalog(),
        system_prompt="Be helpful.",
    )

    session = agent.start_session()
    await session.send("remember this")
    await session.plan("make a plan")

    assert any(getattr(message, "content", "") == "remember this" for message in model.seen_messages[1])


@pytest.mark.asyncio
async def test_agent_session_nag_reminder_appears_after_three_non_todo_turns(tmp_path: Path) -> None:
    model = FakeModel(
        responses=[
            AssistantMessage(content="one"),
            AssistantMessage(content="two"),
            AssistantMessage(content="three"),
            AssistantMessage(content="four"),
        ]
    )
    agent = Agent(
        model=model,
        tool_registry=ToolRegistry(),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=SkillCatalog(),
        system_prompt="Be helpful.",
    )

    session = agent.start_session()
    await session.send("first")
    await session.send("second")
    await session.send("third")
    await session.send("fourth")

    assert any("<reminder>Update your todos.</reminder>" in getattr(message, "content", "") for message in model.seen_messages[3])
    assert all("<reminder>Update your todos.</reminder>" not in getattr(message, "content", "") for message in session.messages)


@pytest.mark.asyncio
async def test_follow_up_turn_does_not_receive_persisted_skill_invocation_template(
    tmp_path: Path, skill_file_contents: str
) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")
    from app.services.generation.agentic.skills import SkillDiscovery
    from app.services.generation.agentic.tools import create_builtin_registry

    catalog = SkillDiscovery(tmp_path).discover()
    model = FakeModel(
        responses=[
            AssistantMessage(content="used skill"),
            AssistantMessage(content="follow-up"),
        ]
    )
    agent = Agent(
        model=model,
        tool_registry=create_builtin_registry(tmp_path),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=catalog,
        system_prompt="Be helpful.",
    )

    session = agent.start_session()
    await session.invoke_skill("example-skill", prompt="handle task 42")
    await session.send("what did you just use?")

    assert all(
        "<skill_invocation>" not in getattr(message, "content", "")
        and "explicit_args_override_context_but_context_remains_available" not in getattr(message, "content", "")
        for message in model.seen_messages[1]
    )


@pytest.mark.asyncio
async def test_manual_compact_rebuilds_session_history_and_preserves_state(tmp_path: Path, skill_file_contents: str) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")
    from app.services.generation.agentic.skills import SkillDiscovery
    from app.services.generation.agentic.tools import create_builtin_registry

    catalog = SkillDiscovery(tmp_path).discover()
    model = FakeModel(
        responses=[
            AssistantMessage(content="skill output"),
            AssistantMessage(content="hello"),
            AssistantMessage(content="summary block"),
            AssistantMessage(content="after compact"),
        ]
    )
    agent = Agent(
        model=model,
        tool_registry=create_builtin_registry(tmp_path),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=catalog,
        system_prompt="Be helpful.",
        compact_tail_turns=0,
        auto_compact_enabled=False,
    )

    session = agent.start_session()
    await session.invoke_skill("example-skill")
    await session.send("first user turn")
    compact_result = await session.compact()
    follow_up = await session.send("second user turn")

    assert compact_result.generation == 1
    assert compact_result.retained_turns == 0
    assert session.compact_summary == "summary block"
    assert any("<compact_summary" in getattr(message, "content", "") for message in session.messages)
    assert any(
        getattr(message, "role", "") == "tool"
        and any(result.tool_name == "load_skill" for result in message.results)
        for message in session.messages
        if hasattr(message, "results")
    )
    assert any("first user turn" in getattr(message, "content", "") for message in model.seen_messages[2])
    assert any("<compact_summary" in getattr(message, "content", "") for message in model.seen_messages[3])
    assert follow_up.output_text == "after compact"


@pytest.mark.asyncio
async def test_manual_compact_keeps_todo_state_outside_summary(tmp_path: Path) -> None:
    from app.services.generation.agentic.tools import create_builtin_registry

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
            AssistantMessage(content="summary block"),
        ]
    )
    agent = Agent(
        model=model,
        tool_registry=create_builtin_registry(tmp_path),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=SkillCatalog(),
        system_prompt="Be helpful.",
        compact_tail_turns=1,
        auto_compact_enabled=False,
    )

    session = agent.start_session()
    await session.plan("make a plan")
    await session.compact()

    assert any("<todo_state>" in getattr(message, "content", "") for message in session.messages)
    assert all("Planning mode:" not in getattr(message, "content", "") for message in session.messages)


@pytest.mark.asyncio
async def test_auto_compact_runs_before_next_turn_when_usage_threshold_exceeded(tmp_path: Path) -> None:
    model = FakeModel(
        responses=[
            AssistantMessage(content="first"),
            AssistantMessage(content="summary block"),
            AssistantMessage(content="second"),
        ],
        usages=[
            ModelUsage(prompt_tokens=6500, completion_tokens=10, total_tokens=6510),
            ModelUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            ModelUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        ],
    )
    agent = Agent(
        model=model,
        tool_registry=ToolRegistry(),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=SkillCatalog(),
        system_prompt="Be helpful.",
        compact_token_threshold=6000,
        compact_tail_turns=0,
    )

    session = agent.start_session()
    first = await session.send("first turn")
    second = await session.send("second turn")

    assert first.output_text == "first"
    assert second.output_text == "second"
    assert second.compact_events[0]["trigger"] == "usage-threshold"
    assert session.compact_generation == 1
    assert any("<compact_summary" in getattr(message, "content", "") for message in session.messages)
    assert any("Older conversation to compact:" in getattr(message, "content", "") for message in model.seen_messages[1])


@pytest.mark.asyncio
async def test_no_auto_compact_when_usage_is_missing(tmp_path: Path) -> None:
    model = FakeModel(
        responses=[
            AssistantMessage(content="first"),
            AssistantMessage(content="second"),
        ]
    )
    agent = Agent(
        model=model,
        tool_registry=ToolRegistry(),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=SkillCatalog(),
        system_prompt="Be helpful.",
        compact_token_threshold=1,
    )

    session = agent.start_session()
    await session.send("first turn")
    second = await session.send("second turn")

    assert second.compact_events == []
    assert session.compact_generation == 0


@pytest.mark.asyncio
async def test_agent_session_use_task_rebuilds_context_and_scopes_todo(tmp_path: Path) -> None:
    task_manager = TaskManager.from_project(tmp_path, create_if_missing=True)
    first = task_manager.create_task(title="First task", summary="Work on the first task")
    second = task_manager.create_task(title="Second task", summary="Work on the second task")
    task_manager.update_task(
        first.id,
        todo_items=[{"id": 1, "text": "Do first task work", "status": "pending"}],
    )
    task_manager.update_task(
        second.id,
        todo_items=[{"id": 2, "text": "Do second task work", "status": "pending"}],
    )
    model = FakeModel(
        responses=[
            AssistantMessage(content="first reply"),
            AssistantMessage(content="second reply"),
        ]
    )
    agent = Agent(
        model=model,
        tool_registry=ToolRegistry(),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=SkillCatalog(),
        task_manager=task_manager,
        system_prompt="Be helpful.",
    )

    session = agent.start_session()
    await session.send("remember this first-task detail")
    switched = await session.use_task(second.id)
    await session.send("what is the current task?")

    assert switched["id"] == second.id
    assert session.current_task is not None and session.current_task["id"] == second.id
    assert session.todo_items == [{"id": 2, "text": "Do second task work", "status": "pending"}]
    assert any("<task_state" in getattr(message, "content", "") and second.id in getattr(message, "content", "") for message in session.messages)
    assert all("remember this first-task detail" not in getattr(message, "content", "") for message in model.seen_messages[1])
    assert any("Second task" in getattr(message, "content", "") for message in model.seen_messages[1])


@pytest.mark.asyncio
async def test_compact_persists_current_task_summary_and_todos(tmp_path: Path) -> None:
    task_manager = TaskManager.from_project(tmp_path, create_if_missing=True)
    task = task_manager.create_task(title="Task to compact", summary="Initial summary")
    from app.services.generation.agentic.tools import create_builtin_registry

    model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="todo",
                        args={"items": [{"id": 1, "text": "Track task work", "status": "pending"}]},
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(content="todo updated"),
            AssistantMessage(content="compacted summary"),
        ]
    )
    agent = Agent(
        model=model,
        tool_registry=create_builtin_registry(tmp_path),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=SkillCatalog(),
        task_manager=task_manager,
        system_prompt="Be helpful.",
        compact_tail_turns=0,
        auto_compact_enabled=False,
    )

    session = agent.start_session()
    await session.send("update the task plan")
    await session.compact()

    reloaded = TaskManager.from_project(tmp_path, create_if_missing=False)
    persisted = reloaded.require_task(task.id)

    assert persisted.compact_summary == "compacted summary"
    assert persisted.todo_items == [{"id": 1, "text": "Track task work", "status": "pending"}]


@pytest.mark.asyncio
async def test_subagent_tool_uses_isolated_messages(tmp_path: Path) -> None:
    from app.services.generation.agentic.tools import create_builtin_registry

    model = FakeModel(
        responses=[
            AssistantMessage(content="parent noted"),
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="subagent_run",
                        args={"task": "summarize only the delegated work", "context": "focus"},
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(content="subagent result"),
            AssistantMessage(content="parent done"),
        ]
    )
    agent = Agent(
        model=model,
        tool_registry=create_builtin_registry(tmp_path),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=SkillCatalog(),
        system_prompt="Be helpful.",
    )

    session = agent.start_session()
    await session.send("remember this parent-only detail")
    result = await session.send("delegate the subtask")

    assert result.stop_reason == "completed"
    assert any(tool_result.tool_name == "subagent_run" for tool_result in result.tool_results)
    assert "remember this parent-only detail" not in "".join(
        getattr(message, "content", "") for message in model.seen_messages[2]
    )
    assert "<delegated_subtask>" in "".join(getattr(message, "content", "") for message in model.seen_messages[2])
    assert model.seen_tools[2] == []


@pytest.mark.asyncio
async def test_subagent_run_with_explicit_allowed_tools_exposes_only_allowlisted_tools(tmp_path: Path) -> None:
    from app.services.generation.agentic.tools import create_builtin_registry

    target = tmp_path / "note.txt"
    target.write_text("hello", encoding="utf-8")
    model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="subagent_run",
                        args={"task": "read note", "context": "need file contents", "allowed_tools": ["read_file"]},
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(
                tool_calls=[ToolCall(tool_name="read_file", args={"path": "note.txt"}, tool_call_id="call-2")]
            ),
            AssistantMessage(content="file read"),
            AssistantMessage(content="parent done"),
        ]
    )
    agent = Agent(
        model=model,
        tool_registry=create_builtin_registry(tmp_path),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=SkillCatalog(),
        system_prompt="Be helpful.",
    )

    session = agent.start_session()
    result = await session.send("delegate with read access")

    assert result.stop_reason == "completed"
    assert [tool["name"] for tool in model.seen_tools[1]] == ["read_file"]


@pytest.mark.asyncio
async def test_background_notifications_are_injected_before_next_turn(tmp_path: Path) -> None:
    from app.services.generation.agentic.tools import create_builtin_registry

    model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        tool_name="background_run",
                        args={"command": "python3 -c \"print('bg done')\""},
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(content="background started"),
            AssistantMessage(content="noticed background result"),
        ]
    )
    agent = Agent(
        model=model,
        tool_registry=create_builtin_registry(tmp_path),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=SkillCatalog(),
        system_prompt="Be helpful.",
    )

    session = agent.start_session()
    first = await session.send("start background work")
    assert first.stop_reason == "completed"

    for _ in range(100):
        tasks = session.background_manager.check() if session.background_manager is not None else []
        if tasks and tasks[0]["status"] != "running":
            break
        await asyncio.sleep(0.01)

    second = await session.send("what finished?")

    assert second.stop_reason == "completed"
    assert any("<background_results>" in getattr(message, "content", "") for message in model.seen_messages[2])


@pytest.mark.asyncio
async def test_model_can_call_load_skill_and_receive_tool_result(tmp_path: Path, skill_file_contents: str) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")
    from app.services.generation.agentic.skills import SkillDiscovery
    from app.services.generation.agentic.tools import create_builtin_registry

    catalog = SkillDiscovery(tmp_path).discover()
    model = FakeModel(
        responses=[
            AssistantMessage(
                tool_calls=[ToolCall(tool_name="load_skill", args={"name": "example-skill"}, tool_call_id="call-1")]
            ),
            AssistantMessage(content="used skill"),
        ]
    )
    agent = Agent(
        model=model,
        tool_registry=create_builtin_registry(tmp_path),
        tool_context=default_tool_context(tmp_path),
        skill_catalog=catalog,
        system_prompt="Be helpful.",
    )

    result = await agent.run("Need example workflow")

    assert result.stop_reason == "completed"
    assert result.tool_results[0].tool_name == "load_skill"
    assert "skill_content" in str(result.tool_results[0].content)

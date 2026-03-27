from __future__ import annotations

import asyncio

import pytest

from app.services.generation.agentic_legacy.todo import TodoManager, build_todo_nag, build_update_todo_tool
from app.services.generation.agentic_legacy.tools import ToolRegistry, dispatch_tool_calls
from app.services.generation.agentic_legacy.types import ToolCall


def test_todo_manager_updates_and_formats_items():
    manager = TodoManager()

    formatted = manager.update(
        [
            {"id": 1, "task": "解析文档", "status": "done"},
            {"id": 2, "task": "生成大纲", "status": "in_progress"},
            {"id": 3, "task": "选择布局", "status": "pending"},
        ]
    )

    assert formatted == "✅ 1. 解析文档\n🔄 2. 生成大纲\n⬜ 3. 选择布局"
    assert manager.has_pending is True


def test_todo_manager_rejects_multiple_in_progress_items():
    manager = TodoManager()

    with pytest.raises(ValueError, match="only one todo item can be in_progress at a time"):
        manager.update(
            [
                {"id": 1, "task": "解析文档", "status": "in_progress"},
                {"id": 2, "task": "生成大纲", "status": "in_progress"},
            ]
        )


def test_todo_manager_rejects_missing_or_invalid_ids():
    manager = TodoManager()

    with pytest.raises(ValueError, match="todo item id must be an integer"):
        manager.update([{"task": "解析文档", "status": "pending"}])

    with pytest.raises(ValueError, match="todo item id must be an integer"):
        manager.update([{"id": object(), "task": "解析文档", "status": "pending"}])


def test_build_todo_nag_reflects_empty_pending_and_done_states():
    manager = TodoManager()
    assert "还没有创建任务计划" in str(build_todo_nag(manager))

    manager.update(
        [
            {"id": 1, "task": "解析文档", "status": "done"},
            {"id": 2, "task": "生成大纲", "status": "pending"},
        ]
    )
    nag = build_todo_nag(manager)
    assert nag is not None
    assert "当前计划状态" in nag
    assert "⬜ 2. 生成大纲" in nag

    manager.update([{"id": 2, "task": "生成大纲", "status": "done"}])
    assert build_todo_nag(manager) is None


def test_update_todo_tool_updates_manager_via_registry_dispatch():
    async def _case():
        manager = TodoManager()
        registry = ToolRegistry()
        registry.register(build_update_todo_tool(manager))

        result = await dispatch_tool_calls(
            [
                ToolCall(
                    tool_name="update_todo",
                    args={
                        "items": [
                            {"id": 1, "task": "解析文档", "status": "done"},
                            {"id": 2, "task": "生成大纲", "status": "in_progress"},
                        ]
                    },
                    tool_call_id="call-1",
                )
            ],
            registry,
        )

        assert result.stop_loop is False
        assert result.parts[0].tool_name == "update_todo"
        assert "🔄 2. 生成大纲" in str(result.parts[0].content)
        assert manager.items[1].status == "in_progress"

    asyncio.run(_case())

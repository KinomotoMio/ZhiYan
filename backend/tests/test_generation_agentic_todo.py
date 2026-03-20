import pytest

from app.services.generation.agentic.todo import (
    TodoManager,
    build_todo_nag,
    build_update_todo_tool_definition,
    update_todo,
)


def test_update_todo_creates_and_updates_items():
    manager = TodoManager()

    first = update_todo(
        [
            {"id": 1, "task": "解析文档", "status": "done"},
            {"id": 2, "task": "生成大纲", "status": "in_progress"},
            {"id": 3, "task": "选择布局", "status": "pending"},
        ],
        manager,
    )

    assert first == "✅ 1. 解析文档\n🔄 2. 生成大纲\n⬜ 3. 选择布局"
    assert manager.items[1].status == "in_progress"

    second = manager.update(
        [
            {"id": 2, "task": "生成大纲并补充章节", "status": "done"},
            {"id": 4, "task": "生成幻灯片", "status": "pending"},
        ]
    )

    assert second == "✅ 1. 解析文档\n✅ 2. 生成大纲并补充章节\n⬜ 3. 选择布局\n⬜ 4. 生成幻灯片"
    assert [item.id for item in manager.items] == [1, 2, 3, 4]


def test_build_todo_nag_before_planning_and_with_pending_work():
    manager = TodoManager()

    nag = build_todo_nag(manager)
    assert nag is not None
    assert "update_todo" in nag
    assert "创建计划" in nag

    manager.update(
        [
            {"id": 1, "task": "解析文档", "status": "done"},
            {"id": 2, "task": "生成大纲", "status": "in_progress"},
            {"id": 3, "task": "选择布局", "status": "pending"},
        ]
    )

    nag = build_todo_nag(manager)
    assert nag is not None
    assert "当前计划状态" in nag
    assert "🔄 2. 生成大纲" in nag
    assert "⬜ 3. 选择布局" in nag
    assert "请按计划继续执行" in nag


def test_build_todo_nag_stops_when_complete():
    manager = TodoManager()
    manager.update(
        [
            {"id": 1, "task": "解析文档", "status": "done"},
            {"id": 2, "task": "生成大纲", "status": "done"},
        ]
    )

    assert build_todo_nag(manager) is None


def test_update_todo_rejects_multiple_in_progress_items():
    manager = TodoManager()

    with pytest.raises(ValueError, match="only one todo item can be in_progress"):
        manager.update(
            [
                {"id": 1, "task": "解析文档", "status": "in_progress"},
                {"id": 2, "task": "生成大纲", "status": "in_progress"},
            ]
        )


def test_update_todo_tool_definition_has_expected_schema():
    tool = build_update_todo_tool_definition()

    assert tool["name"] == "update_todo"
    assert tool["input_schema"]["type"] == "object"
    items_schema = tool["input_schema"]["properties"]["items"]
    assert items_schema["type"] == "array"
    assert items_schema["items"]["properties"]["status"]["enum"] == ["pending", "in_progress", "done"]

"""Planning helpers for generation agentic mode."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Mapping

TODO_STATUSES = ("pending", "in_progress", "done")
TodoStatus = Literal["pending", "in_progress", "done"]

_STATUS_ICONS: dict[TodoStatus, str] = {
    "pending": "⬜",
    "in_progress": "🔄",
    "done": "✅",
}


@dataclass(slots=True)
class TodoItem:
    id: int
    task: str
    status: TodoStatus


@dataclass(slots=True)
class TodoManager:
    items: list[TodoItem] = field(default_factory=list)

    def update(self, items: Iterable[Mapping[str, Any]]) -> str:
        normalized = [_normalize_item(item) for item in items]
        _validate_unique_ids(normalized)
        _validate_in_progress(normalized)

        by_id = {item.id: item for item in self.items}
        existing_order = [item.id for item in self.items]

        for item in normalized:
            if item.id in by_id:
                by_id[item.id].task = item.task
                by_id[item.id].status = item.status
            else:
                by_id[item.id] = TodoItem(id=item.id, task=item.task, status=item.status)
                existing_order.append(item.id)

        self.items = [by_id[item_id] for item_id in existing_order]
        _validate_in_progress(self.items)
        return self.format()

    def format(self) -> str:
        if not self.items:
            return ""
        return "\n".join(f"{_STATUS_ICONS[item.status]} {item.id}. {item.task}" for item in self.items)

    @property
    def has_pending(self) -> bool:
        return any(item.status != "done" for item in self.items)


def update_todo(items: Iterable[Mapping[str, Any]], manager: TodoManager | None = None) -> str:
    """Update todo state and return a model-readable plan summary."""

    todo_manager = manager or TodoManager()
    return todo_manager.update(items)


def build_todo_nag(manager: TodoManager) -> str | None:
    if not manager.items:
        return "你还没有创建任务计划。请先调用 update_todo 创建计划，再执行其他工具。"

    if manager.has_pending:
        return "当前计划状态：\n" + manager.format() + "\n\n请按计划继续执行。"

    return None


def build_update_todo_tool_definition() -> dict[str, Any]:
    return {
        "name": "update_todo",
        "description": "创建或更新任务计划。在执行其他生成工具前先用它记录计划。",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "task": {"type": "string"},
                            "status": {"type": "string", "enum": list(TODO_STATUSES)},
                        },
                        "required": ["id", "task", "status"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["items"],
            "additionalProperties": False,
        },
    }


def _normalize_item(raw: Mapping[str, Any]) -> TodoItem:
    try:
        item_id = int(raw["id"])
    except Exception as exc:
        raise ValueError("todo item id must be an integer") from exc

    task = str(raw["task"]).strip()
    if not task:
        raise ValueError("todo item task must not be empty")

    status = str(raw["status"]).strip()
    if status not in TODO_STATUSES:
        raise ValueError(f"invalid todo status: {status}; expected one of {TODO_STATUSES}")

    return TodoItem(id=item_id, task=task, status=status)


def _validate_unique_ids(items: Iterable[TodoItem]) -> None:
    seen: set[int] = set()
    for item in items:
        if item.id in seen:
            raise ValueError("duplicate todo item id in update payload")
        seen.add(item.id)


def _validate_in_progress(items: Iterable[TodoItem]) -> None:
    in_progress = [item.id for item in items if item.status == "in_progress"]
    if len(in_progress) > 1:
        raise ValueError("only one todo item can be in_progress at a time")

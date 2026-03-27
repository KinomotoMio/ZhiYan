from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


TodoStatus = Literal["pending", "in_progress", "done"]


@dataclass(slots=True)
class TodoItem:
    id: int
    text: str
    status: TodoStatus = "pending"


@dataclass(slots=True)
class TodoManager:
    items: list[TodoItem] = field(default_factory=list)

    def update(self, items: list[dict[str, object]]) -> dict[str, object]:
        validated: list[TodoItem] = []
        in_progress_count = 0
        for raw in items:
            status = str(raw.get("status", "pending"))
            if status not in {"pending", "in_progress", "done"}:
                raise ValueError(f"Invalid todo status: {status}")
            if status == "in_progress":
                in_progress_count += 1
            text = str(raw.get("text", "")).strip()
            if not text:
                raise ValueError("Todo items require non-empty text.")
            validated.append(
                TodoItem(
                    id=int(raw["id"]),
                    text=text,
                    status=status,
                )
            )
        if in_progress_count > 1:
            raise ValueError("Only one todo item can be in_progress.")
        self.items = validated
        return self.snapshot()

    def reset(self) -> None:
        self.items = []

    def snapshot(self) -> dict[str, object]:
        done = sum(item.status == "done" for item in self.items)
        in_progress = sum(item.status == "in_progress" for item in self.items)
        pending = sum(item.status == "pending" for item in self.items)
        return {
            "items": [self._serialize_item(item) for item in self.items],
            "summary": self.render(),
            "counts": {
                "pending": pending,
                "in_progress": in_progress,
                "done": done,
                "total": len(self.items),
            },
        }

    def render(self) -> str:
        if not self.items:
            return "Current plan:\n- (empty)"
        lines = ["Current plan:"]
        for item in self.items:
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "done": "[x]",
            }[item.status]
            lines.append(f"{marker} #{item.id} {item.text}")
        done = sum(item.status == "done" for item in self.items)
        lines.append(f"Progress: {done}/{len(self.items)} complete")
        return "\n".join(lines)

    def _serialize_item(self, item: TodoItem) -> dict[str, object]:
        return {"id": item.id, "text": item.text, "status": item.status}

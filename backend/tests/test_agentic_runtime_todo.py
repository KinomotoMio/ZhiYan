from __future__ import annotations

import pytest

from app.services.generation.agentic.todo import TodoManager


def test_todo_manager_accepts_valid_items_and_renders_summary() -> None:
    manager = TodoManager()

    snapshot = manager.update(
        [
            {"id": 1, "text": "Inspect files", "status": "done"},
            {"id": 2, "text": "Write tests", "status": "in_progress"},
            {"id": 3, "text": "Run checks", "status": "pending"},
        ]
    )

    assert snapshot["counts"]["total"] == 3
    assert "Current plan:" in snapshot["summary"]
    assert "#2 Write tests" in snapshot["summary"]


def test_todo_manager_rejects_multiple_in_progress() -> None:
    manager = TodoManager()

    with pytest.raises(ValueError, match="Only one todo item can be in_progress"):
        manager.update(
            [
                {"id": 1, "text": "One", "status": "in_progress"},
                {"id": 2, "text": "Two", "status": "in_progress"},
            ]
        )

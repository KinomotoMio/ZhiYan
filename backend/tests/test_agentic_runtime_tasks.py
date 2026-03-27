from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.generation.agentic.tasks import TaskManager


def test_task_manager_initializes_persistence_layout(tmp_path: Path) -> None:
    manager = TaskManager.from_project(tmp_path, create_if_missing=True)

    assert manager.index_path == tmp_path / ".agents" / "tasks" / "index.json"
    assert manager.index_path.exists()
    assert json.loads(manager.index_path.read_text(encoding="utf-8")) == {
        "current_task_id": None,
        "tasks": [],
    }


def test_task_manager_persists_and_reloads_graph(tmp_path: Path) -> None:
    manager = TaskManager.from_project(tmp_path, create_if_missing=True)
    first = manager.create_task(title="First task", summary="Do the first thing")
    second = manager.create_task(title="Second task", dependencies=[first.id])
    manager.update_task(first.id, status="done")
    manager.use_task(second.id)

    reloaded = TaskManager.from_project(tmp_path, create_if_missing=False)

    assert reloaded.current_task_id == second.id
    assert reloaded.require_task(first.id).summary == "Do the first thing"
    assert (tmp_path / ".agents" / "tasks" / f"{first.id}.json").exists()
    assert (tmp_path / ".agents" / "tasks" / f"{second.id}.json").exists()


def test_task_manager_reads_legacy_root_tasks_and_rewrites_to_agents_dir(tmp_path: Path) -> None:
    legacy_tasks_dir = tmp_path / "tasks"
    legacy_tasks_dir.mkdir(parents=True)
    legacy_index_path = legacy_tasks_dir / "index.json"
    legacy_index_path.write_text(
        json.dumps(
            {
                "current_task_id": "second-task",
                "tasks": [
                    {"id": "first-task", "title": "First task", "status": "done", "dependencies": []},
                    {
                        "id": "second-task",
                        "title": "Second task",
                        "status": "pending",
                        "dependencies": ["first-task"],
                    },
                ],
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (legacy_tasks_dir / "first-task.json").write_text(
        json.dumps(
            {
                "id": "first-task",
                "title": "First task",
                "status": "done",
                "dependencies": [],
                "summary": "Do the first thing",
                "notes": [],
                "updated_at": "2026-03-27T00:00:00+00:00",
                "compact_summary": "",
                "todo_items": [],
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (legacy_tasks_dir / "second-task.json").write_text(
        json.dumps(
            {
                "id": "second-task",
                "title": "Second task",
                "status": "pending",
                "dependencies": ["first-task"],
                "summary": "",
                "notes": [],
                "updated_at": "2026-03-27T00:00:00+00:00",
                "compact_summary": "",
                "todo_items": [],
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    manager = TaskManager.from_project(tmp_path, create_if_missing=False)

    assert manager.index_path == tmp_path / ".agents" / "tasks" / "index.json"
    assert manager.current_task_id == "second-task"
    assert manager.require_task("first-task").summary == "Do the first thing"
    assert not manager.index_path.exists()

    manager.update_task("second-task", summary="Migrated")

    assert manager.index_path.exists()
    assert (tmp_path / ".agents" / "tasks" / "first-task.json").exists()
    assert (tmp_path / ".agents" / "tasks" / "second-task.json").exists()
    assert json.loads(manager.index_path.read_text(encoding="utf-8"))["current_task_id"] == "second-task"
    assert json.loads((legacy_tasks_dir / "second-task.json").read_text(encoding="utf-8"))["summary"] == ""


def test_task_manager_reports_blocked_tasks_and_validates_dependencies(tmp_path: Path) -> None:
    manager = TaskManager.from_project(tmp_path, create_if_missing=True)
    parent = manager.create_task(title="Parent")
    child = manager.create_task(title="Child", dependencies=[parent.id])

    assert manager.effective_status(child.id) == "blocked"
    assert manager.blocking_dependencies(child.id) == [parent.id]

    manager.update_task(parent.id, status="done")

    assert manager.effective_status(child.id) == "pending"
    with pytest.raises(ValueError, match="Unknown dependency"):
        manager.update_task(child.id, dependencies=["missing"])
    with pytest.raises(ValueError, match="cannot depend on itself"):
        manager.update_task(child.id, dependencies=[child.id])

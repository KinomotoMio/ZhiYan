from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Literal


TaskStatus = Literal["pending", "in_progress", "blocked", "done"]


@dataclass(slots=True)
class TaskRecord:
    id: str
    title: str
    status: TaskStatus = "pending"
    dependencies: list[str] = field(default_factory=list)
    summary: str = ""
    notes: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    compact_summary: str = ""
    todo_items: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "dependencies": list(self.dependencies),
            "summary": self.summary,
            "notes": list(self.notes),
            "updated_at": self.updated_at,
            "compact_summary": self.compact_summary,
            "todo_items": list(self.todo_items),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskRecord":
        return cls(
            id=str(payload["id"]),
            title=str(payload["title"]),
            status=str(payload.get("status", "pending")),  # type: ignore[arg-type]
            dependencies=[str(item) for item in payload.get("dependencies", [])],
            summary=str(payload.get("summary", "")),
            notes=[str(item) for item in payload.get("notes", [])],
            updated_at=str(payload.get("updated_at", datetime.now(UTC).isoformat())),
            compact_summary=str(payload.get("compact_summary", "")),
            todo_items=[dict(item) for item in payload.get("todo_items", [])],
        )


@dataclass(slots=True)
class TaskIndexEntry:
    id: str
    title: str
    status: TaskStatus
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "dependencies": list(self.dependencies),
        }


@dataclass(slots=True)
class TaskIndex:
    current_task_id: str | None = None
    tasks: list[TaskIndexEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_task_id": self.current_task_id,
            "tasks": [task.to_dict() for task in self.tasks],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskIndex":
        return cls(
            current_task_id=str(payload["current_task_id"]) if payload.get("current_task_id") else None,
            tasks=[
                TaskIndexEntry(
                    id=str(item["id"]),
                    title=str(item["title"]),
                    status=str(item.get("status", "pending")),  # type: ignore[arg-type]
                    dependencies=[str(dep) for dep in item.get("dependencies", [])],
                )
                for item in payload.get("tasks", [])
            ],
        )


@dataclass(slots=True)
class TaskManager:
    project_root: Path
    tasks_dir: Path
    index_path: Path
    records: dict[str, TaskRecord] = field(default_factory=dict)
    current_task_id: str | None = None

    @classmethod
    def from_project(cls, project_root: Path, *, create_if_missing: bool = True) -> "TaskManager":
        primary_tasks_dir = (project_root / ".agents" / "tasks").resolve()
        primary_index_path = primary_tasks_dir / "index.json"
        legacy_tasks_dir = (project_root / "tasks").resolve()
        legacy_index_path = legacy_tasks_dir / "index.json"
        if primary_index_path.exists():
            tasks_dir = primary_tasks_dir
            index_path = primary_index_path
        elif legacy_index_path.exists():
            tasks_dir = legacy_tasks_dir
            index_path = legacy_index_path
        else:
            tasks_dir = primary_tasks_dir
            index_path = primary_index_path
        if create_if_missing:
            primary_tasks_dir.mkdir(parents=True, exist_ok=True)
            if not index_path.exists():
                index_path.write_text(json.dumps(TaskIndex().to_dict(), ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        records: dict[str, TaskRecord] = {}
        current_task_id: str | None = None
        if index_path.exists():
            index = TaskIndex.from_dict(json.loads(index_path.read_text(encoding="utf-8")))
            current_task_id = index.current_task_id
            for entry in index.tasks:
                task_path = tasks_dir / f"{entry.id}.json"
                if task_path.exists():
                    records[entry.id] = TaskRecord.from_dict(json.loads(task_path.read_text(encoding="utf-8")))
                else:
                    records[entry.id] = TaskRecord(
                        id=entry.id,
                        title=entry.title,
                        status=entry.status,
                        dependencies=list(entry.dependencies),
                    )
        return cls(
            project_root=project_root.resolve(),
            tasks_dir=primary_tasks_dir,
            index_path=primary_index_path,
            records=records,
            current_task_id=current_task_id,
        )

    @property
    def current_task(self) -> TaskRecord | None:
        if self.current_task_id is None:
            return None
        return self.records.get(self.current_task_id)

    def list_tasks(self) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        for task in sorted(self.records.values(), key=lambda item: item.id):
            blocked_by = self.blocking_dependencies(task.id)
            tasks.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "status": self.effective_status(task.id),
                    "current": task.id == self.current_task_id,
                    "dependencies": list(task.dependencies),
                    "blocked_by": blocked_by,
                    "summary": task.summary,
                    "updated_at": task.updated_at,
                }
            )
        return tasks

    def create_task(
        self,
        *,
        title: str,
        task_id: str | None = None,
        dependencies: list[str] | None = None,
        summary: str = "",
        notes: list[str] | None = None,
        status: TaskStatus = "pending",
    ) -> TaskRecord:
        resolved_id = task_id or self._generate_task_id(title)
        if resolved_id in self.records:
            raise ValueError(f"Task already exists: {resolved_id}")
        dependencies = dependencies or []
        self._validate_dependencies(dependencies)
        record = TaskRecord(
            id=resolved_id,
            title=title.strip(),
            status=status,
            dependencies=list(dependencies),
            summary=summary,
            notes=list(notes or []),
        )
        self.records[record.id] = record
        if self.current_task_id is None:
            self.current_task_id = record.id
        self.save()
        return record

    def update_task(
        self,
        task_id: str,
        *,
        title: str | None = None,
        status: TaskStatus | None = None,
        dependencies: list[str] | None = None,
        summary: str | None = None,
        note: str | None = None,
        replace_notes: bool = False,
        compact_summary: str | None = None,
        todo_items: list[dict[str, object]] | None = None,
    ) -> TaskRecord:
        record = self.require_task(task_id)
        if title is not None:
            record.title = title.strip()
        if status is not None:
            record.status = status
        if dependencies is not None:
            self._validate_dependencies(dependencies, excluding=task_id)
            record.dependencies = list(dependencies)
        if summary is not None:
            record.summary = summary
        if note is not None:
            record.notes = [note] if replace_notes else [*record.notes, note]
        if compact_summary is not None:
            record.compact_summary = compact_summary
        if todo_items is not None:
            record.todo_items = [dict(item) for item in todo_items]
        record.updated_at = datetime.now(UTC).isoformat()
        self.save()
        return record

    def use_task(self, task_id: str) -> TaskRecord:
        record = self.require_task(task_id)
        self.current_task_id = record.id
        self.save()
        return record

    def effective_status(self, task_id: str) -> TaskStatus:
        record = self.require_task(task_id)
        if record.status == "done":
            return "done"
        if self.blocking_dependencies(task_id):
            return "blocked"
        if record.status == "blocked":
            return "blocked"
        return record.status

    def blocking_dependencies(self, task_id: str) -> list[str]:
        record = self.require_task(task_id)
        return [dependency for dependency in record.dependencies if self.require_task(dependency).status != "done"]

    def require_task(self, task_id: str) -> TaskRecord:
        record = self.records.get(task_id)
        if record is None:
            raise ValueError(f"Unknown task: {task_id}")
        return record

    def save(self) -> None:
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        for record in self.records.values():
            task_path = self.tasks_dir / f"{record.id}.json"
            task_path.write_text(json.dumps(record.to_dict(), ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        index = TaskIndex(
            current_task_id=self.current_task_id,
            tasks=[
                TaskIndexEntry(
                    id=record.id,
                    title=record.title,
                    status=record.status,
                    dependencies=list(record.dependencies),
                )
                for record in sorted(self.records.values(), key=lambda item: item.id)
            ],
        )
        self.index_path.write_text(json.dumps(index.to_dict(), ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    def _validate_dependencies(self, dependencies: list[str], excluding: str | None = None) -> None:
        for dependency in dependencies:
            if dependency == excluding:
                raise ValueError("A task cannot depend on itself.")
            if dependency not in self.records:
                raise ValueError(f"Unknown dependency: {dependency}")

    def _generate_task_id(self, title: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "task"
        candidate = base
        counter = 2
        while candidate in self.records:
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

from __future__ import annotations

import asyncio
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from .subagents import SubagentManager


class BashValidator(Protocol):
    def validate(self, command: str, working_directory: Path) -> None:
        ...


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class BackgroundTaskRecord:
    task_id: str
    kind: str
    status: str
    summary: str
    started_at: str = field(default_factory=_utc_now)
    completed_at: str | None = None
    result_preview: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "kind": self.kind,
            "status": self.status,
            "summary": self.summary,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result_preview": self.result_preview,
            "error": self.error,
        }


@dataclass(slots=True)
class BackgroundNotification:
    task_id: str
    kind: str
    status: str
    summary: str
    result_preview: str

    def to_dict(self) -> dict[str, str]:
        return {
            "task_id": self.task_id,
            "kind": self.kind,
            "status": self.status,
            "summary": self.summary,
            "result_preview": self.result_preview,
        }


@dataclass(slots=True)
class BackgroundManager:
    bash_policy: BashValidator
    subagent_manager: SubagentManager | None = None
    tasks: dict[str, BackgroundTaskRecord] = field(default_factory=dict)
    _notifications: list[BackgroundNotification] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def run_command(
        self,
        *,
        command: str,
        working_directory: Path,
        timeout_seconds: float,
    ) -> str:
        self.bash_policy.validate(command, working_directory)
        task_id = self._start_task(kind="command", summary=command)
        thread = threading.Thread(
            target=self._execute_command,
            args=(task_id, command, working_directory, timeout_seconds),
            daemon=True,
        )
        thread.start()
        return task_id

    def run_subagent(
        self,
        *,
        task: str,
        context: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int | None = None,
    ) -> str:
        if self.subagent_manager is None:
            raise ValueError("Subagent manager is not available in this context.")
        task_id = self._start_task(kind="subagent", summary=task)
        thread = threading.Thread(
            target=self._execute_subagent,
            args=(task_id, task, context, allowed_tools, max_turns),
            daemon=True,
        )
        thread.start()
        return task_id

    def check(self, task_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if task_id is not None:
                record = self.tasks.get(task_id)
                if record is None:
                    raise ValueError(f"Unknown background task: {task_id}")
                return [record.to_dict()]
            return [record.to_dict() for record in self.tasks.values()]

    def drain_notifications(self) -> list[dict[str, str]]:
        with self._lock:
            notifications = [notification.to_dict() for notification in self._notifications]
            self._notifications.clear()
        return notifications

    def _start_task(self, *, kind: str, summary: str) -> str:
        task_id = str(uuid.uuid4())[:8]
        with self._lock:
            self.tasks[task_id] = BackgroundTaskRecord(
                task_id=task_id,
                kind=kind,
                status="running",
                summary=summary,
            )
        return task_id

    def _execute_command(
        self,
        task_id: str,
        command: str,
        working_directory: Path,
        timeout_seconds: float,
    ) -> None:
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(working_directory),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            output = f"{result.stdout}{result.stderr}".strip()
            preview = _truncate(output or f"Command finished with return code {result.returncode}.")
            status = "completed" if result.returncode == 0 else "error"
            self._finish_task(task_id, status=status, result_preview=preview)
        except subprocess.TimeoutExpired:
            self._finish_task(task_id, status="error", result_preview="Error: Timeout", error="Timeout")
        except Exception as exc:
            self._finish_task(task_id, status="error", result_preview=f"{type(exc).__name__}: {exc}", error=str(exc))

    def _execute_subagent(
        self,
        task_id: str,
        task: str,
        context: str | None,
        allowed_tools: list[str] | None,
        max_turns: int | None,
    ) -> None:
        assert self.subagent_manager is not None
        try:
            result = asyncio.run(
                self.subagent_manager.run(
                    task=task,
                    context=context,
                    allowed_tools=allowed_tools,
                    max_turns=max_turns,
                )
            )
            preview = _truncate(result.get("output_text") or result.get("error") or result["stop_reason"])
            status = "completed" if result["stop_reason"] == "completed" else "error"
            self._finish_task(task_id, status=status, result_preview=preview, error=result.get("error"))
        except Exception as exc:
            self._finish_task(task_id, status="error", result_preview=f"{type(exc).__name__}: {exc}", error=str(exc))

    def _finish_task(
        self,
        task_id: str,
        *,
        status: str,
        result_preview: str,
        error: str | None = None,
    ) -> None:
        with self._lock:
            record = self.tasks[task_id]
            record.status = status
            record.completed_at = _utc_now()
            record.result_preview = result_preview
            record.error = error
            self._notifications.append(
                BackgroundNotification(
                    task_id=record.task_id,
                    kind=record.kind,
                    status=record.status,
                    summary=record.summary,
                    result_preview=result_preview,
                )
            )


def _truncate(value: str, limit: int = 500) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."

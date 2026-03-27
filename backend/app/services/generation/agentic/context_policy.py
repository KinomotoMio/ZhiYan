from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from .types import Message, ToolResult, UserMessage


class ContextRetentionClass(StrEnum):
    PERSISTENT_CONTENT = "persistent_content"
    PERSISTENT_MARKER = "persistent_marker"
    EPHEMERAL_CONTROL = "ephemeral_control"
    RUNTIME_ONLY = "runtime_only"


@dataclass(slots=True)
class ContextMarker:
    kind: str
    summary: str
    retention: ContextRetentionClass = ContextRetentionClass.PERSISTENT_MARKER
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "kind": self.kind,
            "summary": self.summary,
            "retention": self.retention.value,
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(slots=True)
class ContextPolicy:
    def task_state_message(
        self,
        *,
        task_id: str,
        title: str,
        status: str,
        dependencies: list[str],
        blocked_by: list[str],
        summary: str,
        notes: list[str],
    ) -> UserMessage:
        lines = [
            f'<task_state id="{task_id}">',
            f"Title: {title}",
            f"Status: {status}",
            f"Dependencies: {', '.join(dependencies) if dependencies else '(none)'}",
            f"Blocked by: {', '.join(blocked_by) if blocked_by else '(none)'}",
            f"Summary: {summary or '(empty)'}",
            "Notes:",
        ]
        if notes:
            lines.extend(f"- {note}" for note in notes[-5:])
        else:
            lines.append("- (empty)")
        lines.append("</task_state>")
        return UserMessage(content="\n".join(lines))

    def compact_summary_message(self, summary: str, generation: int) -> UserMessage:
        return UserMessage(content=f'<compact_summary generation="{generation}">\n{summary}\n</compact_summary>')

    def todo_state_message(self, summary: str) -> UserMessage:
        return UserMessage(content=f"<todo_state>\n{summary}\n</todo_state>")

    def planning_control_message(self, prompt: str) -> UserMessage:
        return UserMessage(
            content=(
                "Planning mode: break the request into concrete steps, use the todo tool to create or update the "
                "plan, and do not perform implementation in this planning turn.\n\n"
                f"User request:\n{prompt}"
            )
        )

    def reminder_message(self) -> UserMessage:
        return UserMessage(content="<reminder>Update your todos.</reminder>")

    def background_results_message(self, notifications: list[dict[str, str]]) -> UserMessage:
        lines = ["<background_results>"]
        for notification in notifications:
            lines.append(
                f"[bg:{notification['task_id']}] kind={notification['kind']} status={notification['status']} "
                f"summary={notification['summary']} result={notification['result_preview']}"
            )
        lines.append("</background_results>")
        return UserMessage(content="\n".join(lines))

    def persistent_tool_results(self, tool_results: list[ToolResult]) -> list[ToolResult]:
        return [replace(tool_result, metadata={}) for tool_result in tool_results]

    def is_compact_summary_message(self, message: Message) -> bool:
        return getattr(message, "role", None) == "user" and getattr(message, "content", "").startswith("<compact_summary")

    def is_todo_state_message(self, message: Message) -> bool:
        return getattr(message, "role", None) == "user" and getattr(message, "content", "").startswith("<todo_state>")

    def is_task_state_message(self, message: Message) -> bool:
        return getattr(message, "role", None) == "user" and getattr(message, "content", "").startswith("<task_state")

    def skill_invocation_marker(self, name: str, args: str | None) -> ContextMarker:
        return ContextMarker(
            kind="skill_invocation",
            summary=f"skill={name} args_present={'true' if bool(args and args.strip()) else 'false'}",
            metadata={"skill_name": name, "args_present": bool(args and args.strip())},
        )

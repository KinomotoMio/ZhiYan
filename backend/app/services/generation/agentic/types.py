from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None


@dataclass(slots=True)
class ToolCall:
    tool_name: str
    args: dict[str, Any]
    tool_call_id: str


@dataclass(slots=True)
class ToolResult:
    tool_name: str
    tool_call_id: str
    content: JsonValue
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SystemMessage:
    content: str
    role: Literal["system"] = "system"


@dataclass(slots=True)
class UserMessage:
    content: str
    role: Literal["user"] = "user"


@dataclass(slots=True)
class AssistantMessage:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    role: Literal["assistant"] = "assistant"


@dataclass(slots=True)
class ToolMessage:
    results: list[ToolResult]
    role: Literal["tool"] = "tool"


Message = SystemMessage | UserMessage | AssistantMessage | ToolMessage


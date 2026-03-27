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


def serialize_tool_call(tool_call: ToolCall) -> dict[str, Any]:
    return {
        "tool_name": tool_call.tool_name,
        "args": dict(tool_call.args),
        "tool_call_id": tool_call.tool_call_id,
    }


def deserialize_tool_call(payload: dict[str, Any]) -> ToolCall:
    return ToolCall(
        tool_name=str(payload.get("tool_name") or ""),
        args=dict(payload.get("args") or {}),
        tool_call_id=str(payload.get("tool_call_id") or ""),
    )


def serialize_tool_result(tool_result: ToolResult) -> dict[str, Any]:
    return {
        "tool_name": tool_result.tool_name,
        "tool_call_id": tool_result.tool_call_id,
        "content": tool_result.content,
        "is_error": bool(tool_result.is_error),
        "metadata": dict(tool_result.metadata),
    }


def deserialize_tool_result(payload: dict[str, Any]) -> ToolResult:
    return ToolResult(
        tool_name=str(payload.get("tool_name") or ""),
        tool_call_id=str(payload.get("tool_call_id") or ""),
        content=payload.get("content"),
        is_error=bool(payload.get("is_error")),
        metadata=dict(payload.get("metadata") or {}),
    )


def serialize_message(message: Message) -> dict[str, Any]:
    if isinstance(message, SystemMessage):
        return {"role": message.role, "content": message.content}
    if isinstance(message, UserMessage):
        return {"role": message.role, "content": message.content}
    if isinstance(message, AssistantMessage):
        return {
            "role": message.role,
            "content": message.content,
            "tool_calls": [serialize_tool_call(tool_call) for tool_call in message.tool_calls],
        }
    return {
        "role": message.role,
        "results": [serialize_tool_result(result) for result in message.results],
    }


def deserialize_message(payload: dict[str, Any]) -> Message:
    role = str(payload.get("role") or "").strip()
    if role == "system":
        return SystemMessage(content=str(payload.get("content") or ""))
    if role == "assistant":
        return AssistantMessage(
            content=str(payload.get("content") or ""),
            tool_calls=[
                deserialize_tool_call(item)
                for item in payload.get("tool_calls") or []
                if isinstance(item, dict)
            ],
        )
    if role == "tool":
        return ToolMessage(
            results=[
                deserialize_tool_result(item)
                for item in payload.get("results") or []
                if isinstance(item, dict)
            ]
        )
    return UserMessage(content=str(payload.get("content") or ""))

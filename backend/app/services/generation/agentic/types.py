"""Internal types for generation agentic mode.

Keep the execution core independent from any specific LLM SDK.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class ToolCall:
    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)
    tool_call_id: str = ""


@dataclass(slots=True)
class ToolResult:
    tool_name: str
    content: Any
    tool_call_id: str
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class UserMessage:
    parts: list[str | ToolResult]
    instructions: str | None = None


@dataclass(slots=True)
class AssistantMessage:
    parts: list[str | ToolCall]
    provider_name: str | None = None
    model_name: str | None = None


AgenticMessage = UserMessage | AssistantMessage


class AgenticModelClient(Protocol):
    async def complete(
        self,
        messages: Sequence[AgenticMessage],
        tools: Sequence[dict[str, Any]],
    ) -> AssistantMessage: ...

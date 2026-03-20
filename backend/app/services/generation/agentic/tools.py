"""Tool registry and dispatch helpers for generation agentic mode."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.services.generation.agentic.types import ToolCall, ToolResult

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]
ToolResponsePart = ToolResult


@dataclass(slots=True)
class ToolExecutionResult:
    """Structured tool execution outcome used by dispatch."""

    content: Any
    stop_loop: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolDispatchResult:
    """Result of dispatching one or more tool calls."""

    parts: list[ToolResponsePart] = field(default_factory=list)
    stop_loop: bool = False
    stop_reason: str | None = None


@dataclass(slots=True)
class ToolDef:
    """A generation-scoped tool definition."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler

    def to_model_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    """Thin name-to-handler registry."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def definitions(self) -> list[ToolDef]:
        return list(self._tools.values())

    def to_model_tools(self) -> list[dict[str, Any]]:
        return [tool.to_model_tool() for tool in self._tools.values()]


async def dispatch_tool_calls(
    tool_calls: Sequence[ToolCall],
    registry: ToolRegistry,
) -> ToolDispatchResult:
    """Execute tool calls and convert them back into model-consumable parts."""

    result = ToolDispatchResult()
    for call in tool_calls:
        tool = registry.get(call.tool_name)
        if tool is None:
            result.parts.append(
                ToolResult(
                    tool_name=call.tool_name,
                    content=f"Unknown tool '{call.tool_name}'. Choose one of the registered tools instead.",
                    tool_call_id=call.tool_call_id,
                    is_error=True,
                )
            )
            continue

        try:
            output = await tool.handler(call.args)
        except Exception as exc:
            result.parts.append(
                ToolResult(
                    tool_name=call.tool_name,
                    content=f"Tool '{call.tool_name}' failed: {type(exc).__name__}: {exc}",
                    tool_call_id=call.tool_call_id,
                    is_error=True,
                )
            )
            continue

        metadata: dict[str, Any] | None = None
        content = output
        if isinstance(output, ToolExecutionResult):
            content = output.content
            metadata = dict(output.metadata)
            if output.stop_loop:
                result.stop_loop = True
                result.stop_reason = str(output.metadata.get("stop_reason") or result.stop_reason or "")
        elif isinstance(output, ToolResult):
            result.parts.append(output)
            continue

        result.parts.append(
            ToolResult(
                tool_name=call.tool_name,
                content=content,
                tool_call_id=call.tool_call_id,
                metadata=metadata or {},
            )
        )

    if result.stop_reason == "":
        result.stop_reason = None
    return result

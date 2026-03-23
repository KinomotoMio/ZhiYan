"""Subagent orchestration helpers for generation agentic mode."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.services.generation.agentic.loop import AgenticLoopResult, agentic_loop
from app.services.generation.agentic.tools import ToolDef, ToolRegistry, dispatch_tool_calls
from app.services.generation.agentic.types import AgenticModelClient


@dataclass(slots=True)
class SubagentSpec:
    task: str
    allowed_tool_names: Sequence[str] | None = None
    max_turns: int = 24
    system_prompt: str | None = None


def filter_registry(
    registry: ToolRegistry | None,
    allowed_tool_names: Sequence[str] | None,
) -> ToolRegistry:
    """Build a child registry limited to the allowed tool subset."""

    filtered = ToolRegistry()
    if registry is None:
        return filtered

    allowed = None if allowed_tool_names is None else set(allowed_tool_names)
    for tool in registry.definitions():
        if allowed is not None and tool.name not in allowed:
            continue
        filtered.register(tool)
    return filtered


async def run_subagent(
    task: str,
    *,
    registry: ToolRegistry | None = None,
    allowed_tool_names: Sequence[str] | None = None,
    max_turns: int = 24,
    system_prompt: str | None = None,
    model: AgenticModelClient | None = None,
) -> AgenticLoopResult:
    """Run an isolated child loop with its own empty message history."""

    child_registry = filter_registry(registry, allowed_tool_names)
    return await agentic_loop(
        user_prompt=task,
        model=model,
        instructions=system_prompt,
        tool_definitions=child_registry.to_model_tools(),
        dispatch_tools=lambda calls: dispatch_tool_calls(calls, child_registry),
        max_turns=max_turns,
    )


async def run_parallel_subagents(
    specs: Sequence[SubagentSpec],
    *,
    registry: ToolRegistry | None = None,
    model: AgenticModelClient | None = None,
) -> list[AgenticLoopResult]:
    """Run multiple isolated subagents concurrently."""

    coroutines = [
        run_subagent(
            spec.task,
            registry=registry,
            allowed_tool_names=spec.allowed_tool_names,
            max_turns=spec.max_turns,
            system_prompt=spec.system_prompt,
            model=model,
        )
        for spec in specs
    ]
    return await asyncio.gather(*coroutines)


def build_dispatch_subagent_tool(
    registry: ToolRegistry,
    *,
    model: AgenticModelClient | None = None,
) -> ToolDef:
    """Create a tool that launches an isolated child agent."""

    async def _handler(args: dict[str, Any]) -> dict[str, Any]:
        raw_task = args.get("task")
        task = str(raw_task or "").strip()
        if not task:
            raise ValueError(f"dispatch_subagent requires a non-empty 'task'; got {raw_task!r}")

        raw_tools = args.get("tools")
        if raw_tools is None:
            allowed_tool_names = None
        elif isinstance(raw_tools, list):
            allowed_tool_names = [str(name).strip() for name in raw_tools if str(name).strip()]
        else:
            raise ValueError(f"dispatch_subagent 'tools' must be an array of tool names; got {raw_tools!r}")

        raw_max_turns = args.get("max_turns", 24)
        try:
            max_turns = int(raw_max_turns)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"dispatch_subagent 'max_turns' must be an integer; got {raw_max_turns!r}"
            ) from exc

        system_prompt = str(args.get("system_prompt") or "").strip() or None
        result = await run_subagent(
            task,
            registry=registry,
            allowed_tool_names=allowed_tool_names,
            max_turns=max_turns,
            system_prompt=system_prompt,
            model=model,
        )
        return {
            "output_text": result.output_text,
            "turns": result.turns,
            "stop_reason": result.stop_reason,
            "max_turns_reached": result.max_turns_reached,
        }

    return ToolDef(
        name="dispatch_subagent",
        description=(
            "Launch an isolated child agent with its own message history and an optional limited tool subset."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The scoped child task to run in isolation.",
                },
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of tool names available to the child agent.",
                },
                "max_turns": {
                    "type": "integer",
                    "description": "Maximum turns for the child loop.",
                },
                "system_prompt": {
                    "type": "string",
                    "description": "Optional extra system prompt for the child agent.",
                },
            },
            "required": ["task"],
            "additionalProperties": False,
        },
        handler=_handler,
    )

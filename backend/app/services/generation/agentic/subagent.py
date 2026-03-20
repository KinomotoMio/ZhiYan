"""Subagent orchestration helpers for generation agentic mode."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.services.generation.agentic.loop import AgenticLoopResult, agentic_loop
from app.services.generation.agentic.tools import ToolRegistry, dispatch_tool_calls
from app.services.generation.agentic.types import AgenticMessage, AgenticModelClient, UserMessage


@dataclass(slots=True)
class SubagentSpec:
    task: str
    allowed_tool_names: Sequence[str] | None = None
    message_history: Sequence[AgenticMessage] = field(default_factory=tuple)
    max_turns: int = 24
    system_prompt: str | None = None


def _filter_registry(
    registry: ToolRegistry | None,
    allowed_tool_names: Sequence[str] | None,
) -> ToolRegistry:
    filtered = ToolRegistry()
    if registry is None:
        return filtered

    allowed = None if allowed_tool_names is None else set(allowed_tool_names)
    for tool in registry.definitions():
        if allowed is not None and tool.name not in allowed:
            continue
        filtered.register(tool)
    return filtered


def _build_child_history(
    task: str,
    message_history: Sequence[AgenticMessage] | None,
    system_prompt: str | None,
) -> list[AgenticMessage]:
    history = list(message_history or [])
    history.append(UserMessage(parts=[task], instructions=system_prompt))
    return history


async def run_subagent(
    task: str,
    *,
    registry: ToolRegistry | None = None,
    allowed_tool_names: Sequence[str] | None = None,
    message_history: Sequence[AgenticMessage] | None = None,
    max_turns: int = 24,
    system_prompt: str | None = None,
    model: AgenticModelClient | None = None,
    message_transform=None,
    loop_runner=agentic_loop,
) -> AgenticLoopResult:
    """Run an isolated subagent with its own message history and tool subset."""

    child_history = _build_child_history(task, message_history, system_prompt)
    child_registry = _filter_registry(registry, allowed_tool_names)
    return await loop_runner(
        message_history=child_history,
        model=model,
        tool_definitions=child_registry.to_model_tools(),
        dispatch_tools=lambda calls: dispatch_tool_calls(calls, child_registry),
        max_turns=max_turns,
        message_transform=message_transform,
    )


async def run_parallel_subagents(
    specs: Sequence[SubagentSpec],
    *,
    registry: ToolRegistry | None = None,
    model: AgenticModelClient | None = None,
    message_transform=None,
    loop_runner=agentic_loop,
) -> list[AgenticLoopResult]:
    """Run multiple subagents concurrently."""

    tasks = [
        run_subagent(
            spec.task,
            registry=registry,
            allowed_tool_names=spec.allowed_tool_names,
            message_history=spec.message_history,
            max_turns=spec.max_turns,
            system_prompt=spec.system_prompt,
            model=model,
            message_transform=message_transform,
            loop_runner=loop_runner,
        )
        for spec in specs
    ]
    return await asyncio.gather(*tasks)

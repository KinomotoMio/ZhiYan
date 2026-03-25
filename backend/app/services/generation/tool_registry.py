"""Generation tool registry used by the harness loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from app.models.generation import StageStatus
from app.services.pipeline.graph import PipelineState, ProgressHook, SlideHook


ToolRunner = Callable[[PipelineState, ProgressHook | None, SlideHook | None], Awaitable[None]]
TimeoutResolver = Callable[[], float]


@dataclass(frozen=True)
class GenerationTool:
    name: str
    stage: StageStatus
    description: str
    timeout_seconds: TimeoutResolver
    runner: ToolRunner


class GenerationToolRegistry:
    def __init__(self, tools: list[GenerationTool]):
        self._tools = list(tools)
        self._tool_map = {tool.name: tool for tool in self._tools}

    def list_tools(self) -> list[GenerationTool]:
        return list(self._tools)

    def get(self, tool_name: str) -> GenerationTool:
        return self._tool_map[tool_name]

    def names(self) -> list[str]:
        return [tool.name for tool in self._tools]

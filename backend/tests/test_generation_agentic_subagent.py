from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.services.generation.agentic.loop import AgenticLoopResult
from app.services.generation.agentic.subagent import SubagentSpec, run_parallel_subagents, run_subagent
from app.services.generation.agentic.tools import ToolDef, ToolRegistry
from app.services.generation.agentic.types import AgenticMessage, AssistantMessage, UserMessage


@dataclass
class CapturingLoop:
    result: AgenticLoopResult
    calls: list[dict] | None = None

    async def __call__(self, **kwargs):
        if self.calls is None:
            self.calls = []
        self.calls.append(kwargs)
        return self.result


def test_run_subagent_keeps_parent_history_isolated():
    async def _case():
        parent_history: list[AgenticMessage] = [UserMessage(parts=["parent"]), AssistantMessage(parts=["parent reply"])]
        loop = CapturingLoop(result=AgenticLoopResult(output_text="ok"))
        registry = ToolRegistry()
        registry.register(ToolDef(name="parse_document", description="parse", input_schema={}, handler=lambda *_args: None))
        registry.register(ToolDef(name="generate_outline", description="outline", input_schema={}, handler=lambda *_args: None))

        result = await run_subagent(
            "child task",
            registry=registry,
            allowed_tool_names=["generate_outline"],
            message_history=parent_history,
            max_turns=7,
            loop_runner=loop,
        )

        assert result.output_text == "ok"
        assert len(parent_history) == 2
        assert len(loop.calls) == 1
        call = loop.calls[0]
        assert call["max_turns"] == 7
        assert [tool["name"] for tool in call["tool_definitions"]] == ["generate_outline"]
        assert call["message_history"] is not parent_history
        assert len(call["message_history"]) == 3
        assert isinstance(call["message_history"][-1], UserMessage)
        assert call["message_history"][-1].parts == ["child task"]

    asyncio.run(_case())


def test_run_subagent_allows_only_explicit_tool_subset():
    async def _case():
        loop = CapturingLoop(result=AgenticLoopResult(output_text="ok"))
        registry = ToolRegistry()
        registry.register(ToolDef(name="parse_document", description="parse", input_schema={}, handler=lambda *_args: None))
        registry.register(ToolDef(name="generate_outline", description="outline", input_schema={}, handler=lambda *_args: None))
        registry.register(ToolDef(name="verify_slides", description="verify", input_schema={}, handler=lambda *_args: None))

        await run_subagent(
            "child task",
            registry=registry,
            allowed_tool_names=["parse_document", "verify_slides"],
            loop_runner=loop,
        )

        call = loop.calls[0]
        assert [tool["name"] for tool in call["tool_definitions"]] == ["parse_document", "verify_slides"]

    asyncio.run(_case())


def test_run_subagent_forwards_max_turns_and_result():
    async def _case():
        loop = CapturingLoop(result=AgenticLoopResult(output_text="done", max_turns_reached=True, stop_reason="max_turns"))

        result = await run_subagent(
            "child task",
            max_turns=3,
            loop_runner=loop,
        )

        assert result.max_turns_reached is True
        assert result.stop_reason == "max_turns"
        assert loop.calls[0]["max_turns"] == 3

    asyncio.run(_case())


def test_run_parallel_subagents_runs_concurrently():
    async def _case():
        started = 0
        ready = asyncio.Event()
        release = asyncio.Event()

        async def loop_runner(**kwargs):
            nonlocal started
            started += 1
            if started == 2:
                ready.set()
            await release.wait()
            return AgenticLoopResult(output_text=kwargs["message_history"][-1].parts[0])

        specs = [
            SubagentSpec(task="task-a"),
            SubagentSpec(task="task-b"),
        ]

        task = asyncio.create_task(run_parallel_subagents(specs, loop_runner=loop_runner))
        await asyncio.wait_for(ready.wait(), timeout=0.5)
        assert started == 2
        release.set()
        results = await asyncio.wait_for(task, timeout=0.5)

        assert [result.output_text for result in results] == ["task-a", "task-b"]

    asyncio.run(_case())

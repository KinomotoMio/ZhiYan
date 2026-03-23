from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.services.generation.agentic.subagent import (
    SubagentSpec,
    build_dispatch_subagent_tool,
    filter_registry,
    run_parallel_subagents,
    run_subagent,
)
from app.services.generation.agentic.tools import ToolDef, ToolRegistry, dispatch_tool_calls
from app.services.generation.agentic.types import AgenticMessage, AgenticModelClient, AssistantMessage, ToolCall


@dataclass
class StubModel(AgenticModelClient):
    responses: list[AssistantMessage]
    seen_messages: list[list[AgenticMessage]]
    seen_tools: list[list[dict]]

    async def complete(
        self,
        messages,
        tools,
    ) -> AssistantMessage:
        self.seen_messages.append(list(messages))
        self.seen_tools.append(list(tools))
        return self.responses.pop(0)


def _text_response(text: str) -> AssistantMessage:
    return AssistantMessage(parts=[text])


def test_filter_registry_limits_tools_to_allowed_subset():
    async def _noop(_args):
        return "ok"

    registry = ToolRegistry()
    registry.register(ToolDef(name="a", description="A", input_schema={"type": "object"}, handler=_noop))
    registry.register(ToolDef(name="b", description="B", input_schema={"type": "object"}, handler=_noop))

    filtered = filter_registry(registry, ["b"])

    assert [tool.name for tool in filtered.definitions()] == ["b"]


def test_run_subagent_uses_isolated_history_and_tool_subset():
    async def _case():
        async def _handler(_args):
            return {"status": "ok"}

        registry = ToolRegistry()
        registry.register(
            ToolDef(
                name="generate_slide",
                description="Generate slide",
                input_schema={"type": "object", "properties": {}},
                handler=_handler,
            )
        )
        registry.register(
            ToolDef(
                name="verify_slide",
                description="Verify slide",
                input_schema={"type": "object", "properties": {}},
                handler=_handler,
            )
        )

        model = StubModel(
            responses=[_text_response("child done")],
            seen_messages=[],
            seen_tools=[],
        )

        result = await run_subagent(
            "generate page 3",
            registry=registry,
            allowed_tool_names=["generate_slide"],
            system_prompt="child scope only",
            model=model,
        )

        assert result.output_text == "child done"
        first_request = model.seen_messages[0]
        assert len(first_request) == 1
        assert first_request[0].parts == ["generate page 3"]
        assert first_request[0].instructions == "child scope only"
        assert model.seen_tools[0] == [
            {
                "name": "generate_slide",
                "description": "Generate slide",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]

    asyncio.run(_case())


def test_run_parallel_subagents_returns_results_in_order():
    async def _case():
        model = StubModel(
            responses=[_text_response("first"), _text_response("second")],
            seen_messages=[],
            seen_tools=[],
        )

        results = await run_parallel_subagents(
            [
                SubagentSpec(task="task 1"),
                SubagentSpec(task="task 2"),
            ],
            registry=ToolRegistry(),
            model=model,
        )

        assert [result.output_text for result in results] == ["first", "second"]
        assert [messages[0].parts[0] for messages in model.seen_messages] == ["task 1", "task 2"]

    asyncio.run(_case())


def test_dispatch_subagent_tool_runs_child_and_returns_compact_result():
    async def _case():
        registry = ToolRegistry()
        model = StubModel(
            responses=[_text_response("subagent complete")],
            seen_messages=[],
            seen_tools=[],
        )
        registry.register(build_dispatch_subagent_tool(registry, model=model))

        result = await dispatch_tool_calls(
            [
                ToolCall(
                    tool_name="dispatch_subagent",
                    args={"task": "inspect this deck", "max_turns": 3},
                    tool_call_id="call-1",
                )
            ],
            registry,
        )

        assert result.parts[0].content == {
            "output_text": "subagent complete",
            "turns": 1,
            "stop_reason": "text",
            "max_turns_reached": False,
        }
        assert model.seen_messages[0][0].parts == ["inspect this deck"]

    asyncio.run(_case())


def test_dispatch_subagent_tool_reports_raw_task_in_validation_error():
    async def _case():
        registry = ToolRegistry()
        registry.register(build_dispatch_subagent_tool(registry, model=StubModel(responses=[], seen_messages=[], seen_tools=[])))

        result = await dispatch_tool_calls(
            [
                ToolCall(
                    tool_name="dispatch_subagent",
                    args={"task": "   "},
                    tool_call_id="call-1",
                )
            ],
            registry,
        )

        assert result.parts[0].is_error is True
        assert "got '   '" in str(result.parts[0].content)

    asyncio.run(_case())


def test_dispatch_subagent_tool_reports_raw_tools_in_validation_error():
    async def _case():
        registry = ToolRegistry()
        registry.register(build_dispatch_subagent_tool(registry, model=StubModel(responses=[], seen_messages=[], seen_tools=[])))

        result = await dispatch_tool_calls(
            [
                ToolCall(
                    tool_name="dispatch_subagent",
                    args={"task": "inspect this deck", "tools": "generate_slide"},
                    tool_call_id="call-1",
                )
            ],
            registry,
        )

        assert result.parts[0].is_error is True
        assert "got 'generate_slide'" in str(result.parts[0].content)

    asyncio.run(_case())


def test_dispatch_subagent_tool_reports_raw_max_turns_in_validation_error():
    async def _case():
        registry = ToolRegistry()
        registry.register(build_dispatch_subagent_tool(registry, model=StubModel(responses=[], seen_messages=[], seen_tools=[])))

        result = await dispatch_tool_calls(
            [
                ToolCall(
                    tool_name="dispatch_subagent",
                    args={"task": "inspect this deck", "max_turns": "three"},
                    tool_call_id="call-1",
                )
            ],
            registry,
        )

        assert result.parts[0].is_error is True
        assert "got 'three'" in str(result.parts[0].content)

    asyncio.run(_case())

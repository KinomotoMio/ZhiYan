from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.services.generation.agentic.loop import agentic_loop
from app.services.generation.agentic.types import (
    AgenticMessage,
    AgenticModelClient,
    AssistantMessage,
    ToolCall,
    ToolResult,
    UserMessage,
)


@dataclass
class StubModel(AgenticModelClient):
    responses: list[AssistantMessage]

    async def complete(
        self,
        messages: list[AgenticMessage],
        tools,
    ) -> AssistantMessage:
        assert isinstance(messages[-1], UserMessage | AssistantMessage)
        return self.responses.pop(0)


def _text_response(text: str) -> AssistantMessage:
    return AssistantMessage(parts=[text])


def test_agentic_loop_returns_text_without_tools():
    async def _case():
        result = await agentic_loop(
            "hello",
            model=StubModel(responses=[_text_response("world")]),
            max_turns=2,
        )
        assert result.output_text == "world"
        assert result.turns == 1
        assert result.max_turns_reached is False

    asyncio.run(_case())


def test_agentic_loop_dispatches_tool_calls_and_accumulates_messages():
    async def _case():
        calls: list[str] = []

        async def _dispatch(parts):
            calls.extend(part.tool_name for part in parts)
            return [
                ToolResult(
                    tool_name="parse_document",
                    content={"status": "ok"},
                    tool_call_id=parts[0].tool_call_id,
                )
            ]

        model = StubModel(
            responses=[
                AssistantMessage(parts=[ToolCall(tool_name="parse_document", args={}, tool_call_id="call-1")]),
                _text_response("done"),
            ]
        )
        result = await agentic_loop(
            "generate",
            model=model,
            dispatch_tools=_dispatch,
            max_turns=3,
        )
        assert calls == ["parse_document"]
        assert result.output_text == "done"
        assert len(result.messages) == 4

    asyncio.run(_case())


def test_agentic_loop_stops_after_max_turns():
    async def _case():
        async def _dispatch(parts):
            return [
                ToolResult(
                    tool_name=parts[0].tool_name,
                    content="ok",
                    tool_call_id=parts[0].tool_call_id,
                )
            ]

        model = StubModel(
            responses=[
                AssistantMessage(parts=[ToolCall(tool_name="parse_document", args={}, tool_call_id="call-1")]),
                _text_response("summary"),
            ]
        )
        result = await agentic_loop(
            "generate",
            model=model,
            dispatch_tools=_dispatch,
            max_turns=1,
        )
        assert result.max_turns_reached is True
        assert result.stop_reason == "max-turns"
        assert result.output_text == "summary"

    asyncio.run(_case())

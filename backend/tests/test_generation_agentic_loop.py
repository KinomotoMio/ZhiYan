from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.services.generation.agentic.loop import agentic_loop
from app.services.generation.agentic.todo import TodoManager
from app.services.generation.agentic.tools import ToolDispatchResult
from app.services.generation.agentic.types import AgenticMessage, AgenticModelClient, AssistantMessage, ToolCall, ToolResult, UserMessage
from app.services.pipeline.graph import PipelineState


@dataclass
class StubModel(AgenticModelClient):
    responses: list[AssistantMessage]
    seen_messages: list[list[AgenticMessage]] | None = None

    async def complete(
        self,
        messages: list[AgenticMessage],
        tools,
    ) -> AssistantMessage:
        if self.seen_messages is not None:
            self.seen_messages.append(list(messages))
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
            return ToolDispatchResult(
                parts=[
                    ToolResult(
                        tool_name="parse_document",
                        content={"status": "ok"},
                        tool_call_id=parts[0].tool_call_id,
                    )
                ]
            )

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
            return ToolDispatchResult(
                parts=[
                    ToolResult(
                        tool_name=parts[0].tool_name,
                        content="ok",
                        tool_call_id=parts[0].tool_call_id,
                    )
                ]
            )

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


def test_agentic_loop_attaches_state_summary_and_compacts_history():
    async def _case():
        async def _dispatch(parts):
            return ToolDispatchResult(
                parts=[
                    ToolResult(
                        tool_name=parts[0].tool_name,
                        content={"status": "ok"},
                        tool_call_id=parts[0].tool_call_id,
                    )
                ]
            )

        state = PipelineState(outline={"items": [{"slide_number": 1, "title": "问题定义"}]})
        model = StubModel(
            responses=[
                AssistantMessage(parts=[ToolCall(tool_name="generate_outline", args={}, tool_call_id="call-1")]),
                _text_response("done"),
            ]
        )
        result = await agentic_loop(
            "generate",
            model=model,
            state=state,
            dispatch_tools=_dispatch,
            skill_summaries="## Available Skills\n\n- ppt-health-check: Review slides",
            harness_config={"quality_level": "strict"},
            max_turns=3,
            compact_every_turns=1,
            compact_max_tokens=1,
            compact_keep_recent=1,
        )

        assert result.output_text == "done"
        assert len(result.messages) == 3
        summary_message = result.messages[0]
        assert isinstance(summary_message, UserMessage)
        assert "Condensed earlier context:" in summary_message.parts[0]
        assert "大纲已生成：1 页 - 问题定义" in summary_message.parts[0]
        assert result.messages[1].instructions is not None
        assert "## Available Skills" in result.messages[1].instructions
        assert "质量级别：strict" in result.messages[1].instructions
        tool_message = result.messages[1]
        assert isinstance(tool_message, UserMessage)
        tool_result = tool_message.parts[0]
        assert isinstance(tool_result, ToolResult)
        assert tool_result.content["state_summary"] == "大纲已生成：1 页 - 问题定义"
        assert tool_result.metadata["state_summary"] == "大纲已生成：1 页 - 问题定义"

    asyncio.run(_case())


def test_agentic_loop_injects_todo_nag_until_all_items_done():
    async def _case():
        seen_messages: list[list[AgenticMessage]] = []
        model = StubModel(
            responses=[
                AssistantMessage(parts=[ToolCall(tool_name="update_todo", args={}, tool_call_id="call-1")]),
                _text_response("done"),
            ],
            seen_messages=seen_messages,
        )
        todo_manager = TodoManager()

        async def _dispatch(parts):
            todo_manager.update(
                [
                    {"id": 1, "task": "解析文档", "status": "done"},
                    {"id": 2, "task": "生成大纲", "status": "done"},
                ]
            )
            return ToolDispatchResult(
                parts=[
                    ToolResult(
                        tool_name=parts[0].tool_name,
                        content=todo_manager.format(),
                        tool_call_id=parts[0].tool_call_id,
                    )
                ]
            )

        result = await agentic_loop(
            "generate",
            model=model,
            todo_manager=todo_manager,
            dispatch_tools=_dispatch,
            skill_summaries="## Available Skills\n\n- data-to-chart: Build charts",
            max_turns=3,
        )

        first_request = seen_messages[0]
        assert isinstance(first_request[-1], UserMessage)
        assert "还没有创建任务计划" in first_request[-1].parts[0]
        root_request = first_request[0]
        assert isinstance(root_request, UserMessage)
        assert root_request.instructions is not None
        assert "## Available Skills" in root_request.instructions
        second_request = seen_messages[1]
        assert all(
            not (
                isinstance(message, UserMessage)
                and any(isinstance(part, str) and "当前计划状态" in part for part in message.parts)
            )
            for message in second_request
        )
        assert result.output_text == "done"

    asyncio.run(_case())


def test_agentic_loop_injects_skill_summary_without_persisting_it():
    async def _case():
        seen_messages: list[list[AgenticMessage]] = []
        model = StubModel(
            responses=[_text_response("done")],
            seen_messages=seen_messages,
        )

        result = await agentic_loop(
            "generate",
            model=model,
            skill_summaries="## Available Skills\n\n- slidev-syntax: Slidev markdown reference",
            harness_config={"outline_style": "structural"},
            max_turns=1,
        )

        root_request = seen_messages[0][0]
        assert isinstance(root_request, UserMessage)
        assert root_request.instructions is not None
        assert "slidev-syntax" in root_request.instructions
        assert "大纲风格偏好：structural" in root_request.instructions
        assert all("slidev-syntax" not in str(part) for message in result.messages for part in message.parts)
        assert result.output_text == "done"

    asyncio.run(_case())

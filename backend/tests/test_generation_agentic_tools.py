from __future__ import annotations

import asyncio

from app.services.generation.agentic.tools import ToolDef, ToolExecutionResult, ToolRegistry, dispatch_tool_calls
from app.services.generation.agentic.types import ToolCall, ToolResult


def test_tool_registry_exports_model_tools():
    async def handler(_input):
        return {"status": "ok"}

    registry = ToolRegistry()
    registry.register(
        ToolDef(
            name="parse_document",
            description="Parse a document",
            input_schema={"type": "object", "properties": {}},
            handler=handler,
        )
    )

    model_tools = registry.to_model_tools()
    assert len(model_tools) == 1
    assert model_tools[0]["name"] == "parse_document"


def test_dispatch_tool_calls_returns_retry_for_unknown_tool():
    async def _case():
        registry = ToolRegistry()
        result = await dispatch_tool_calls([ToolCall(tool_name="missing", args={}, tool_call_id="call-1")], registry)
        assert len(result.parts) == 1
        assert isinstance(result.parts[0], ToolResult)
        assert result.parts[0].is_error is True
        assert "Unknown tool" in result.parts[0].content

    asyncio.run(_case())


def test_dispatch_tool_calls_returns_retry_for_handler_error():
    async def _case():
        async def handler(_input):
            raise RuntimeError("boom")

        registry = ToolRegistry()
        registry.register(
            ToolDef(
                name="parse_document",
                description="Parse a document",
                input_schema={"type": "object", "properties": {}},
                handler=handler,
            )
        )
        result = await dispatch_tool_calls([ToolCall(tool_name="parse_document", args={}, tool_call_id="call-1")], registry)
        assert isinstance(result.parts[0], ToolResult)
        assert result.parts[0].is_error is True
        assert "boom" in result.parts[0].content

    asyncio.run(_case())


def test_dispatch_tool_calls_bubbles_stop_loop_signal():
    async def _case():
        async def handler(_input):
            return ToolExecutionResult(content={"status": "ok"}, stop_loop=True, metadata={"stop_reason": "paused"})

        registry = ToolRegistry()
        registry.register(
            ToolDef(
                name="generate_outline",
                description="Generate outline",
                input_schema={"type": "object", "properties": {}},
                handler=handler,
            )
        )
        result = await dispatch_tool_calls([ToolCall(tool_name="generate_outline", args={}, tool_call_id="call-1")], registry)
        assert result.stop_loop is True
        assert result.stop_reason == "paused"
        assert isinstance(result.parts[0], ToolResult)

    asyncio.run(_case())

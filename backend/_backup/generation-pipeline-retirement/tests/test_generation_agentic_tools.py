from __future__ import annotations

import asyncio

from app.services.generation.agentic_legacy.tools import (
    ToolDef,
    ToolExecutionResult,
    ToolRegistry,
    dispatch_tool_calls,
)
from app.services.generation.agentic_legacy.types import ToolCall


def test_tool_registry_exports_model_tools():
    async def _handler(_args):
        return {"status": "ok"}

    registry = ToolRegistry()
    registry.register(
        ToolDef(
            name="generate_outline",
            description="Generate an outline",
            input_schema={"type": "object", "properties": {}},
            handler=_handler,
        )
    )

    tools = registry.to_model_tools()
    assert tools == [
        {
            "name": "generate_outline",
            "description": "Generate an outline",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]


def test_dispatch_tool_calls_returns_unknown_tool_error():
    async def _case():
        registry = ToolRegistry()
        result = await dispatch_tool_calls(
            [ToolCall(tool_name="missing", args={}, tool_call_id="call-1")],
            registry,
        )

        assert result.stop_loop is False
        assert result.parts[0].tool_name == "missing"
        assert result.parts[0].tool_call_id == "call-1"
        assert result.parts[0].is_error is True
        assert "Unknown tool" in str(result.parts[0].content)

    asyncio.run(_case())


def test_dispatch_tool_calls_wraps_handler_exceptions():
    async def _case():
        async def _handler(_args):
            raise RuntimeError("boom")

        registry = ToolRegistry()
        registry.register(
            ToolDef(
                name="generate_outline",
                description="Generate an outline",
                input_schema={"type": "object", "properties": {}},
                handler=_handler,
            )
        )

        result = await dispatch_tool_calls(
            [ToolCall(tool_name="generate_outline", args={}, tool_call_id="call-1")],
            registry,
        )

        assert result.parts[0].is_error is True
        assert "RuntimeError" in str(result.parts[0].content)
        assert "boom" in str(result.parts[0].content)

    asyncio.run(_case())


def test_dispatch_tool_calls_preserves_tool_result_and_stop_signal():
    async def _case():
        async def _handler(_args):
            return ToolExecutionResult(
                content={"stage": "outline"},
                stop_loop=True,
                metadata={"stop_reason": "waiting-outline-review"},
            )

        registry = ToolRegistry()
        registry.register(
            ToolDef(
                name="generate_outline",
                description="Generate an outline",
                input_schema={"type": "object", "properties": {}},
                handler=_handler,
            )
        )

        result = await dispatch_tool_calls(
            [ToolCall(tool_name="generate_outline", args={}, tool_call_id="call-1")],
            registry,
        )

        assert result.stop_loop is True
        assert result.stop_reason == "waiting-outline-review"
        assert result.parts[0].content == {"stage": "outline"}
        assert result.parts[0].metadata == {"stop_reason": "waiting-outline-review"}

    asyncio.run(_case())


def test_dispatch_tool_calls_keeps_first_stop_reason():
    async def _case():
        async def _first_handler(_args):
            return ToolExecutionResult(
                content={"stage": "outline"},
                stop_loop=True,
                metadata={"stop_reason": "waiting-outline-review"},
            )

        async def _second_handler(_args):
            return ToolExecutionResult(
                content={"stage": "verify"},
                stop_loop=True,
                metadata={"stop_reason": "waiting-fix-review"},
            )

        registry = ToolRegistry()
        registry.register(
            ToolDef(
                name="generate_outline",
                description="Generate an outline",
                input_schema={"type": "object", "properties": {}},
                handler=_first_handler,
            )
        )
        registry.register(
            ToolDef(
                name="verify_slides",
                description="Verify slides",
                input_schema={"type": "object", "properties": {}},
                handler=_second_handler,
            )
        )

        result = await dispatch_tool_calls(
            [
                ToolCall(tool_name="generate_outline", args={}, tool_call_id="call-1"),
                ToolCall(tool_name="verify_slides", args={}, tool_call_id="call-2"),
            ],
            registry,
        )

        assert result.stop_loop is True
        assert result.stop_reason == "waiting-outline-review"

    asyncio.run(_case())

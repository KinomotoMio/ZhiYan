from __future__ import annotations

import json

from app.services.generation.agentic.models import _expand_litellm_message
from app.services.generation.agentic.types import AssistantMessage, ToolCall, ToolMessage, ToolResult


def test_multi_tool_message_expands_to_multiple_tool_messages() -> None:
    message = ToolMessage(
        results=[
            ToolResult(
                tool_name="read_file",
                tool_call_id="call-1",
                content={"path": "/tmp/note.txt", "content": "hello"},
                metadata={"debug": "hidden"},
            ),
            ToolResult(
                tool_name="todo",
                tool_call_id="call-2",
                content={"summary": "Current plan:\n- item"},
                metadata={"trace": "hidden"},
            ),
        ]
    )

    payload = _expand_litellm_message(message)

    assert len(payload) == 2
    assert payload[0]["role"] == "tool"
    assert payload[0]["tool_call_id"] == "call-1"
    assert json.loads(payload[0]["content"])["path"] == "/tmp/note.txt"
    assert payload[1]["role"] == "tool"
    assert payload[1]["tool_call_id"] == "call-2"
    assert "Current plan" in json.loads(payload[1]["content"])["summary"]


def test_assistant_tool_call_message_uses_null_content() -> None:
    payload = _expand_litellm_message(
        AssistantMessage(
            tool_calls=[ToolCall(tool_name="read_file", args={"path": "note.txt"}, tool_call_id="call-1")]
        )
    )

    assert payload == [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": "{\"path\": \"note.txt\"}",
                    },
                }
            ],
        }
    ]

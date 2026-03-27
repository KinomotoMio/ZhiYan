from __future__ import annotations

import json

from app.services.generation.agentic.models import _to_litellm_message
from app.services.generation.agentic.types import ToolMessage, ToolResult


def test_multi_tool_message_omits_protocol_metadata_from_model_content() -> None:
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

    payload = _to_litellm_message(message)
    content = json.loads(payload["content"])

    assert payload["role"] == "user"
    assert content[0]["tool_name"] == "read_file"
    assert "tool_call_id" not in content[0]
    assert "metadata" not in content[0]
    assert "tool_call_id" not in content[1]
    assert "metadata" not in content[1]

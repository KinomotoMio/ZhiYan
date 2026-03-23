"""Generation-scoped agentic primitives."""

from app.services.generation.agentic.context import (
    attach_state_summary,
    compact_context,
    estimate_message_tokens,
    summarize_state,
)
from app.services.generation.agentic.loop import AgenticLoopResult, agentic_loop
from app.services.generation.agentic.todo import TodoItem, TodoManager, build_todo_nag, build_update_todo_tool
from app.services.generation.agentic.tools import ToolDef, ToolDispatchResult, ToolExecutionResult, ToolRegistry, dispatch_tool_calls
from app.services.generation.agentic.types import (
    AgenticMessage,
    AssistantMessage,
    ToolCall,
    ToolResult,
    UserMessage,
)

__all__ = [
    "AgenticLoopResult",
    "AgenticMessage",
    "AssistantMessage",
    "ToolCall",
    "ToolDef",
    "attach_state_summary",
    "compact_context",
    "estimate_message_tokens",
    "summarize_state",
    "TodoItem",
    "TodoManager",
    "ToolDispatchResult",
    "ToolExecutionResult",
    "ToolRegistry",
    "ToolResult",
    "UserMessage",
    "agentic_loop",
    "build_todo_nag",
    "build_update_todo_tool",
    "dispatch_tool_calls",
]

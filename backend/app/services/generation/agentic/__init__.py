"""Agentic generation helpers."""

from app.services.generation.agentic.context import compact_context, summarize_state
from app.services.generation.agentic.loop import AgenticLoopResult, agentic_loop, build_model
from app.services.generation.agentic.prompt import build_system_prompt, load_harness_config
from app.services.generation.agentic.skills import (
    build_load_skill_tool_definition,
    build_run_skill_tool_definition,
    build_skill_summaries,
    execute_skill_script,
    load_skill_markdown,
)
from app.services.generation.agentic.subagent import SubagentSpec, run_parallel_subagents, run_subagent
from app.services.generation.agentic.todo import (
    TodoItem,
    TodoManager,
    build_todo_nag,
    build_update_todo_tool_definition,
    update_todo,
)
from app.services.generation.agentic.types import AgenticMessage, AssistantMessage, ToolCall, ToolResult, UserMessage
from app.services.generation.agentic.tools import (
    ToolDef,
    ToolDispatchResult,
    ToolExecutionResult,
    ToolRegistry,
    dispatch_tool_calls,
)

__all__ = [
    "AgenticLoopResult",
    "AgenticMessage",
    "AssistantMessage",
    "ToolDef",
    "ToolCall",
    "TodoItem",
    "TodoManager",
    "ToolDispatchResult",
    "ToolExecutionResult",
    "ToolRegistry",
    "ToolResult",
    "UserMessage",
    "agentic_loop",
    "build_system_prompt",
    "build_model",
    "build_load_skill_tool_definition",
    "build_run_skill_tool_definition",
    "build_skill_summaries",
    "build_todo_nag",
    "build_update_todo_tool_definition",
    "compact_context",
    "dispatch_tool_calls",
    "execute_skill_script",
    "load_harness_config",
    "load_skill_markdown",
    "run_parallel_subagents",
    "run_subagent",
    "SubagentSpec",
    "summarize_state",
    "update_todo",
]

"""Generation-scoped agentic primitives."""

from app.services.generation.agentic.context import (
    attach_state_summary,
    compact_context,
    estimate_message_tokens,
    summarize_state,
)
from app.services.generation.agentic.loop import AgenticLoopResult, agentic_loop
from app.services.generation.agentic.prompt import (
    build_error_recovery_section,
    build_identity_section,
    build_quality_gates_section,
    build_system_prompt,
    build_task_section,
    build_tool_rules_section,
    load_harness_config,
)
from app.services.generation.agentic.skills import build_load_skill_tool, build_run_skill_tool, build_skill_summaries
from app.services.generation.agentic.subagent import (
    SubagentSpec,
    build_dispatch_subagent_tool,
    filter_registry,
    run_parallel_subagents,
    run_subagent,
)
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
    "SubagentSpec",
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
    "build_dispatch_subagent_tool",
    "build_todo_nag",
    "build_update_todo_tool",
    "build_load_skill_tool",
    "build_error_recovery_section",
    "build_identity_section",
    "build_quality_gates_section",
    "build_run_skill_tool",
    "build_skill_summaries",
    "build_system_prompt",
    "build_task_section",
    "build_tool_rules_section",
    "dispatch_tool_calls",
    "filter_registry",
    "load_harness_config",
    "run_parallel_subagents",
    "run_subagent",
]

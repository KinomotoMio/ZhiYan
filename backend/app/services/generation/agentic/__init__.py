"""Project-native embedded agent runtime."""

from app.services.generation.agentic.agent import Agent, AgentResult, AgentSession, CompactResult
from app.services.generation.agentic.background import BackgroundManager
from app.services.generation.agentic.builder import AgentBuilder
from app.services.generation.agentic.context_policy import ContextPolicy, ContextRetentionClass
from app.services.generation.agentic.mcp import MCPConfig, MCPConfigLoader
from app.services.generation.agentic.models import LiteLLMModelClient, ModelClient, ModelResponse, ModelUsage
from app.services.generation.agentic.skills import SkillCatalog, SkillDiscovery
from app.services.generation.agentic.subagents import SubagentManager
from app.services.generation.agentic.tasks import TaskIndex, TaskManager, TaskRecord, TaskStatus
from app.services.generation.agentic.todo import TodoItem, TodoManager
from app.services.generation.agentic.tools import (
    Tool,
    ToolContext,
    ToolRegistry,
    create_builtin_registry,
    default_tool_context,
    tool,
)
from app.services.generation.agentic.types import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolCall,
    ToolMessage,
    ToolResult,
    UserMessage,
)

__all__ = [
    "Agent",
    "AgentBuilder",
    "AgentResult",
    "AgentSession",
    "AssistantMessage",
    "BackgroundManager",
    "CompactResult",
    "ContextPolicy",
    "ContextRetentionClass",
    "LiteLLMModelClient",
    "MCPConfig",
    "MCPConfigLoader",
    "Message",
    "ModelClient",
    "ModelResponse",
    "ModelUsage",
    "SkillCatalog",
    "SkillDiscovery",
    "SubagentManager",
    "SystemMessage",
    "TaskIndex",
    "TaskManager",
    "TaskRecord",
    "TaskStatus",
    "TodoItem",
    "TodoManager",
    "Tool",
    "ToolCall",
    "ToolContext",
    "ToolMessage",
    "ToolRegistry",
    "ToolResult",
    "UserMessage",
    "create_builtin_registry",
    "default_tool_context",
    "tool",
]

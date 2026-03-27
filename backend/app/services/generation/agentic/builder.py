from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agent import Agent
from .mcp import LoadedMCPConfig, MCPConfigLoader
from .models import LiteLLMModelClient, ModelClient
from .skills import SkillCatalog, SkillDiscovery
from .tasks import TaskManager
from .tools import Tool, ToolHandler, ToolRegistry, create_builtin_registry, default_tool_context


DEFAULT_SYSTEM_PROMPT = """You are a helpful single-agent runtime.
Use tools when they are necessary and available.
When a relevant skill is available, use the load_skill tool before applying it.
Delegate bounded clean-context subtasks with subagent_run when helpful.
Use background_run or background_subagent for slow work you can monitor later.
Prefer concise, direct answers after tool results are available."""


@dataclass(slots=True)
class AgentBuilder:
    project_root: Path
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_turns: int = 8
    permissive_tools: bool = False
    auto_compact_enabled: bool = True
    compact_token_threshold: int = 6000
    compact_tail_turns: int = 2
    model_client: ModelClient | None = None
    tool_registry: ToolRegistry | None = None
    skill_catalog: SkillCatalog | None = None
    loaded_mcp_config: LoadedMCPConfig | None = None
    tool_definitions: list[Tool | ToolHandler] = field(default_factory=list)

    @classmethod
    def from_project(cls, project_root: str | Path) -> "AgentBuilder":
        return cls(project_root=Path(project_root).resolve())

    def with_model_client(self, client: ModelClient) -> "AgentBuilder":
        self.model_client = client
        return self

    def with_litellm(
        self,
        *,
        model: str,
        temperature: float | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        **extra_kwargs: Any,
    ) -> "AgentBuilder":
        self.model_client = LiteLLMModelClient(
            model=model,
            temperature=temperature,
            api_base=api_base,
            api_key=api_key,
            extra_kwargs=extra_kwargs,
        )
        return self

    def with_system_prompt(self, prompt: str) -> "AgentBuilder":
        self.system_prompt = prompt
        return self

    def with_max_turns(self, max_turns: int) -> "AgentBuilder":
        self.max_turns = max_turns
        return self

    def with_permissive_tools(self, enabled: bool = True) -> "AgentBuilder":
        self.permissive_tools = enabled
        return self

    def with_auto_compact(self, enabled: bool = True) -> "AgentBuilder":
        self.auto_compact_enabled = enabled
        return self

    def with_compact_token_threshold(self, threshold: int) -> "AgentBuilder":
        self.compact_token_threshold = threshold
        return self

    def with_compact_tail_turns(self, turns: int) -> "AgentBuilder":
        self.compact_tail_turns = turns
        return self

    def register_tool(self, tool_definition: Tool | ToolHandler) -> "AgentBuilder":
        self.tool_definitions.append(tool_definition)
        return self

    def discover_skills(self) -> "AgentBuilder":
        self.skill_catalog = SkillDiscovery(self.project_root).discover()
        return self

    def load_mcp_config(self) -> "AgentBuilder":
        self.loaded_mcp_config = MCPConfigLoader(self.project_root).load()
        return self

    def build(self) -> Agent:
        if self.model_client is None:
            raise ValueError("Model client is required. Use with_model_client() or with_litellm().")
        registry = self.tool_registry or create_builtin_registry(
            workspace_root=self.project_root,
            permissive_mode=self.permissive_tools,
        )
        registry.extend(self.tool_definitions)
        skills = self.skill_catalog or SkillDiscovery(self.project_root).discover()
        if self.loaded_mcp_config is None:
            self.loaded_mcp_config = MCPConfigLoader(self.project_root).load()
        task_manager = TaskManager.from_project(self.project_root, create_if_missing=True)
        return Agent(
            model=self.model_client,
            tool_registry=registry,
            tool_context=default_tool_context(self.project_root, self.permissive_tools),
            skill_catalog=skills,
            task_manager=task_manager,
            system_prompt=self.system_prompt,
            max_turns=self.max_turns,
            auto_compact_enabled=self.auto_compact_enabled,
            compact_token_threshold=self.compact_token_threshold,
            compact_tail_turns=self.compact_tail_turns,
        )

    def inspect(self) -> dict[str, Any]:
        registry = self.tool_registry or create_builtin_registry(
            workspace_root=self.project_root,
            permissive_mode=self.permissive_tools,
        )
        registry.extend(self.tool_definitions)
        skills = self.skill_catalog or SkillDiscovery(self.project_root).discover()
        loaded_mcp = self.loaded_mcp_config or MCPConfigLoader(self.project_root).load()
        task_manager = TaskManager.from_project(self.project_root, create_if_missing=False)
        return {
            "project_root": str(self.project_root),
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "source": tool.source,
                }
                for tool in registry.tools.values()
            ],
            "skills": [
                {
                    "name": skill.name,
                    "description": skill.description,
                    "argument_hint": skill.argument_hint,
                    "location": str(skill.location),
                    "diagnostics": [diagnostic.message for diagnostic in skill.diagnostics],
                }
                for skill in skills.records.values()
            ],
            "skill_diagnostics": [diagnostic.message for diagnostic in skills.diagnostics],
            "tasks": task_manager.list_tasks(),
            "current_task_id": task_manager.current_task_id,
            "mcp": {
                "path": str(loaded_mcp.path),
                "servers": loaded_mcp.config.model_dump(mode="json")["mcpServers"],
                "diagnostics": [diagnostic.message for diagnostic in loaded_mcp.diagnostics],
            },
        }

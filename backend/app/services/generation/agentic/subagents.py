from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .skills import SkillCatalog
from .tasks import TaskManager
from .types import UserMessage


SUBAGENT_SYSTEM_PROMPT = """You are a focused subagent.
Work only on the delegated subtask.
Keep your context clean and do not speculate beyond the delegated scope.
Return concise, high-signal results for the parent agent."""


@dataclass(slots=True)
class SubagentManager:
    model: Any
    tool_registry: Any
    tool_context: Any
    skill_catalog: SkillCatalog
    task_manager: TaskManager
    max_turns: int = 4
    default_tool_mode: str = "none"

    async def run(
        self,
        *,
        task: str,
        context: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int | None = None,
    ) -> dict[str, Any]:
        from .agent import AgentSession

        registry = self._build_registry(allowed_tools)
        session = AgentSession(
            model=self.model,
            tool_registry=registry,
            tool_context=self.tool_context,
            skill_catalog=self.skill_catalog,
            task_manager=self.task_manager,
            system_prompt=SUBAGENT_SYSTEM_PROMPT,
            max_turns=max_turns or self.max_turns,
            auto_compact_enabled=False,
        )
        result = await session._continue_loop(
            nag_enabled=False,
            ephemeral_messages=[UserMessage(content=self._build_prompt(task=task, context=context))],
        )
        return {
            "task": task,
            "allowed_tools": list(allowed_tools or []),
            "output_text": result.output_text,
            "stop_reason": result.stop_reason,
            "turns": result.turns,
            "error": result.error,
            "tool_results": [
                {
                    "tool_name": tool_result.tool_name,
                    "content": tool_result.content,
                    "is_error": tool_result.is_error,
                }
                for tool_result in result.tool_results
            ],
        }

    def _build_registry(self, allowed_tools: list[str] | None) -> Any:
        from .tools import ToolRegistry

        registry = ToolRegistry()
        if allowed_tools is not None:
            registry.extend(
                [tool for name, tool in self.tool_registry.tools.items() if name in set(allowed_tools)]
            )
            return registry
        if self.default_tool_mode == "inherit":
            registry.extend(list(self.tool_registry.tools.values()))
        return registry

    def _build_prompt(self, *, task: str, context: str | None) -> str:
        lines = [
            "<delegated_subtask>",
            f"<task>{task}</task>",
        ]
        if context:
            lines.append(f"<context>{context}</context>")
        lines.extend(
            [
                "<execution_rule>Do the delegated subtask directly. Do not explore, inspect files, or gather extra context unless tools were explicitly provided. If the task is answerable from the prompt and context alone, answer directly.</execution_rule>",
                "</delegated_subtask>",
            ]
        )
        return "\n".join(lines)

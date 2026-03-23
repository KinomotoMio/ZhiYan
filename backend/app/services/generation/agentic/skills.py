"""Skill discovery and tool helpers for generation agentic mode."""

from __future__ import annotations

from typing import Any

from app.services.generation.agentic.tools import ToolDef
from app.services.skill_runtime.executor import execute_skill
from app.services.skill_runtime.registry import SkillRegistry


def build_skill_summaries(registry: SkillRegistry | None = None) -> str:
    """Build the layer-1 skill summary block shown to the model."""

    skill_registry = registry or SkillRegistry()
    skills = skill_registry.discover()
    if not skills:
        return ""

    lines = ["## Available Skills", ""]
    for skill in skills:
        name = str(skill.get("name") or "").strip()
        if not name:
            continue
        description = str(skill.get("description") or "无描述").strip()
        lines.append(f"- {name}: {description}")

    lines.extend(["", "Use `load_skill` to inspect a skill in detail before relying on it."])
    return "\n".join(lines)


def build_load_skill_tool(registry: SkillRegistry | None = None) -> ToolDef:
    """Create a tool that loads a skill's full SKILL.md content."""

    skill_registry = registry or SkillRegistry()

    async def _handler(args: dict[str, Any]) -> str:
        name = str(args.get("name") or "").strip()
        if not name:
            raise ValueError("load_skill requires a non-empty 'name'")

        content = skill_registry.load_skill(name)
        if content is None:
            return f"Skill '{name}' not found."
        return content

    return ToolDef(
        name="load_skill",
        description="Load the full SKILL.md content for a named skill.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The skill name to inspect.",
                }
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        handler=_handler,
    )


def build_run_skill_tool(registry: SkillRegistry | None = None) -> ToolDef:
    """Create a tool that executes a script exposed by a registered skill."""

    skill_registry = registry or SkillRegistry()

    async def _handler(args: dict[str, Any]) -> dict[str, Any] | str:
        name = str(args.get("name") or "").strip()
        if not name:
            raise ValueError("run_skill requires a non-empty 'name'")
        if skill_registry.load_skill(name) is None:
            return f"Skill '{name}' not found."

        script = str(args.get("script") or "").strip()
        if not script:
            raise ValueError("run_skill requires a non-empty 'script'")

        parameters = args.get("parameters") or {}
        if not isinstance(parameters, dict):
            raise ValueError("run_skill 'parameters' must be an object")

        slides = args.get("slides") or []
        if not isinstance(slides, list):
            raise ValueError("run_skill 'slides' must be an array")

        return await execute_skill(
            skill_name=name,
            script_name=script,
            input_data={
                "slides": slides,
                "parameters": parameters,
            },
        )

    return ToolDef(
        name="run_skill",
        description="Execute a script from a named skill after inspecting its instructions.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The skill name to execute.",
                },
                "script": {
                    "type": "string",
                    "description": "The script file inside the skill's scripts directory.",
                },
                "slides": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Optional slide payloads to pass through.",
                },
                "parameters": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "Additional JSON parameters for the script.",
                },
            },
            "required": ["name", "script"],
            "additionalProperties": False,
        },
        handler=_handler,
    )

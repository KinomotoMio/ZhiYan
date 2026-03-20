"""Skill helpers for generation agentic mode."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.skill_runtime.executor import execute_skill
from app.services.skill_runtime.registry import SkillRegistry

_SKILL_SPECS = (
    "data-to-chart",
    "ppt-health-check",
)


def build_skill_summaries(registry: SkillRegistry | None = None) -> str:
    """Build a compact summary of available skills for the system prompt."""

    skill_registry = registry or SkillRegistry()
    discovered = _filter_supported_skills(skill_registry.discover())
    if not discovered:
        return ""

    lines = ["## Available Skills"]
    for skill in discovered:
        description = _skill_description(skill)
        lines.append(f"- **{skill['name']}**: {description}")
    return "\n".join(lines)


def load_skill_markdown(skill_name: str, registry: SkillRegistry | None = None) -> str | None:
    """Load the full SKILL.md content for a supported skill."""

    if skill_name not in _SKILL_SPECS:
        return None

    skill_registry = registry or SkillRegistry()
    return skill_registry.load_skill(skill_name)


async def execute_skill_script(
    skill_name: str,
    script_name: str,
    args: Mapping[str, Any] | None = None,
    *,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Execute a named skill script with explicit args."""

    payload = dict(args or {})
    if skill_name not in _SKILL_SPECS:
        raise ValueError(f"unsupported skill: {skill_name}")

    if timeout is None:
        return await execute_skill(skill_name=skill_name, script_name=script_name, input_data=payload)
    return await execute_skill(
        skill_name=skill_name,
        script_name=script_name,
        input_data=payload,
        timeout=timeout,
    )


def build_load_skill_tool_definition() -> dict[str, Any]:
    return {
        "name": "load_skill",
        "description": "加载指定 skill 的完整 SKILL.md 内容。",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "enum": list(_SKILL_SPECS),
                    "description": "skill 名称",
                }
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    }


def build_run_skill_tool_definition() -> dict[str, Any]:
    return {
        "name": "run_skill",
        "description": "执行指定 skill 的脚本，输入必须是明确的 JSON 参数。",
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "enum": list(_SKILL_SPECS),
                    "description": "skill 名称",
                },
                "script_name": {
                    "type": "string",
                    "description": "脚本文件名，例如 check.py",
                },
                "args": {
                    "type": "object",
                    "description": "传递给脚本的 JSON 参数",
                    "additionalProperties": True,
                },
            },
            "required": ["skill_name", "script_name"],
            "additionalProperties": False,
        },
    }


def _filter_supported_skills(skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    supported: list[dict[str, Any]] = []
    for skill in skills:
        name = str(skill.get("name") or "").strip()
        if name not in _SKILL_SPECS:
            continue
        supported.append(skill)
    return supported


def _skill_description(skill: Mapping[str, Any]) -> str:
    description = str(skill.get("description") or "").strip()
    if description:
        return description
    return "无描述"

"""Skill defaults, catalog summaries, and activation helpers."""

from __future__ import annotations

from typing import Any

from app.models.generation import PresentationOutputMode
from app.services.skill_runtime.registry import SkillRegistry


DEFAULT_SKILL_BY_OUTPUT: dict[str, str] = {
    PresentationOutputMode.SLIDEV.value: "slidev-default",
    PresentationOutputMode.HTML.value: "html-default",
}


def resolve_default_skill_name(output_mode: str) -> str | None:
    normalized = str(output_mode or "").strip().lower()
    return DEFAULT_SKILL_BY_OUTPUT.get(normalized)


def resolve_skill_name(
    *,
    requested_skill: str | None,
    output_mode: str,
    registry: SkillRegistry | None = None,
) -> str | None:
    registry = registry or SkillRegistry()
    requested = str(requested_skill or "").strip()
    if requested:
        if registry.get_skill(requested) is None:
            raise ValueError(f"Skill '{requested}' 不存在")
        return requested

    default_skill = resolve_default_skill_name(output_mode)
    if default_skill and registry.get_skill(default_skill) is not None:
        return default_skill
    return None


def build_skill_catalog_context(
    *,
    output_mode: str,
    requested_skill: str | None = None,
    registry: SkillRegistry | None = None,
) -> str:
    registry = registry or SkillRegistry()
    skills = registry.discover()
    current_skill = resolve_skill_name(
        requested_skill=requested_skill,
        output_mode=output_mode,
        registry=registry,
    )
    if not skills:
        return ""

    lines = [
        "当前支持多种输出模式，并通过 skills 驱动不同的生成/编辑心智。",
        f"- 当前 output_mode: {output_mode}",
        f"- 当前基础 skill: {current_skill or '无'}",
        "- 若任务需要额外能力或专项规则，应先调用 load_skill 再继续执行。",
        "",
        "输出模式建议：",
        "- slidev: 适合 markdown-first、快速写 deck、持续改稿。",
        "- html: 适合强视觉自定义与异步渲染，但生成通常更重。",
    ]
    catalog_lines = []
    for item in skills[:12]:
        catalog_lines.append(
            f"- {item.get('name')}: {item.get('description') or ''}"
            + (f" [scope={item.get('scope')}]" if item.get("scope") else "")
            + (f" [default_for_output={item.get('default_for_output')}]" if item.get("default_for_output") else "")
        )
    if catalog_lines:
        lines.extend(["", "可用 skills 摘要：", *catalog_lines])
    return "\n".join(lines).strip()
def build_skill_activation_record(
    skill_name: str | None,
    *,
    source: str,
    reason: str,
    registry: SkillRegistry | None = None,
) -> dict[str, Any] | None:
    if not skill_name:
        return None
    registry = registry or SkillRegistry()
    meta = registry.get_skill(skill_name)
    if not meta:
        return None
    return {
        "skill_id": skill_name,
        "name": meta.get("name") or skill_name,
        "scope": meta.get("scope"),
        "path": meta.get("path"),
        "source": source,
        "reason": reason,
        "default_for_output": meta.get("default_for_output"),
        "resources": list(meta.get("resources") or []),
        "shadowed": list(meta.get("shadowed") or []),
    }


def build_skill_summary(skill_name: str | None, *, registry: SkillRegistry | None = None) -> dict[str, Any]:
    registry = registry or SkillRegistry()
    if not skill_name:
        return {
            "skill_id": None,
            "resources": [],
        }
    meta = registry.get_skill(skill_name) or {}
    return {
        "skill_id": skill_name,
        "name": meta.get("name") or skill_name,
        "description": meta.get("description") or "",
        "scope": meta.get("scope"),
        "path": meta.get("path"),
        "default_for_output": meta.get("default_for_output"),
        "allowed_tools": meta.get("allowed_tools"),
        "resources": registry.list_resource_files(skill_name),
        "shadowed": list(meta.get("shadowed") or []),
    }

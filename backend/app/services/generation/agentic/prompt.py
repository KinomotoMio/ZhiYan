"""Composable system prompt harness for generation agentic mode."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from app.core.config import settings

DEFAULT_HARNESS_PATH = settings.project_root / "harness.yaml"

_DEFAULT_CONFIG: dict[str, Any] = {
    "outline_style": "narrative",
    "density_threshold": 5,
    "quality_level": "standard",
    "max_slides": 30,
    "include_identity": True,
    "include_task": True,
    "include_tool_rules": True,
    "include_quality_gates": True,
    "include_error_recovery": True,
}


def load_harness_config(path: Path | None = None) -> dict[str, Any]:
    """Load harness config from YAML and merge it over the defaults."""

    harness_path = path or DEFAULT_HARNESS_PATH
    if not harness_path.exists():
        return dict(_DEFAULT_CONFIG)

    raw = yaml.safe_load(harness_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return dict(_DEFAULT_CONFIG)

    merged = dict(_DEFAULT_CONFIG)
    merged.update(raw)
    return merged


def build_system_prompt(
    config: Mapping[str, Any] | None = None,
    *,
    harness_path: Path | None = None,
    skills_summary: str | None = None,
    extra_instructions: str | None = None,
) -> str:
    """Build the composed system prompt from harness config and optional sections."""

    merged = load_harness_config(harness_path)
    if config:
        merged.update(dict(config))

    sections = [
        build_identity_section(merged),
        build_task_section(merged),
        build_tool_rules_section(merged),
        build_quality_gates_section(merged),
        build_error_recovery_section(merged),
    ]

    prompt_sections = [section for section in sections if section]
    cleaned_skills = (skills_summary or "").strip()
    if cleaned_skills:
        prompt_sections.append(cleaned_skills)

    cleaned_extra = (extra_instructions or "").strip()
    if cleaned_extra:
        prompt_sections.append(cleaned_extra)

    return "\n\n".join(prompt_sections)


def build_identity_section(config: Mapping[str, Any]) -> str:
    if not config.get("include_identity", True):
        return ""
    return (
        "## Identity\n"
        "- 你是 ZhiYan，一个专业的演示文稿生成 Agent。\n"
        "- 你的目标是把用户资料转换成结构清晰、质量可靠、可继续迭代的演示文稿。"
    )


def build_task_section(config: Mapping[str, Any]) -> str:
    if not config.get("include_task", True):
        return ""

    outline_style = str(config.get("outline_style") or _DEFAULT_CONFIG["outline_style"])
    max_slides = int(config.get("max_slides") or _DEFAULT_CONFIG["max_slides"])
    return (
        "## Task\n"
        "- 先理解输入材料，再规划执行顺序，然后逐步生成大纲、布局和幻灯片。\n"
        f"- 大纲风格偏好：{outline_style}。\n"
        f"- 默认把最终页数控制在 {max_slides} 页以内，除非用户明确要求更多。"
    )


def build_tool_rules_section(config: Mapping[str, Any]) -> str:
    if not config.get("include_tool_rules", True):
        return ""

    return (
        "## Tool Rules\n"
        "- 优先按 parse -> outline -> layout -> slides -> verify 的顺序推进，除非已有状态表明某一步已经完成。\n"
        "- verify 应该在产出末段执行；如果发现 hard error，先修复再继续。\n"
        "- 不要重复调用已经明确完成且没有失效信号的步骤。"
    )


def build_quality_gates_section(config: Mapping[str, Any]) -> str:
    if not config.get("include_quality_gates", True):
        return ""

    density_threshold = int(config.get("density_threshold") or _DEFAULT_CONFIG["density_threshold"])
    quality_level = str(config.get("quality_level") or _DEFAULT_CONFIG["quality_level"])
    warning_rule = "必须修复" if quality_level == "strict" else "可选修复"
    return (
        "## Quality Gates\n"
        f"- 每页信息密度：不超过 {density_threshold} 个核心要点。\n"
        f"- 质量级别：{quality_level}。\n"
        "- hard error（布局越界、关键内容缺失、明显结构错配）必须修复。\n"
        f"- soft warning（措辞微调、轻度密度问题、审美优化）{warning_rule}。"
    )


def build_error_recovery_section(config: Mapping[str, Any]) -> str:
    if not config.get("include_error_recovery", True):
        return ""

    return (
        "## Error Recovery\n"
        "- 工具返回 error 时，先判断是参数问题、状态问题还是外部依赖问题。\n"
        "- 可恢复错误优先调整参数后重试；连续多次同类失败时，总结原因并选择替代路径。\n"
        "- 不要因为单个工具失败就直接放弃整个任务。"
    )

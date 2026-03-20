"""System prompt harness for generation agentic mode."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
import tomllib

from app.core.config import settings

DEFAULT_HARNESS_PATH = settings.project_root / "backend" / "harness.toml"

_DEFAULT_SECTIONS: dict[str, list[str]] = {
    "identity": [
        "你是 ZhiYan 的生成 Agent。",
        "你的目标是把用户提供的资料转换成高质量、可执行的演示文稿。",
    ],
    "task": [
        "优先理解输入材料，再规划执行顺序，最后输出结果。",
        "如果某一步已经完成，就不要重复执行。",
    ],
    "tool_rules": [
        "只有在确实需要信息、状态或产物时才调用工具。",
        "工具返回的内容优先于推测；不确定时先澄清或继续收集信息。",
        "执行过程中保持最小上下文膨胀，只保留对后续决策有用的信息。",
    ],
    "quality": [
        "控制信息密度，避免单页承载过多要点。",
        "遇到内容缺失、结构冲突或明显质量问题时，先修复再继续。",
    ],
    "error_recovery": [
        "工具报错时先判断是输入问题、状态问题还是外部依赖问题。",
        "可恢复错误要重试，无法恢复时要总结原因并选择可行的替代路径。",
    ],
}


def load_harness_config(path: Path | None = None) -> dict[str, Any]:
    """Load harness configuration from TOML, falling back to defaults when absent."""

    harness_path = Path(path) if path is not None else DEFAULT_HARNESS_PATH
    if not harness_path.exists():
        return {}

    data = tomllib.loads(harness_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def build_system_prompt(
    harness: Mapping[str, Any] | Path | None = None,
    *,
    skills_summary: str | None = None,
) -> str:
    """Build the agent system prompt from harness config and optional skills summary."""

    config = _coerce_harness_config(harness)
    sections = [
        build_identity_section(config.get("identity")),
        build_task_section(config.get("task")),
        build_tool_rules_section(config.get("tool_rules")),
        build_quality_section(config.get("quality")),
        build_error_recovery_section(config.get("error_recovery")),
    ]

    prompt_parts = [section for section in sections if section]
    if skills_summary:
        cleaned_skills = skills_summary.strip()
        if cleaned_skills:
            prompt_parts.append(cleaned_skills)

    return "\n\n".join(prompt_parts)


def build_identity_section(section: Mapping[str, Any] | None = None) -> str:
    return _build_section("Identity", _section_lines(section, "identity"))


def build_task_section(section: Mapping[str, Any] | None = None) -> str:
    return _build_section("Task", _section_lines(section, "task"))


def build_tool_rules_section(section: Mapping[str, Any] | None = None) -> str:
    return _build_section("Tool Rules", _section_lines(section, "tool_rules"))


def build_quality_section(section: Mapping[str, Any] | None = None) -> str:
    return _build_section("Quality", _section_lines(section, "quality"))


def build_error_recovery_section(section: Mapping[str, Any] | None = None) -> str:
    return _build_section("Error Recovery", _section_lines(section, "error_recovery"))


def _coerce_harness_config(harness: Mapping[str, Any] | Path | None) -> dict[str, Any]:
    if harness is None:
        return load_harness_config()
    if isinstance(harness, Path):
        return load_harness_config(harness)
    return dict(harness)


def _section_lines(section: Mapping[str, Any] | None, key: str) -> list[str]:
    if section is None:
        return list(_DEFAULT_SECTIONS[key])

    if section.get("enabled") is False:
        return []

    text = section.get("text")
    if isinstance(text, str):
        cleaned = [line.strip() for line in text.splitlines() if line.strip()]
        if cleaned:
            return cleaned
        return []

    lines = section.get("lines")
    if isinstance(lines, Sequence) and not isinstance(lines, (str, bytes)):
        cleaned_lines = [str(line).strip() for line in lines if str(line).strip()]
        if cleaned_lines:
            return cleaned_lines
        return []

    return []


def _build_section(title: str, lines: list[str]) -> str:
    cleaned = [line.strip() for line in lines if line and line.strip()]
    if not cleaned:
        return ""
    body = "\n".join(f"- {line}" for line in cleaned)
    return f"## {title}\n{body}"

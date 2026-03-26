"""Harness configuration and prompt composition helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.skill_runtime.registry import SkillRegistry


HARNESS_ROOT = settings.project_root / "harness" / "generation"


@dataclass(frozen=True)
class PlannerHarnessConfig:
    mode: str = "llm"
    fallback_mode: str = "deterministic"
    max_iterations: int = 8


@dataclass(frozen=True)
class OutlineHarnessConfig:
    agenda_page_index: int = 2
    narrative_arc: str = "问题→分析→方案→结论"
    content_brief_range: str = "100-200字"


@dataclass(frozen=True)
class SlidevHarnessConfig:
    theme: str = "default"
    paginate: bool = True


@dataclass(frozen=True)
class PromptHarnessConfig:
    outline_extra_instruction: str = ""
    planner_extra_instruction: str = ""


@dataclass(frozen=True)
class SkillHarnessConfig:
    enabled: tuple[str, ...] = ()


@dataclass(frozen=True)
class GenerationHarnessConfig:
    planner: PlannerHarnessConfig = field(default_factory=PlannerHarnessConfig)
    outline: OutlineHarnessConfig = field(default_factory=OutlineHarnessConfig)
    slidev: SlidevHarnessConfig = field(default_factory=SlidevHarnessConfig)
    prompts: PromptHarnessConfig = field(default_factory=PromptHarnessConfig)
    skills: SkillHarnessConfig = field(default_factory=SkillHarnessConfig)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_generation_harness_config(root: Path | None = None) -> GenerationHarnessConfig:
    root = root or HARNESS_ROOT
    raw = _read_json(root / "config.json")
    planner = raw.get("planner") or {}
    outline = raw.get("outline") or {}
    slidev = raw.get("slidev") or {}
    prompts = raw.get("prompts") or {}
    skills = raw.get("skills") or {}

    return GenerationHarnessConfig(
        planner=PlannerHarnessConfig(
            mode=str(planner.get("mode") or "llm"),
            fallback_mode=str(planner.get("fallback_mode") or "deterministic"),
            max_iterations=max(1, int(planner.get("max_iterations") or 8)),
        ),
        outline=OutlineHarnessConfig(
            agenda_page_index=max(2, int(outline.get("agenda_page_index") or 2)),
            narrative_arc=str(outline.get("narrative_arc") or "问题→分析→方案→结论"),
            content_brief_range=str(outline.get("content_brief_range") or "100-200字"),
        ),
        slidev=SlidevHarnessConfig(
            theme=str(slidev.get("theme") or "default"),
            paginate=bool(slidev.get("paginate", True)),
        ),
        prompts=PromptHarnessConfig(
            outline_extra_instruction=str(prompts.get("outline_extra_instruction") or "").strip(),
            planner_extra_instruction=str(prompts.get("planner_extra_instruction") or "").strip(),
        ),
        skills=SkillHarnessConfig(
            enabled=tuple(
                str(item).strip()
                for item in (skills.get("enabled") or [])
                if str(item).strip()
            )
        ),
    )


def load_prompt_template(name: str, root: Path | None = None) -> str:
    root = root or HARNESS_ROOT
    path = root / "agents" / f"{name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def build_skill_instruction_bundle(
    skill_names: list[str] | tuple[str, ...],
    *,
    registry: SkillRegistry | None = None,
) -> str:
    registry = registry or SkillRegistry()
    parts: list[str] = []
    known = {item.get("name"): item for item in registry.discover()}
    for skill_name in skill_names:
        meta = known.get(skill_name)
        if not meta:
            continue
        desc = str(meta.get("description") or "").strip()
        if not desc:
            continue
        parts.append(f"- {skill_name}: {desc}")
    if not parts:
        return ""
    return "已启用 Skills:\n" + "\n".join(parts)


def compose_outline_instructions(
    *,
    role_contract: str,
    config: GenerationHarnessConfig | None = None,
    root: Path | None = None,
) -> str:
    config = config or load_generation_harness_config(root=root)
    template = load_prompt_template("outline_synthesizer", root=root)
    if not template:
        return ""
    skill_bundle = build_skill_instruction_bundle(config.skills.enabled)
    outline_extra = config.prompts.outline_extra_instruction
    if skill_bundle:
        outline_extra = f"{outline_extra}\n\n{skill_bundle}".strip()
    return template.format(
        role_contract=role_contract,
        agenda_page_index=config.outline.agenda_page_index,
        narrative_arc=config.outline.narrative_arc,
        content_brief_range=config.outline.content_brief_range,
        outline_extra_instruction=outline_extra,
    ).strip()


def compose_planner_instructions(config: GenerationHarnessConfig | None = None, root: Path | None = None) -> str:
    config = config or load_generation_harness_config(root=root)
    template = load_prompt_template("loop_planner", root=root)
    if not template:
        return ""
    extra = config.prompts.planner_extra_instruction
    skill_bundle = build_skill_instruction_bundle(config.skills.enabled)
    if skill_bundle:
        extra = f"{extra}\n\n{skill_bundle}".strip()
    return template.format(planner_extra_instruction=extra).strip()

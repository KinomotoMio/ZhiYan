from __future__ import annotations

from html import escape
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class SkillDiagnostic:
    level: str
    message: str


@dataclass(slots=True)
class SkillRecord:
    name: str
    description: str
    location: Path
    skill_dir: Path
    body: str
    argument_hint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    allowed_tools: str | None = None
    diagnostics: list[SkillDiagnostic] = field(default_factory=list)


@dataclass(slots=True)
class SkillCatalog:
    records: dict[str, SkillRecord] = field(default_factory=dict)
    diagnostics: list[SkillDiagnostic] = field(default_factory=list)

    def render_catalog(self) -> str:
        if not self.records:
            return ""
        lines = [
            "Available skills are listed below.",
            "When a task matches a skill, use the load_skill tool to load the full instructions before proceeding.",
            "",
            "<available_skills>",
        ]
        for skill in sorted(self.records.values(), key=lambda item: item.name):
            lines.extend(
                [
                    "  <skill>",
                    f"    <name>{skill.name}</name>",
                    f"    <description>{skill.description}</description>",
                    *(
                        [f"    <argument_hint>{escape(skill.argument_hint)}</argument_hint>"]
                        if skill.argument_hint
                        else []
                    ),
                    "  </skill>",
                ]
            )
        lines.append("</available_skills>")
        return "\n".join(lines)

    def render_skill_content(self, name: str) -> str:
        record = self.records[name]
        resource_lines = sorted(
            str(path.relative_to(record.skill_dir))
            for folder in ("scripts", "references", "assets")
            for path in (record.skill_dir / folder).rglob("*")
            if (record.skill_dir / folder).exists() and path.is_file()
        )
        lines = [
            f'<skill_content name="{record.name}">',
            record.body,
            "",
            f"Skill directory: {record.skill_dir}",
            "Relative paths in this skill are relative to the skill directory.",
        ]
        if resource_lines:
            lines.append("<skill_resources>")
            lines.extend(f"<file>{resource}</file>" for resource in resource_lines)
            lines.append("</skill_resources>")
        lines.append("</skill_content>")
        return "\n".join(lines)


@dataclass(slots=True)
class SkillDiscovery:
    project_root: Path
    relative_skill_dir: Path = Path(".agents/skills")

    def discover(self) -> SkillCatalog:
        catalog = SkillCatalog()
        skills_root = (self.project_root / self.relative_skill_dir).resolve()
        if not skills_root.exists():
            return catalog
        for skill_md in sorted(skills_root.rglob("SKILL.md")):
            record, diagnostics = parse_skill_file(skill_md)
            if record is None:
                catalog.diagnostics.extend(diagnostics)
                continue
            existing = catalog.records.get(record.name)
            if existing is not None:
                diagnostic = SkillDiagnostic(
                    level="warning",
                    message=f"Skill '{record.name}' at {record.location} shadows {existing.location}.",
                )
                record.diagnostics.append(diagnostic)
                catalog.diagnostics.append(diagnostic)
            catalog.records[record.name] = record
            catalog.diagnostics.extend(diagnostics)
        return catalog


def parse_skill_file(path: Path) -> tuple[SkillRecord | None, list[SkillDiagnostic]]:
    diagnostics: list[SkillDiagnostic] = []
    text = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)
    if frontmatter is None:
        diagnostics.append(SkillDiagnostic(level="error", message=f"Missing frontmatter in {path}."))
        return None, diagnostics
    try:
        data = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError:
        try:
            data = yaml.safe_load(_repair_frontmatter(frontmatter)) or {}
            diagnostics.append(
                SkillDiagnostic(level="warning", message=f"Recovered malformed YAML in {path}.")
            )
        except yaml.YAMLError as exc:
            diagnostics.append(SkillDiagnostic(level="error", message=f"Invalid YAML in {path}: {exc}"))
            return None, diagnostics

    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()
    argument_hint = str(data.get("argument-hint", "")).strip() or None
    if not description:
        diagnostics.append(SkillDiagnostic(level="error", message=f"Skill at {path} is missing description."))
        return None, diagnostics
    parent_name = path.parent.name
    if name != parent_name:
        diagnostics.append(
            SkillDiagnostic(
                level="warning",
                message=f"Skill name '{name}' does not match directory '{parent_name}'.",
            )
        )
    record = SkillRecord(
        name=name or parent_name,
        description=description,
        location=path.resolve(),
        skill_dir=path.parent.resolve(),
        body=body.strip(),
        argument_hint=argument_hint,
        metadata=data.get("metadata", {}) or {},
        allowed_tools=data.get("allowed-tools"),
        diagnostics=list(diagnostics),
    )
    return record, diagnostics


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    _, frontmatter, remainder = parts
    return frontmatter.strip(), remainder.strip()


def _repair_frontmatter(frontmatter: str) -> str:
    repaired_lines: list[str] = []
    for line in frontmatter.splitlines():
        if ":" in line and not line.lstrip().startswith(("-", "#")):
            key, value = line.split(":", 1)
            stripped = value.strip()
            if stripped and ": " in stripped and not stripped.startswith(("'", '"', "|", ">")):
                escaped = stripped.replace('"', '\\"')
                repaired_lines.append(f'{key}: "{escaped}"')
                continue
        repaired_lines.append(line)
    return "\n".join(repaired_lines)

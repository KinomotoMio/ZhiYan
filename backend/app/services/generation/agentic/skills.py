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
    version: str | None = None
    command: str | None = None
    allowed_tools: str | None = None
    default_for_output: str | None = None
    scope: str = "builtin"
    source_root: Path | None = None
    shadowed_records: list["SkillRecord"] = field(default_factory=list)
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
                    f"    <scope>{skill.scope}</scope>",
                    *(
                        [f"    <argument_hint>{escape(skill.argument_hint)}</argument_hint>"]
                        if skill.argument_hint
                        else []
                    ),
                    *(
                        [f"    <default_for_output>{escape(skill.default_for_output)}</default_for_output>"]
                        if skill.default_for_output
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
            f"Scope: {record.scope}",
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
    search_roots: tuple[tuple[Path, str, int], ...] = (
        (Path("skills"), "builtin", 20),
        (Path(".zhiyan/skills"), "user", 30),
        (Path(".agents/skills"), "legacy", 10),
    )

    def discover(self) -> SkillCatalog:
        catalog = SkillCatalog()
        priority_by_name: dict[str, int] = {}
        for relative_root, scope, priority in self.search_roots:
            skills_root = (self.project_root / relative_root).resolve()
            if not skills_root.exists():
                continue
            for skill_md in sorted(skills_root.rglob("SKILL.md")):
                record, diagnostics = parse_skill_file(skill_md)
                catalog.diagnostics.extend(diagnostics)
                if record is None:
                    continue
                record.scope = scope
                record.source_root = skills_root
                existing = catalog.records.get(record.name)
                existing_priority = priority_by_name.get(record.name, -1)
                if existing is None or priority > existing_priority:
                    if existing is not None:
                        record.shadowed_records = [*existing.shadowed_records, existing]
                        diagnostic = SkillDiagnostic(
                            level="warning",
                            message=(
                                f"Skill '{record.name}' at {record.location} overrides "
                                f"{existing.location}."
                            ),
                        )
                        record.diagnostics.append(diagnostic)
                        catalog.diagnostics.append(diagnostic)
                    catalog.records[record.name] = record
                    priority_by_name[record.name] = priority
                    continue
                existing.shadowed_records.append(record)
                diagnostic = SkillDiagnostic(
                    level="warning",
                    message=(
                        f"Skill '{existing.name}' at {existing.location} shadows "
                        f"{record.location}."
                    ),
                )
                existing.diagnostics.append(diagnostic)
                catalog.diagnostics.append(diagnostic)
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
        version=str(data.get("version") or "").strip() or None,
        command=str(data.get("command") or "").strip() or None,
        allowed_tools=str(data.get("allowed_tools") or data.get("allowed-tools") or "").strip() or None,
        default_for_output=str(data.get("default_for_output") or "").strip() or None,
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

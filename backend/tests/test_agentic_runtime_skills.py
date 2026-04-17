from __future__ import annotations

from pathlib import Path

from app.services.generation.agentic.skills import SkillDiscovery, parse_skill_file


def test_skill_discovery_finds_skill(tmp_path: Path, skill_file_contents: str) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "nested" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")

    catalog = SkillDiscovery(tmp_path).discover()

    assert "example-skill" in catalog.records
    assert catalog.records["example-skill"].description.startswith("Use when")
    assert catalog.records["example-skill"].argument_hint == "Optional task selector or target identifier."


def test_skill_discovery_reports_duplicate_names_across_nested_paths(tmp_path: Path, skill_file_contents: str) -> None:
    first = tmp_path / ".agents" / "skills" / "first" / "example-skill"
    second = tmp_path / ".agents" / "skills" / "second" / "example-skill"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (first / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")
    (second / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")

    catalog = SkillDiscovery(tmp_path).discover()

    assert any("shadows" in diagnostic.message for diagnostic in catalog.diagnostics)


def test_skill_parser_leniently_recovers_malformed_yaml(tmp_path: Path) -> None:
    skill_dir = tmp_path / "broken-skill"
    skill_dir.mkdir()
    path = skill_dir / "SKILL.md"
    path.write_text(
        """---
name: broken-skill
description: Use this skill when: the user asks for help
---

Body.
""",
        encoding="utf-8",
    )

    record, diagnostics = parse_skill_file(path)

    assert record is not None
    assert any(diagnostic.level == "warning" for diagnostic in diagnostics)


def test_skill_catalog_render_includes_argument_hint_when_present(tmp_path: Path, skill_file_contents: str) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "nested" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_file_contents, encoding="utf-8")

    catalog = SkillDiscovery(tmp_path).discover()
    rendered = catalog.render_catalog()

    assert "<argument_hint>Optional task selector or target identifier.</argument_hint>" in rendered


def test_skill_discovery_prefers_user_skill_over_builtin(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "skills" / "example-skill"
    builtin_dir.mkdir(parents=True)
    (builtin_dir / "SKILL.md").write_text(
        """---
name: example-skill
description: Builtin version.
default_for_output: slidev
---

Builtin body.
""",
        encoding="utf-8",
    )
    user_dir = tmp_path / ".zhiyan" / "skills" / "example-skill"
    user_dir.mkdir(parents=True)
    (user_dir / "SKILL.md").write_text(
        """---
name: example-skill
description: User override version.
default_for_output: slidev
---

User body.
""",
        encoding="utf-8",
    )

    catalog = SkillDiscovery(tmp_path).discover()

    assert catalog.records["example-skill"].scope == "user"
    assert catalog.records["example-skill"].description == "User override version."
    assert len(catalog.records["example-skill"].shadowed_records) == 1
    assert catalog.records["example-skill"].shadowed_records[0].scope == "builtin"

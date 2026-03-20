from __future__ import annotations

import asyncio

from app.services.generation.agentic.skills import (
    build_load_skill_tool_definition,
    build_run_skill_tool_definition,
    build_skill_summaries,
    execute_skill_script,
    load_skill_markdown,
)
from app.services.skill_runtime.registry import SkillRegistry


def test_build_skill_summaries_uses_only_supported_skills(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    for name, description in [
        ("data-to-chart", "chart skill"),
        ("ppt-health-check", "health skill"),
        ("ignored-skill", "nope"),
    ]:
        skill_dir = skills_dir / name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n",
            encoding="utf-8",
        )

    registry = SkillRegistry(skills_dir)
    summary = build_skill_summaries(registry)

    assert "## Available Skills" in summary
    assert "data-to-chart" in summary
    assert "ppt-health-check" in summary
    assert "ignored-skill" not in summary


def test_build_skill_summaries_returns_empty_when_none_supported(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "other").mkdir()
    (skills_dir / "other" / "SKILL.md").write_text(
        "---\nname: other\ndescription: other\n---\n",
        encoding="utf-8",
    )

    registry = SkillRegistry(skills_dir)
    assert build_skill_summaries(registry) == ""


def test_load_skill_markdown_returns_none_for_missing_or_unsupported_skill(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    registry = SkillRegistry(skills_dir)

    assert load_skill_markdown("missing", registry) is None
    assert load_skill_markdown("ignored-skill", registry) is None


def test_load_skill_markdown_loads_full_skill_doc(tmp_path):
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "data-to-chart"
    skill_dir.mkdir(parents=True)
    content = "---\nname: data-to-chart\ndescription: chart skill\n---\nfull doc\n"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    registry = SkillRegistry(skills_dir)

    loaded = load_skill_markdown("data-to-chart", registry)

    assert loaded == content


def test_execute_skill_script_delegates_to_executor(monkeypatch):
    async def _case():
        calls: list[dict] = []

        async def fake_execute_skill(*, skill_name, script_name, input_data, timeout=30):
            calls.append(
                {
                    "skill_name": skill_name,
                    "script_name": script_name,
                    "input_data": input_data,
                    "timeout": timeout,
                }
            )
            return {"status": "ok"}

        monkeypatch.setattr("app.services.generation.agentic.skills.execute_skill", fake_execute_skill)

        result = await execute_skill_script(
            "data-to-chart",
            "gen_chart.py",
            {"dataset": [1, 2, 3]},
            timeout=12,
        )

        assert result == {"status": "ok"}
        assert calls == [
            {
                "skill_name": "data-to-chart",
                "script_name": "gen_chart.py",
                "input_data": {"dataset": [1, 2, 3]},
                "timeout": 12,
            }
        ]

    asyncio.run(_case())


def test_tool_definitions_are_plain_dicts():
    load_tool = build_load_skill_tool_definition()
    run_tool = build_run_skill_tool_definition()

    assert load_tool["name"] == "load_skill"
    assert run_tool["name"] == "run_skill"
    assert load_tool["input_schema"]["properties"]["name"]["enum"] == ["data-to-chart", "ppt-health-check"]
    assert run_tool["input_schema"]["properties"]["skill_name"]["enum"] == ["data-to-chart", "ppt-health-check"]

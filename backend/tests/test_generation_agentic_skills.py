from __future__ import annotations

import asyncio

from app.core.config import settings
from app.services.generation.agentic.skills import build_load_skill_tool, build_run_skill_tool, build_skill_summaries
from app.services.generation.agentic.tools import ToolRegistry, dispatch_tool_calls
from app.services.generation.agentic.types import ToolCall
from app.services.skill_runtime.registry import SkillRegistry


def test_build_skill_summaries_lists_discovered_skills(tmp_path):
    skills_dir = tmp_path / "skills"
    (skills_dir / "alpha").mkdir(parents=True)
    (skills_dir / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: First helper\n---\n\n# Alpha\n",
        encoding="utf-8",
    )
    (skills_dir / "beta").mkdir(parents=True)
    (skills_dir / "beta" / "SKILL.md").write_text(
        "---\nname: beta\ndescription: Second helper\n---\n\n# Beta\n",
        encoding="utf-8",
    )

    summary = build_skill_summaries(SkillRegistry(skills_dir))

    assert "## Available Skills" in summary
    assert "- alpha: First helper" in summary
    assert "- beta: Second helper" in summary
    assert "Use `load_skill`" in summary


def test_load_skill_tool_returns_markdown_and_friendly_missing_message(tmp_path):
    skills_dir = tmp_path / "skills"
    (skills_dir / "alpha").mkdir(parents=True)
    (skills_dir / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: First helper\n---\n\n# Alpha\nfull content\n",
        encoding="utf-8",
    )
    tool = build_load_skill_tool(SkillRegistry(skills_dir))
    registry = ToolRegistry()
    registry.register(tool)

    async def _case():
        found = await dispatch_tool_calls(
            [ToolCall(tool_name="load_skill", args={"name": "alpha"}, tool_call_id="call-1")],
            registry,
        )
        missing = await dispatch_tool_calls(
            [ToolCall(tool_name="load_skill", args={"name": "missing"}, tool_call_id="call-2")],
            registry,
        )

        assert "# Alpha" in str(found.parts[0].content)
        assert "Skill 'missing' not found." == missing.parts[0].content

    asyncio.run(_case())


def test_run_skill_tool_executes_registered_script(tmp_path, monkeypatch):
    skills_dir = tmp_path / "skills"
    (skills_dir / "alpha" / "scripts").mkdir(parents=True)
    (skills_dir / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: First helper\n---\n\n# Alpha\n",
        encoding="utf-8",
    )
    (skills_dir / "alpha" / "scripts" / "echo.py").write_text(
        "import json, sys\npayload = json.load(sys.stdin)\njson.dump({'status': 'ok', 'echo': payload['parameters']['topic']}, sys.stdout)\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(settings, "skills_dir", skills_dir)
    tool = build_run_skill_tool(SkillRegistry(skills_dir))
    registry = ToolRegistry()
    registry.register(tool)

    async def _case():
        result = await dispatch_tool_calls(
            [
                ToolCall(
                    tool_name="run_skill",
                    args={"name": "alpha", "script": "echo.py", "parameters": {"topic": "AI"}, "slides": []},
                    tool_call_id="call-1",
                )
            ],
            registry,
        )

        assert result.parts[0].content == {"status": "ok", "echo": "AI"}

    asyncio.run(_case())


def test_run_skill_tool_validates_missing_skill(tmp_path):
    tool = build_run_skill_tool(SkillRegistry(tmp_path / "skills"))
    registry = ToolRegistry()
    registry.register(tool)

    async def _case():
        result = await dispatch_tool_calls(
            [
                ToolCall(
                    tool_name="run_skill",
                    args={"name": "missing", "script": "echo.py"},
                    tool_call_id="call-1",
                )
            ],
            registry,
        )

        assert result.parts[0].content == "Skill 'missing' not found."

    asyncio.run(_case())


def test_run_skill_tool_checks_registry_once_for_known_skill(tmp_path, monkeypatch):
    skills_dir = tmp_path / "skills"
    (skills_dir / "alpha" / "scripts").mkdir(parents=True)
    (skills_dir / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: First helper\n---\n\n# Alpha\n",
        encoding="utf-8",
    )
    (skills_dir / "alpha" / "scripts" / "echo.py").write_text(
        "import json, sys\npayload = json.load(sys.stdin)\njson.dump({'status': 'ok'}, sys.stdout)\n",
        encoding="utf-8",
    )

    class TrackingRegistry(SkillRegistry):
        def __init__(self, skills_dir):
            super().__init__(skills_dir)
            self.load_calls = 0

        def load_skill(self, skill_name: str) -> str | None:
            self.load_calls += 1
            return super().load_skill(skill_name)

    monkeypatch.setattr(settings, "skills_dir", skills_dir)
    tracking_registry = TrackingRegistry(skills_dir)
    tool = build_run_skill_tool(tracking_registry)
    registry = ToolRegistry()
    registry.register(tool)

    async def _case():
        result = await dispatch_tool_calls(
            [
                ToolCall(
                    tool_name="run_skill",
                    args={"name": "alpha", "script": "echo.py"},
                    tool_call_id="call-1",
                )
            ],
            registry,
        )

        assert result.parts[0].content == {"status": "ok"}
        assert tracking_registry.load_calls == 0

    asyncio.run(_case())

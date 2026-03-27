from __future__ import annotations

from app.services.generation.agentic.prompt import build_system_prompt, load_harness_config


def test_load_harness_config_uses_defaults_when_file_missing(tmp_path):
    config = load_harness_config(tmp_path / "missing.yaml")

    assert config["outline_style"] == "narrative"
    assert config["density_threshold"] == 5
    assert config["quality_level"] == "standard"


def test_build_system_prompt_reflects_config_and_skills(tmp_path):
    harness = tmp_path / "harness.yaml"
    harness.write_text(
        "outline_style: structural\n"
        "density_threshold: 3\n"
        "quality_level: strict\n"
        "max_slides: 20\n",
        encoding="utf-8",
    )

    prompt = build_system_prompt(
        harness_path=harness,
        skills_summary="## Available Skills\n- slidev-syntax: Slidev markdown reference",
    )

    assert "大纲风格偏好：structural" in prompt
    assert "每页信息密度：不超过 3 个核心要点" in prompt
    assert "soft warning（措辞微调、轻度密度问题、审美优化）必须修复" in prompt
    assert "默认把最终页数控制在 20 页以内" in prompt
    assert "slidev-syntax" in prompt


def test_build_system_prompt_skips_disabled_sections():
    prompt = build_system_prompt(
        {
            "include_identity": False,
            "include_error_recovery": False,
        }
    )

    assert "## Identity" not in prompt
    assert "## Error Recovery" not in prompt
    assert "## Task" in prompt

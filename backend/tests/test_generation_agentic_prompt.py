from app.services.generation.agentic.prompt import (
    build_error_recovery_section,
    build_identity_section,
    build_quality_section,
    build_system_prompt,
    build_task_section,
    build_tool_rules_section,
    load_harness_config,
)


def test_load_harness_config_returns_empty_for_missing_file(tmp_path):
    missing = tmp_path / "missing.toml"

    assert load_harness_config(missing) == {}


def test_build_system_prompt_uses_defaults_when_harness_is_missing(tmp_path):
    missing = tmp_path / "missing.toml"

    prompt = build_system_prompt(missing)

    assert "## Identity" in prompt
    assert "## Task" in prompt
    assert "## Tool Rules" in prompt
    assert "## Quality" in prompt
    assert "## Error Recovery" in prompt
    assert "ZhiYan 的生成 Agent" in prompt


def test_build_system_prompt_respects_toml_overrides(tmp_path):
    harness = tmp_path / "harness.toml"
    harness.write_text(
        """
[identity]
lines = ["你是测试助手。"]

[task]
lines = ["只做一件事。"]

[tool_rules]
lines = ["先计划，再执行。"]

[quality]
lines = ["每页只保留三个要点。"]

[error_recovery]
lines = ["失败后先总结原因。"]
""".strip(),
        encoding="utf-8",
    )

    prompt = build_system_prompt(harness)

    assert "你是测试助手。" in prompt
    assert "只做一件事。" in prompt
    assert "先计划，再执行。" in prompt
    assert "每页只保留三个要点。" in prompt
    assert "失败后先总结原因。" in prompt
    assert "ZhiYan 的生成 Agent" not in prompt


def test_build_system_prompt_skips_empty_sections():
    prompt = build_system_prompt(
        {
            "identity": {"lines": [""]},
            "task": {"lines": []},
            "tool_rules": {"enabled": False},
            "quality": {"text": "\n"},
            "error_recovery": {"lines": ["仍然保留恢复策略。"]},
        }
    )

    assert "## Identity" not in prompt
    assert "## Task" not in prompt
    assert "## Tool Rules" not in prompt
    assert "## Quality" not in prompt
    assert "## Error Recovery" in prompt
    assert "仍然保留恢复策略。" in prompt


def test_build_system_prompt_appends_skills_summary():
    prompt = build_system_prompt(skills_summary="## Available Skills\n- chart: 画图")

    assert prompt.endswith("## Available Skills\n- chart: 画图")


def test_section_builders_return_expected_defaults():
    identity = build_identity_section()
    task = build_task_section()
    tool_rules = build_tool_rules_section()
    quality = build_quality_section()
    error_recovery = build_error_recovery_section()

    assert "## Identity" in identity
    assert "## Task" in task
    assert "## Tool Rules" in tool_rules
    assert "## Quality" in quality
    assert "## Error Recovery" in error_recovery

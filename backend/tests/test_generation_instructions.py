from pathlib import Path

from app.services.generation.instructions import (
    compose_outline_instructions,
    compose_planner_instructions,
    load_generation_harness_config,
)


def test_load_generation_harness_config_reads_defaults():
    cfg = load_generation_harness_config()
    assert cfg.planner.mode == "deterministic"
    assert cfg.outline.agenda_page_index == 2
    assert "ppt-health-check" in cfg.skills.enabled


def test_compose_outline_instructions_uses_external_config(tmp_path: Path):
    root = tmp_path / "generation"
    (root / "agents").mkdir(parents=True)
    (root / "config.json").write_text(
        '{"outline":{"agenda_page_index":3,"narrative_arc":"背景→冲突→解法→结论","content_brief_range":"80-120字"},'
        '"prompts":{"outline_extra_instruction":"必须包含业务影响"}}',
        encoding="utf-8",
    )
    (root / "agents" / "outline_synthesizer.md").write_text(
        "agenda={agenda_page_index}\narc={narrative_arc}\nbrief={content_brief_range}\n{role_contract}\n{outline_extra_instruction}",
        encoding="utf-8",
    )

    text = compose_outline_instructions(role_contract="role-contract", root=root)
    assert "agenda=3" in text
    assert "arc=背景→冲突→解法→结论" in text
    assert "brief=80-120字" in text
    assert "role-contract" in text
    assert "必须包含业务影响" in text


def test_compose_planner_instructions_uses_prompt_template(tmp_path: Path):
    root = tmp_path / "generation"
    (root / "agents").mkdir(parents=True)
    (root / "config.json").write_text(
        '{"prompts":{"planner_extra_instruction":"优先减少回溯"}}',
        encoding="utf-8",
    )
    (root / "agents" / "loop_planner.md").write_text(
        "planner={planner_extra_instruction}",
        encoding="utf-8",
    )

    text = compose_planner_instructions(root=root)
    assert "优先减少回溯" in text

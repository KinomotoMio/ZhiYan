from __future__ import annotations

from pathlib import Path


def test_active_backend_code_no_longer_imports_pipeline():
    root = Path(__file__).resolve().parents[1] / "app"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "app.services.pipeline" in text:
            offenders.append(str(path))
    assert offenders == []


def test_active_backend_code_no_longer_imports_harness_or_slidev_mvp_models():
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in (root / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "app.services.harness" in text or "SlidevMvpRequest" in text or "SlidevMvpResponse" in text:
            offenders.append(str(path))
    assert offenders == []


def test_retired_v2_generation_entrypoints_are_removed():
    root = Path(__file__).resolve().parents[1] / "app" / "api" / "v2"
    assert not (root / "router.py").exists()
    assert not (root / "generation.py").exists()


def test_retired_generation_backup_tree_is_removed():
    root = Path(__file__).resolve().parents[1]
    assert not (root / "_backup" / "generation-pipeline-retirement").exists()


def test_top_level_harness_and_slidev_artifacts_are_removed():
    root = Path(__file__).resolve().parents[2]
    assert not (root / "harness").exists()
    assert not (root / "design" / "slidev-mvp").exists()
    assert not (root / "skills" / "slidev-mvp" / "SKILL.md").exists()


def test_active_agent_adapter_no_longer_exposes_deck_types():
    path = Path(__file__).resolve().parents[1] / "app" / "services" / "generation" / "agent_adapter.py"
    text = path.read_text(encoding="utf-8")
    assert "class AgentDeck" not in text
    assert "deck_to_slides" not in text
    assert "deck_to_layout_selections" not in text


def test_legacy_deck_adapter_is_removed():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "generation" / "legacy"
    assert not (root / "deck_adapter.py").exists()


def test_active_backend_code_no_longer_depends_on_top_level_harness_path():
    root = Path(__file__).resolve().parents[1] / "app"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if 'settings.project_root / "harness"' in text or "harness/generation" in text:
            offenders.append(str(path))
    assert offenders == []

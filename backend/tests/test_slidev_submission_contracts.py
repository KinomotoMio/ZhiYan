from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import settings
from app.services import slidev as slidev_mod


def _real_failure_fixture_path() -> Path:
    return settings.project_root / "data" / "agentic-runs" / "job-eb00b4c9e52c" / "artifacts" / "slides.md"


def test_real_slidev_failure_fixture_normalizes_to_five_pages() -> None:
    fixture_path = _real_failure_fixture_path()
    assert fixture_path.exists(), f"missing fixture: {fixture_path}"
    markdown = fixture_path.read_text(encoding="utf-8")

    inspection = slidev_mod.inspect_slidev_markdown_submission(markdown=markdown)
    parsed = slidev_mod.parse_slidev_markdown(markdown=markdown)

    assert inspection["raw_slide_count"] == 9
    assert inspection["normalized_slide_count"] == 5
    assert parsed["slide_count"] == 5
    assert [slide["title"] for slide in parsed["slides"]] == [
        "Prompt，不只是文字",
        "藏在提示词背后的三次转向",
        "PART 01",
        "协作者模式：沉默是金",
        "四岁小孩就会的事",
    ]


@pytest.mark.asyncio
async def test_finalize_slidev_deck_uses_normalized_page_count(monkeypatch, tmp_path: Path) -> None:
    markdown = _real_failure_fixture_path().read_text(encoding="utf-8")

    async def fake_validate_slidev_deck(**kwargs):  # noqa: ANN003
        parsed = slidev_mod.parse_slidev_markdown(markdown=str(kwargs["markdown"]))
        return {"ok": True, "issues": [], "slide_count": parsed["slide_count"]}

    async def fake_review_slidev_deck(**kwargs):  # noqa: ANN003
        parsed = slidev_mod.parse_slidev_markdown(markdown=str(kwargs["markdown"]))
        return {"issues": [], "slide_count": parsed["slide_count"]}

    async def fake_build_slidev_spa(**kwargs):  # noqa: ANN003
        out_dir = Path(kwargs["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text("<html><body>ok</body></html>", encoding="utf-8")

    monkeypatch.setattr(slidev_mod, "validate_slidev_deck", fake_validate_slidev_deck)
    monkeypatch.setattr(slidev_mod, "review_slidev_deck", fake_review_slidev_deck)
    monkeypatch.setattr(slidev_mod, "build_slidev_spa", fake_build_slidev_spa)

    finalized = await slidev_mod.finalize_slidev_deck(
        markdown=markdown,
        fallback_title="Claude Code Prompt Suggestions",
        selected_style_id="tech-launch",
        topic="Claude Code Prompt Suggestions",
        outline_items=[
            {"slide_number": 1, "title": "Prompt，不只是文字", "suggested_slide_role": "cover"},
            {"slide_number": 2, "title": "藏在提示词背后的三次转向", "suggested_slide_role": "narrative"},
            {"slide_number": 3, "title": "PART 01", "suggested_slide_role": "section-divider"},
            {"slide_number": 4, "title": "协作者模式：沉默是金", "suggested_slide_role": "narrative"},
            {"slide_number": 5, "title": "四岁小孩就会的事", "suggested_slide_role": "closing"},
        ],
        expected_pages=5,
        build_base_path="/slidev/build/",
        build_out_dir=tmp_path / "dist",
    )

    assert finalized["meta"]["slide_count"] == 5
    assert finalized["presentation"]["slides"][0]["contentData"]["title"] == "Prompt，不只是文字"

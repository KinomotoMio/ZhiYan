"""Contract tests for centi-deck submission normalization."""

from __future__ import annotations

import pytest

from app.services.centi_deck import (
    CentiDeckArtifact,
    normalize_centi_deck_submission,
    validate_module_source,
)


MINIMAL_MODULE = "export default { id: 'cover', render() { return '<section>hi</section>'; } };"


def _sample_payload(**overrides) -> dict:
    base = {
        "title": "T",
        "slides": [
            {
                "slideId": "cover",
                "title": "Cover",
                "plainText": "cover slide",
                "moduleSource": MINIMAL_MODULE,
            }
        ],
    }
    base.update(overrides)
    return base


def test_normalize_roundtrip_minimal():
    artifact, render = normalize_centi_deck_submission(
        payload=_sample_payload(),
        fallback_title="fallback",
    )
    assert artifact["version"] == "centi-deck-v1"
    assert artifact["title"] == "T"
    assert len(artifact["slides"]) == 1
    assert artifact["slides"][0]["slideId"] == "cover"
    assert artifact["slides"][0]["moduleSource"].startswith('"use strict"')
    assert render["artifactVersion"] == "centi-deck-v1"
    assert render["slideCount"] == 1
    assert render["presenterCapabilities"]["navigation"] is True
    assert render["exportCapabilities"]["pdf"] is True


def test_normalize_fallback_title_used_when_empty():
    artifact, _ = normalize_centi_deck_submission(
        payload=_sample_payload(title=""),
        fallback_title="fallback deck",
    )
    assert artifact["title"] == "fallback deck"


def test_normalize_rejects_missing_export_default():
    payload = _sample_payload()
    payload["slides"][0]["moduleSource"] = "const x = 1;"
    with pytest.raises(ValueError, match="export default"):
        normalize_centi_deck_submission(payload=payload, fallback_title="T")


def test_normalize_rejects_forbidden_fetch():
    payload = _sample_payload()
    payload["slides"][0]["moduleSource"] = (
        "export default { render() { fetch('/api'); return ''; } };"
    )
    with pytest.raises(ValueError, match="fetch"):
        normalize_centi_deck_submission(payload=payload, fallback_title="T")


def test_normalize_rejects_duplicate_slide_ids():
    payload = _sample_payload()
    payload["slides"].append({
        "slideId": "cover",
        "title": "Cover2",
        "plainText": "again",
        "moduleSource": MINIMAL_MODULE,
    })
    with pytest.raises(ValueError, match="Duplicate slideId"):
        normalize_centi_deck_submission(payload=payload, fallback_title="T")


def test_normalize_rejects_empty_plain_text():
    payload = _sample_payload()
    payload["slides"][0]["plainText"] = "   "
    with pytest.raises(ValueError, match="plain_text is empty"):
        normalize_centi_deck_submission(payload=payload, fallback_title="T")


def test_normalize_rejects_oversized_module():
    payload = _sample_payload()
    # Build a valid module that's over 64KB
    filler = "x".repeat(70000) if False else ("x" * 70000)
    payload["slides"][0]["moduleSource"] = (
        f"export default {{ plain: '{filler}' }};"
    )
    with pytest.raises(ValueError, match="exceeds"):
        normalize_centi_deck_submission(payload=payload, fallback_title="T")


def test_normalize_enforces_expected_slide_count():
    with pytest.raises(ValueError, match="slide count mismatch"):
        normalize_centi_deck_submission(
            payload=_sample_payload(),
            fallback_title="T",
            expected_slide_count=5,
        )


def test_normalize_preserves_strict_preamble_when_present():
    payload = _sample_payload()
    payload["slides"][0]["moduleSource"] = f'"use strict";\n{MINIMAL_MODULE}'
    artifact, _ = normalize_centi_deck_submission(payload=payload, fallback_title="T")
    # Should NOT double-prepend
    assert artifact["slides"][0]["moduleSource"].count('"use strict"') == 1


def test_validate_module_source_rejects_toplevel_import():
    with pytest.raises(ValueError, match="import"):
        validate_module_source(
            "import x from 'y';\nexport default {};",
            slide_id="s1",
        )


def test_artifact_round_trips_through_pydantic():
    artifact, _ = normalize_centi_deck_submission(
        payload=_sample_payload(),
        fallback_title="T",
    )
    # Should round-trip through model_validate without errors
    reparsed = CentiDeckArtifact.model_validate(artifact)
    assert reparsed.slides[0].slide_id == "cover"

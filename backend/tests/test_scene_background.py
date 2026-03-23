import json
from pathlib import Path

from app.models.slide import LayoutType, Slide
from app.services.presentations.normalizer import normalize_presentation_payload
from app.utils.scene_background import get_scene_background_rule, supports_scene_background_layout


def _wrap_slides(slides):
    return {
        "presentationId": "pres-bg",
        "title": "Scene Backgrounds",
        "slides": slides,
    }


def test_scene_background_rules_match_expected_layout_defaults():
    assert supports_scene_background_layout("intro-slide") is True
    assert supports_scene_background_layout("metrics-slide") is False
    assert get_scene_background_rule("outline-slide").preset == "outline-grid"
    assert get_scene_background_rule("outline-slide").allowed_emphasis == (
        "subtle",
        "balanced",
    )
    assert get_scene_background_rule("thank-you").emphasis == "immersive"


def test_slide_schema_layout_enum_stays_in_sync_with_backend_layout_types():
    schema_path = Path(__file__).resolve().parents[2] / "shared" / "schemas" / "slide.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    layout_enum = set(schema["$defs"]["Slide"]["properties"]["layoutType"]["enum"])

    assert layout_enum == {layout.value for layout in LayoutType}


def test_slide_model_accepts_legal_scene_background_on_eligible_layout():
    slide = Slide.model_validate(
        {
            "slideId": "slide-1",
            "layoutType": "intro-slide",
            "layoutId": "intro-slide",
            "background": {
                "kind": "scene",
                "preset": "hero-glow",
                "emphasis": "immersive",
                "colorToken": "secondary",
            },
        }
    )

    assert slide.background is not None
    assert slide.background.preset.value == "hero-glow"
    assert slide.background.emphasis.value == "immersive"
    assert slide.background.color_token.value == "secondary"


def test_slide_model_repairs_partial_and_ineligible_scene_backgrounds():
    repaired_slide = Slide.model_validate(
        {
            "slideId": "slide-2",
            "layoutType": "thank-you",
            "layoutId": "thank-you",
            "background": {
                "kind": "scene",
            },
        }
    )
    assert repaired_slide.background is not None
    assert repaired_slide.background.preset.value == "closing-wash"
    assert repaired_slide.background.emphasis.value == "immersive"
    assert repaired_slide.background.color_token.value == "primary"

    ineligible_slide = Slide.model_validate(
        {
            "slideId": "slide-3",
            "layoutType": "metrics-slide",
            "layoutId": "metrics-slide",
            "background": {
                "kind": "scene",
                "preset": "hero-glow",
                "emphasis": "immersive",
            },
        }
    )
    assert ineligible_slide.background is None


def test_normalize_presentation_payload_repairs_scene_background_contract():
    payload = _wrap_slides(
        [
            {
                "slideId": "slide-intro",
                "layoutType": "intro-slide",
                "layoutId": "intro-slide",
                "background": {
                    "kind": "scene",
                },
                "contentData": {"title": "Cover"},
            },
            {
                "slideId": "slide-outline",
                "layoutType": "outline-slide",
                "layoutId": "outline-slide",
                "background": {
                    "kind": "scene",
                    "preset": "hero-glow",
                    "emphasis": "immersive",
                    "colorToken": "neutral",
                },
                "contentData": {
                    "title": "Agenda",
                    "sections": [
                        {"title": "A"},
                        {"title": "B"},
                        {"title": "C"},
                        {"title": "D"},
                    ],
                },
            },
            {
                "slideId": "slide-metrics",
                "layoutType": "metrics-slide",
                "layoutId": "metrics-slide",
                "background": {
                    "kind": "scene",
                    "preset": "hero-glow",
                },
                "contentData": {
                    "title": "KPIs",
                    "metrics": [
                        {"value": "10", "label": "Growth"},
                        {"value": "8", "label": "Margin"},
                    ],
                },
            },
        ]
    )

    normalized, changed, report = normalize_presentation_payload(payload)
    assert changed is True
    assert "scene-background" in report["repair_types"]

    intro_background = normalized["slides"][0]["background"]
    assert intro_background == {
        "kind": "scene",
        "preset": "hero-glow",
        "emphasis": "immersive",
        "colorToken": "primary",
    }

    outline_background = normalized["slides"][1]["background"]
    assert outline_background == {
        "kind": "scene",
        "preset": "outline-grid",
        "emphasis": "balanced",
        "colorToken": "neutral",
    }

    assert "background" not in normalized["slides"][2]


def test_normalize_presentation_payload_keeps_missing_background_untouched():
    payload = _wrap_slides(
        [
            {
                "slideId": "slide-quote",
                "layoutType": "quote-slide",
                "layoutId": "quote-slide",
                "contentData": {
                    "quote": "Focus on the critical path.",
                    "author": "Ops Team",
                },
            }
        ]
    )

    normalized, changed, report = normalize_presentation_payload(payload)
    assert changed is False
    assert report["repair_types"] == []
    assert "background" not in normalized["slides"][0]

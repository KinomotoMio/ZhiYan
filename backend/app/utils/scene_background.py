"""Shared scene-background eligibility and normalization rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SceneBackgroundRule:
    preset: str
    emphasis: str
    allowed_emphasis: tuple[str, ...]


SCENE_BACKGROUND_RULES: dict[str, SceneBackgroundRule] = {
    "intro-slide": SceneBackgroundRule(
        preset="hero-glow",
        emphasis="immersive",
        allowed_emphasis=("balanced", "immersive"),
    ),
    "section-header": SceneBackgroundRule(
        preset="section-band",
        emphasis="immersive",
        allowed_emphasis=("balanced", "immersive"),
    ),
    "outline-slide": SceneBackgroundRule(
        preset="outline-grid",
        emphasis="subtle",
        allowed_emphasis=("subtle", "balanced"),
    ),
    "quote-slide": SceneBackgroundRule(
        preset="quote-focus",
        emphasis="balanced",
        allowed_emphasis=("balanced", "immersive"),
    ),
    "thank-you": SceneBackgroundRule(
        preset="closing-wash",
        emphasis="immersive",
        allowed_emphasis=("balanced", "immersive"),
    ),
}

SCENE_BACKGROUND_COLOR_TOKENS = frozenset({"primary", "secondary", "neutral"})
_EMPHASIS_ORDER = ("subtle", "balanced", "immersive")
_AUTO_SCENE_BACKGROUND_ROLES: dict[str, str] = {
    "intro-slide": "cover",
    "outline-slide": "agenda",
    "section-header": "section-divider",
    "quote-slide": "highlight",
    "thank-you": "closing",
}


class _RemoveBackground:
    pass


REMOVE_BACKGROUND = _RemoveBackground()


def get_scene_background_rule(layout_id: str | None) -> SceneBackgroundRule | None:
    if not layout_id:
        return None
    return SCENE_BACKGROUND_RULES.get(layout_id)


def supports_scene_background_layout(layout_id: str | None) -> bool:
    return get_scene_background_rule(layout_id) is not None


def build_generated_scene_background(
    layout_id: str | None,
    slide_role: str | None,
    *,
    color_token: str = "primary",
) -> dict[str, str] | None:
    if not layout_id:
        return None

    expected_role = _AUTO_SCENE_BACKGROUND_ROLES.get(layout_id)
    if expected_role is None:
        return None

    from app.services.pipeline.layout_roles import normalize_slide_role

    if normalize_slide_role(slide_role) != expected_role:
        return None

    rule = get_scene_background_rule(layout_id)
    if rule is None:
        return None

    safe_color_token = (
        color_token if color_token in SCENE_BACKGROUND_COLOR_TOKENS else "primary"
    )
    return {
        "kind": "scene",
        "preset": rule.preset,
        "emphasis": rule.emphasis,
        "colorToken": safe_color_token,
    }


def _normalize_emphasis(value: Any, rule: SceneBackgroundRule) -> str:
    if value not in _EMPHASIS_ORDER:
        return rule.emphasis
    if value in rule.allowed_emphasis:
        return str(value)

    max_allowed_index = max(_EMPHASIS_ORDER.index(item) for item in rule.allowed_emphasis)
    return _EMPHASIS_ORDER[max_allowed_index]


def normalize_scene_background(
    layout_id: str | None,
    background: Any,
) -> dict[str, str] | None | _RemoveBackground:
    rule = get_scene_background_rule(layout_id)
    if rule is None:
        return REMOVE_BACKGROUND

    if background is None:
        return None

    if not isinstance(background, dict) or background.get("kind") != "scene":
        return None

    preset = background.get("preset")
    color_token = background.get("colorToken")

    return {
        "kind": "scene",
        "preset": preset if preset == rule.preset else rule.preset,
        "emphasis": _normalize_emphasis(background.get("emphasis"), rule),
        "colorToken": (
            str(color_token)
            if color_token in SCENE_BACKGROUND_COLOR_TOKENS
            else "primary"
        ),
    }

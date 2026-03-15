from __future__ import annotations

import re
from typing import Any

BACKGROUND_COLOR = "var(--background-color,#ffffff)"
BACKGROUND_TEXT = "var(--background-text,#111827)"

_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_RGB_COLOR = re.compile(
    r"^rgba?\((?:\s*\d{1,3}%?\s*,){2}\s*\d{1,3}%?(?:\s*,\s*(?:0|1|0?\.\d+))?\s*\)$"
)
_HSL_COLOR = re.compile(
    r"^hsla?\(\s*\d{1,3}(?:deg|rad|turn)?\s*,\s*\d{1,3}%\s*,\s*\d{1,3}%(?:\s*,\s*(?:0|1|0?\.\d+))?\s*\)$"
)

_EMPHASIS_PROFILES = {
    "subtle": {"accent": 0.72, "spread": 0.92, "density": 0.88},
    "balanced": {"accent": 1.0, "spread": 1.0, "density": 1.0},
    "immersive": {"accent": 1.34, "spread": 1.18, "density": 1.12},
}


def sanitize_css_color(value: Any, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback

    color = value.strip()
    if not color:
        return fallback

    if _HEX_COLOR.match(color) or _RGB_COLOR.match(color) or _HSL_COLOR.match(color):
        return color
    return fallback


def build_theme_root_css(theme: dict[str, Any] | None) -> str:
    theme_dict = theme if isinstance(theme, dict) else {}
    primary = sanitize_css_color(theme_dict.get("primaryColor"), "#3b82f6")
    secondary = sanitize_css_color(theme_dict.get("secondaryColor"), primary)
    background = sanitize_css_color(theme_dict.get("backgroundColor"), "#ffffff")
    return (
        ":root {"
        f"--primary-color: {primary};"
        f"--secondary-color: {secondary};"
        f"--background-color: {background};"
        "--background-text: #111827;"
        "--primary-text: #ffffff;"
        "}"
    )


def _clamp_percent(value: float) -> float:
    return max(0.0, min(100.0, value))


def _mix_with_transparent(color: str, percent: float) -> str:
    return f"color-mix(in srgb, {color} {_clamp_percent(percent):.3g}%, transparent)"


def _mix_with_base(color: str, percent: float, base: str = BACKGROUND_COLOR) -> str:
    return f"color-mix(in srgb, {color} {_clamp_percent(percent):.3g}%, {base})"


def _resolve_accent_color(token: str | None) -> str:
    if token == "secondary":
        return "var(--secondary-color,var(--primary-color,#3b82f6))"
    if token == "neutral":
        return f"color-mix(in srgb, {BACKGROUND_TEXT} 20%, {BACKGROUND_COLOR})"
    return "var(--primary-color,#3b82f6)"


def _resolve_secondary_accent(token: str | None) -> str:
    if token == "secondary":
        return f"color-mix(in srgb, {BACKGROUND_TEXT} 14%, {BACKGROUND_COLOR})"
    if token == "neutral":
        return "var(--primary-color,#3b82f6)"
    return "var(--secondary-color,var(--primary-color,#3b82f6))"


def _create_layer(key: str, style: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": key,
        "style": {
            "position": "absolute",
            "inset": 0,
            "pointer-events": "none",
            **style,
        },
    }


def _hero_glow_layers(accent: str, alt_accent: str, emphasis: str) -> list[dict[str, Any]]:
    profile = _EMPHASIS_PROFILES[emphasis]
    return [
        _create_layer(
            "hero-base",
            {
                "background": (
                    f"linear-gradient(140deg, {_mix_with_base(accent, 8 * profile['density'])} 0%, "
                    f"{BACKGROUND_COLOR} 42%, {_mix_with_base(alt_accent, 12 * profile['density'])} 100%)"
                )
            },
        ),
        _create_layer(
            "hero-orb-a",
            {
                "inset": "-14%",
                "background": (
                    f"radial-gradient(circle at 18% 20%, {_mix_with_transparent(accent, 26 * profile['accent'])} 0%, "
                    f"{_mix_with_transparent(accent, 14 * profile['accent'])} 18%, transparent {56 * profile['spread']:.3g}%)"
                ),
                "transform": f"scale({1 + (profile['spread'] - 1) * 0.12:.3g})",
            },
        ),
        _create_layer(
            "hero-orb-b",
            {
                "inset": "-18%",
                "background": (
                    f"radial-gradient(circle at 82% 26%, {_mix_with_transparent(alt_accent, 18 * profile['accent'])} 0%, "
                    f"{_mix_with_transparent(alt_accent, 10 * profile['accent'])} 20%, transparent {44 * profile['spread']:.3g}%)"
                ),
            },
        ),
        _create_layer(
            "hero-beam",
            {
                "inset": "-10%",
                "background": (
                    f"linear-gradient(124deg, transparent 30%, {_mix_with_transparent(accent, 14 * profile['accent'])} 56%, "
                    f"{_mix_with_transparent(alt_accent, 12 * profile['accent'])} 66%, transparent 80%)"
                ),
                "transform": "translateX(-2%)" if emphasis == "immersive" else "translateX(0)",
            },
        ),
        _create_layer(
            "hero-safe-zone",
            {
                "background": (
                    f"radial-gradient(circle at 50% 48%, "
                    f"{_mix_with_transparent(BACKGROUND_COLOR, 78 if emphasis == 'immersive' else 86)} 0%, "
                    f"{_mix_with_transparent(BACKGROUND_COLOR, 60 if emphasis == 'immersive' else 72)} 28%, transparent 72%)"
                )
            },
        ),
    ]


def _section_band_layers(accent: str, alt_accent: str, emphasis: str) -> list[dict[str, Any]]:
    profile = _EMPHASIS_PROFILES[emphasis]
    return [
        _create_layer(
            "section-haze",
            {
                "background": (
                    f"linear-gradient(180deg, {_mix_with_base(accent, 6 * profile['density'])} 0%, "
                    f"{BACKGROUND_COLOR} 56%, {_mix_with_base(alt_accent, 10 * profile['density'])} 100%)"
                )
            },
        ),
        _create_layer(
            "section-band-major",
            {
                "inset": "auto",
                "top": f"{8 - (profile['spread'] - 1) * 10:.3g}%",
                "left": f"{-16 - (profile['spread'] - 1) * 12:.3g}%",
                "width": f"{76 + (profile['spread'] - 1) * 34:.3g}%",
                "height": f"{34 + (profile['spread'] - 1) * 34:.3g}%",
                "border-radius": "44px",
                "transform": "rotate(-10deg)",
                "background": (
                    f"linear-gradient(135deg, {_mix_with_transparent(accent, 20 * profile['accent'])} 0%, "
                    f"{_mix_with_transparent(alt_accent, 34 * profile['accent'])} 100%)"
                ),
            },
        ),
        _create_layer(
            "section-band-minor",
            {
                "inset": "auto",
                "right": f"{-18 - (profile['spread'] - 1) * 10:.3g}%",
                "bottom": f"{-10 - (profile['spread'] - 1) * 8:.3g}%",
                "width": f"{62 + (profile['spread'] - 1) * 24:.3g}%",
                "height": f"{28 + (profile['spread'] - 1) * 18:.3g}%",
                "border-radius": "36px",
                "transform": "rotate(10deg)",
                "background": (
                    f"linear-gradient(135deg, {_mix_with_transparent(alt_accent, 16 * profile['accent'])} 0%, "
                    f"{_mix_with_transparent(accent, 14 * profile['accent'])} 100%)"
                ),
            },
        ),
        _create_layer(
            "section-safe-zone",
            {
                "background": (
                    f"linear-gradient(180deg, {_mix_with_transparent(BACKGROUND_COLOR, 82)} 12%, "
                    f"{_mix_with_transparent(BACKGROUND_COLOR, 70 if emphasis == 'immersive' else 80)} 48%, "
                    f"{_mix_with_transparent(BACKGROUND_COLOR, 82)} 90%)"
                )
            },
        ),
    ]


def _outline_grid_layers(accent: str, emphasis: str) -> list[dict[str, Any]]:
    profile = _EMPHASIS_PROFILES[emphasis]
    return [
        _create_layer(
            "outline-base",
            {
                "background": (
                    f"linear-gradient(180deg, {_mix_with_base(accent, 5 * profile['density'])} 0%, {BACKGROUND_COLOR} 100%)"
                )
            },
        ),
        _create_layer(
            "outline-grid",
            {
                "opacity": 1 if emphasis == "balanced" else 0.88,
                "background-image": (
                    f"linear-gradient({_mix_with_transparent(accent, 10 * profile['accent'])} 1px, transparent 1px),"
                    f"linear-gradient(90deg, {_mix_with_transparent(accent, 8 * profile['accent'])} 1px, transparent 1px)"
                ),
                "background-size": "96px 96px, 96px 96px" if emphasis == "balanced" else "108px 108px, 108px 108px",
                "background-position": "0 18px, 18px 0",
            },
        ),
        _create_layer(
            "outline-highlight",
            {
                "inset": "-12%",
                "background": (
                    f"radial-gradient(circle at 82% 12%, {_mix_with_transparent(accent, 14 * profile['accent'])} 0%, "
                    f"transparent {44 * profile['spread']:.3g}%)"
                ),
            },
        ),
        _create_layer(
            "outline-safe-zone",
            {
                "background": (
                    f"linear-gradient(180deg, {_mix_with_transparent(BACKGROUND_COLOR, 94)} 0%, "
                    f"{_mix_with_transparent(BACKGROUND_COLOR, 88)} 100%)"
                )
            },
        ),
    ]


def _quote_focus_layers(accent: str, alt_accent: str, emphasis: str) -> list[dict[str, Any]]:
    profile = _EMPHASIS_PROFILES[emphasis]
    return [
        _create_layer(
            "quote-base",
            {
                "background": (
                    f"linear-gradient(180deg, {_mix_with_base(accent, 6 * profile['density'])} 0%, {BACKGROUND_COLOR} 100%)"
                )
            },
        ),
        _create_layer(
            "quote-halo",
            {
                "inset": "-16%",
                "background": (
                    f"radial-gradient(circle at 50% 42%, {_mix_with_transparent(accent, 22 * profile['accent'])} 0%, "
                    f"{_mix_with_transparent(accent, 12 * profile['accent'])} 22%, transparent {48 * profile['spread']:.3g}%)"
                ),
            },
        ),
        _create_layer(
            "quote-pulse",
            {
                "inset": "-8%",
                "background": (
                    f"radial-gradient(circle at 26% 24%, {_mix_with_transparent(alt_accent, 14 * profile['accent'])} 0%, "
                    f"transparent {34 * profile['spread']:.3g}%)"
                ),
            },
        ),
        _create_layer(
            "quote-safe-zone",
            {
                "background": (
                    f"radial-gradient(circle at 50% 48%, "
                    f"{_mix_with_transparent(BACKGROUND_COLOR, 86 if emphasis == 'immersive' else 92)} 0%, "
                    f"{_mix_with_transparent(BACKGROUND_COLOR, 70 if emphasis == 'immersive' else 80)} 34%, transparent 76%)"
                )
            },
        ),
    ]


def _closing_wash_layers(accent: str, alt_accent: str, emphasis: str) -> list[dict[str, Any]]:
    profile = _EMPHASIS_PROFILES[emphasis]
    return [
        _create_layer(
            "closing-base",
            {
                "background": (
                    f"linear-gradient(180deg, {_mix_with_base(alt_accent, 6 * profile['density'])} 0%, "
                    f"{BACKGROUND_COLOR} 44%, {_mix_with_base(accent, 10 * profile['density'])} 100%)"
                )
            },
        ),
        _create_layer(
            "closing-wash-top",
            {
                "inset": "-20%",
                "background": (
                    f"radial-gradient(circle at 84% 16%, {_mix_with_transparent(accent, 24 * profile['accent'])} 0%, "
                    f"{_mix_with_transparent(accent, 14 * profile['accent'])} 20%, transparent {54 * profile['spread']:.3g}%)"
                ),
            },
        ),
        _create_layer(
            "closing-wash-bottom",
            {
                "inset": "-24%",
                "background": (
                    f"radial-gradient(circle at 16% 88%, {_mix_with_transparent(alt_accent, 18 * profile['accent'])} 0%, "
                    f"{_mix_with_transparent(alt_accent, 10 * profile['accent'])} 24%, transparent {52 * profile['spread']:.3g}%)"
                ),
            },
        ),
        _create_layer(
            "closing-ribbon",
            {
                "inset": "-12%",
                "background": (
                    f"linear-gradient(118deg, transparent 36%, {_mix_with_transparent(accent, 14 * profile['accent'])} 58%, transparent 78%)"
                ),
            },
        ),
        _create_layer(
            "closing-safe-zone",
            {
                "background": (
                    f"radial-gradient(circle at 50% 46%, "
                    f"{_mix_with_transparent(BACKGROUND_COLOR, 76 if emphasis == 'immersive' else 84)} 0%, "
                    f"{_mix_with_transparent(BACKGROUND_COLOR, 56 if emphasis == 'immersive' else 68)} 34%, transparent 80%)"
                )
            },
        ),
    ]


def _style_to_css(style: dict[str, Any]) -> str:
    return ";".join(f"{key}:{value}" for key, value in style.items())


def _attributes_to_html(attributes: dict[str, str]) -> str:
    return " ".join(f'{key}="{value}"' for key, value in attributes.items())


def get_scene_background_render_model(background: Any) -> dict[str, Any] | None:
    if not isinstance(background, dict) or background.get("kind") != "scene":
        return None

    preset = background.get("preset")
    emphasis = background.get("emphasis") or "balanced"
    if preset not in {
        "hero-glow",
        "section-band",
        "outline-grid",
        "quote-focus",
        "closing-wash",
    } or emphasis not in _EMPHASIS_PROFILES:
        return None

    color_token = background.get("colorToken") if isinstance(background.get("colorToken"), str) else None
    accent = _resolve_accent_color(color_token)
    alt_accent = _resolve_secondary_accent(color_token)

    if preset == "hero-glow":
        layers = _hero_glow_layers(accent, alt_accent, emphasis)
    elif preset == "section-band":
        layers = _section_band_layers(accent, alt_accent, emphasis)
    elif preset == "outline-grid":
        layers = _outline_grid_layers(accent, emphasis)
    elif preset == "quote-focus":
        layers = _quote_focus_layers(accent, alt_accent, emphasis)
    else:
        layers = _closing_wash_layers(accent, alt_accent, emphasis)

    return {
        "attributes": {
            "data-scene-background": "scene",
            "data-scene-preset": preset,
            "data-scene-emphasis": emphasis,
        },
        "frame_style": {
            "position": "relative",
            "width": "100%",
            "height": "100%",
            "overflow": "hidden",
            "background-color": BACKGROUND_COLOR,
            "isolation": "isolate",
        },
        "content_style": {
            "position": "relative",
            "z-index": 1,
            "width": "100%",
            "height": "100%",
        },
        "layers": layers,
    }


def render_scene_background_frame(background: Any, content_html: str) -> str:
    render_model = get_scene_background_render_model(background)
    if render_model is None:
        return f'<div class="slide-shell"><div class="slide-content">{content_html}</div></div>'

    layers_html = "".join(
        f'<div aria-hidden="true" data-scene-layer="{layer["key"]}" style="{_style_to_css(layer["style"])}"></div>'
        for layer in render_model["layers"]
    )
    return (
        f'<div class="slide-shell" {_attributes_to_html(render_model["attributes"])} '
        f'style="{_style_to_css(render_model["frame_style"])}">'
        f"{layers_html}"
        f'<div class="slide-content" style="{_style_to_css(render_model["content_style"])}">{content_html}</div>'
        "</div>"
    )

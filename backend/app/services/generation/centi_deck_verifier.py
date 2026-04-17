"""Lightweight non-blocking heuristics for centi-deck slide quality."""

from __future__ import annotations

import re
from typing import Any


_RENDER_TEMPLATE_RE = re.compile(
    r"render\s*\([^)]*\)\s*\{\s*return\s*`(?P<html>[\s\S]*?)`;\s*\}",
    re.MULTILINE,
)
_GLOBAL_ANIMATION_TARGET_RE = re.compile(
    r"\.(?:from|to|fromTo|set)\(\s*(['\"])(?P<selector>[^'\"]+)\1",
)


def inspect_centi_deck_artifact(artifact: dict[str, Any] | None) -> list[dict[str, Any]]:
    slides = artifact.get("slides") if isinstance(artifact, dict) else None
    if not isinstance(slides, list):
        return []

    issues: list[dict[str, Any]] = []
    signatures: list[str] = []

    for index, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        slide_id = str(slide.get("slideId") or f"slide-{index + 1}").strip() or f"slide-{index + 1}"
        title = str(slide.get("title") or "").strip()
        module_source = str(slide.get("moduleSource") or "")
        markup = _extract_markup(module_source)
        signature = _build_signature(markup)
        signatures.append(signature)

        if not _has_strong_title_signal(title, markup):
            issues.append(
                _issue(
                    slide_id,
                    category="missing-visual-hierarchy",
                    message="页面缺少明显的主标题或主视觉层级，观众难以在短时间内抓住主旨。",
                    suggestion="给这一页加入更明确的 headline 或 statement block，并压缩次级说明。",
                )
            )

        if _has_global_animation_targets(module_source):
            issues.append(
                _issue(
                    slide_id,
                    category="animation-scope",
                    message="生命周期动画使用了明显的全局选择器，可能影响其他 slide 或导致清理不稳定。",
                    suggestion="在 enter/leave 中改用 el.querySelector(...) 或 el.querySelectorAll(...) 作用域动画。",
                )
            )

    for index in range(2, len(signatures)):
        if signatures[index] and signatures[index] == signatures[index - 1] == signatures[index - 2]:
            slide = slides[index]
            if not isinstance(slide, dict):
                continue
            slide_id = str(slide.get("slideId") or f"slide-{index + 1}").strip() or f"slide-{index + 1}"
            issues.append(
                _issue(
                    slide_id,
                    category="repetitive-structure",
                    message="连续多页复用了几乎相同的结构签名，叙事节奏开始变平。",
                    suggestion="为这一页切换不同 recipe，例如 section break、agenda、evidence 或 closing 结构。",
                )
            )

    return issues


def _issue(slide_id: str, *, category: str, message: str, suggestion: str) -> dict[str, Any]:
    return {
        "slide_id": slide_id,
        "severity": "warning",
        "tier": "advisory",
        "category": category,
        "message": message,
        "suggestion": suggestion,
        "source": "centi-deck-guidance",
    }


def _extract_markup(module_source: str) -> str:
    match = _RENDER_TEMPLATE_RE.search(module_source or "")
    if not match:
        return ""
    return match.group("html")


def _has_strong_title_signal(title: str, markup: str) -> bool:
    lowered = markup.lower()
    has_visible_title_signal = any(
        signal in lowered
        for signal in ("<h1", "<h2", "<h3", "font-size:clamp(", "text-5", "text-6", "text-7")
    )
    if has_visible_title_signal:
        return True
    return bool(title) and any(marker in lowered for marker in ("font-size:2", "font-size:3", "font-weight:7", "font-weight:8"))

def _has_global_animation_targets(module_source: str) -> bool:
    for match in _GLOBAL_ANIMATION_TARGET_RE.finditer(module_source or ""):
        selector = match.group("selector").strip()
        if not selector:
            continue
        if selector.startswith("<"):
            continue
        if selector.startswith("#") or selector.startswith(".") or selector[0].isalpha():
            return True
    return "document.querySelector" in (module_source or "")


def _build_signature(markup: str) -> str:
    lowered = markup.lower()
    tokens = [
        "heading" if any(tag in lowered for tag in ("<h1", "<h2", "<h3")) else "no-heading",
        "grid" if "display:grid" in lowered or "grid-template-columns" in lowered else "no-grid",
        "cards" if ".card" in lowered or 'class="card' in lowered or "border-radius:1rem" in lowered else "no-cards",
        "steps" if ".step" in lowered or 'class="step' in lowered else "no-steps",
        "emoji" if any(char in markup for char in ("⚡", "🚀", "🌍", "🤔", "👶", "✓")) else "no-emoji",
    ]
    return "|".join(tokens)

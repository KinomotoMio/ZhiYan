#!/usr/bin/env python3
"""Select Slidev design-system references for the current outline."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
REFERENCES_DIR = ROOT / "references"


def main() -> int:
    payload = json.load(sys.stdin)
    parameters = payload.get("parameters") or {}
    outline_items = parameters.get("outline_items") or []
    topic = str(parameters.get("topic") or "")
    num_pages = int(parameters.get("num_pages") or 0)
    material_excerpt = str(parameters.get("material_excerpt") or "")
    result = select_references(
        outline_items=outline_items,
        topic=topic,
        num_pages=num_pages,
        material_excerpt=material_excerpt,
    )
    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


def select_references(*, outline_items: Any, topic: str, num_pages: int, material_excerpt: str) -> dict[str, Any]:
    if not isinstance(outline_items, list) or not outline_items:
        return {
            "selected_style": {},
            "selected_theme": {},
            "selected_layouts": [],
            "selected_blocks": [],
            "selection_summary": {"error": "outline_items_missing"},
        }

    styles = _load_reference_group("styles")
    layouts = _load_reference_group("layouts")
    blocks = _load_reference_group("blocks")
    style = _select_style(styles=styles, topic=topic, material_excerpt=material_excerpt, outline_items=outline_items, num_pages=num_pages)
    theme_choice = _theme_choice(style)

    selected_layouts: list[dict[str, Any]] = []
    selected_blocks: list[dict[str, Any]] = []
    for item in outline_items:
        if not isinstance(item, dict):
            continue
        role = str(item.get("slide_role") or "").strip().lower()
        slide_number = int(item.get("slide_number") or 0)
        title = str(item.get("title") or f"Slide {slide_number}")
        content_shape = str(item.get("content_shape") or "")

        layout = _select_layout(layouts=layouts, role=role, content_shape=content_shape)
        block_items = _select_blocks(blocks=blocks, role=role, content_shape=content_shape)
        selected_layouts.append(
            {
                "slide_number": slide_number,
                "title": title,
                "slide_role": role,
                "recipe_name": layout.get("name") or role,
                "layout": layout.get("layout"),
                "preferred_layout": layout.get("preferred_layout"),
                "container_classes": layout.get("container_classes") or "",
                "content_classes": layout.get("content_classes") or "",
                "required_signals": list(layout.get("required_signals") or []),
                "required_visual_signals": list(layout.get("required_visual_signals") or []),
                "anti_patterns": list(layout.get("anti_patterns") or []),
                "forbidden_patterns": list(layout.get("forbidden_patterns") or []),
            }
        )
        selected_blocks.append(
            {
                "slide_number": slide_number,
                "title": title,
                "slide_role": role,
                "blocks": block_items,
            }
        )

    return {
        "selected_style": style,
        "selected_theme": theme_choice,
        "selected_layouts": selected_layouts,
        "selected_blocks": selected_blocks,
        "selection_summary": {
            "style_name": style.get("name"),
            "style_reason": style.get("selection_reason"),
            "selected_theme": theme_choice.get("theme"),
            "theme_reason": theme_choice.get("theme_reason"),
            "selected_layout_names": [item.get("recipe_name") for item in selected_layouts],
            "selected_block_names": [block.get("name") for item in selected_blocks for block in item.get("blocks", [])],
        },
    }


def _load_reference_group(group: str) -> list[dict[str, Any]]:
    group_dir = REFERENCES_DIR / group
    refs: list[dict[str, Any]] = []
    for path in sorted(group_dir.glob("*.json")):
        refs.append(json.loads(path.read_text(encoding="utf-8")))
    return refs


def _select_style(*, styles: list[dict[str, Any]], topic: str, material_excerpt: str, outline_items: list[dict[str, Any]], num_pages: int) -> dict[str, Any]:
    text = f"{topic}\n{material_excerpt}".lower()
    role_counts: dict[str, int] = {}
    for item in outline_items:
        role = str(item.get("slide_role") or "").strip().lower()
        if role:
            role_counts[role] = role_counts.get(role, 0) + 1

    best: dict[str, Any] | None = None
    best_score = -1
    for style in styles:
        score = 0
        if str(style.get("name") or "") == "tech-launch":
            if any(token in text for token in ("ai", "future", "launch", "impact", "transformation", "work")):
                score += 3
        for keyword in style.get("keywords", []):
            if str(keyword).lower() in text:
                score += 2
        if role_counts.get("comparison", 0) and style.get("prefers_comparison"):
            score += 1
        if num_pages >= 6 and style.get("supports_dense_decks"):
            score += 1
        if best is None or score > best_score:
            best = style
            best_score = score

    chosen = dict(best or styles[0])
    chosen["selection_reason"] = _style_reason(chosen, topic=topic, outline_items=outline_items)
    return chosen


def _style_reason(style: dict[str, Any], *, topic: str, outline_items: list[dict[str, Any]]) -> str:
    role_preview = ", ".join(str(item.get("slide_role") or "") for item in outline_items[:5] if isinstance(item, dict))
    return f"Selected {style.get('name')} for topic `{topic or 'untitled'}` with roles [{role_preview}] and the style's visual tone/contrast profile."


def _theme_choice(style: dict[str, Any]) -> dict[str, Any]:
    return {
        "theme": str(style.get("theme") or "seriph"),
        "theme_reason": str(
            style.get("theme_reason")
            or "Use an official Slidev theme baseline first, then layer the design-system recipes on top."
        ),
        "theme_mode": str(style.get("theme_mode") or "official-theme-plus-light-overrides"),
    }


def _select_layout(*, layouts: list[dict[str, Any]], role: str, content_shape: str) -> dict[str, Any]:
    lower_shape = content_shape.lower()
    for layout in layouts:
        if str(layout.get("slide_role") or "") == role:
            selected = dict(layout)
            if role == "comparison" and "table" in lower_shape:
                selected["preferred_block_order"] = ["compare-split", "compact-bullets"]
            return selected
    return {"name": role or "default", "layout": None, "container_classes": "", "content_classes": "", "required_signals": [], "anti_patterns": []}


def _select_blocks(*, blocks: list[dict[str, Any]], role: str, content_shape: str) -> list[dict[str, Any]]:
    lower_shape = content_shape.lower()
    block_names_by_role = {
        "cover": ["hero-title"],
        "context": ["quote-callout" if any(token in lower_shape for token in ("quote", "callout")) else "compact-bullets"],
        "framework": ["framework-explainer"],
        "detail": ["framework-explainer" if any(token in lower_shape for token in ("diagram", "framework")) else "compact-bullets"],
        "comparison": ["compare-split"],
        "recommendation": ["takeaway-next-steps"],
        "closing": ["takeaway-next-steps"],
    }
    selected_names = block_names_by_role.get(role, ["compact-bullets"])
    selected = []
    for name in selected_names:
        block = next((item for item in blocks if item.get("name") == name), None)
        if block is not None:
            selected.append(dict(block))
    return selected


if __name__ == "__main__":
    raise SystemExit(main())

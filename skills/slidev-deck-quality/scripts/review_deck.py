#!/usr/bin/env python3
"""Review Slidev deck structure quality after markdown generation."""

from __future__ import annotations

import json
import re
import sys
from typing import Any


def main() -> int:
    payload = json.load(sys.stdin)
    parameters = payload.get("parameters") or {}
    markdown = str(parameters.get("markdown") or "")
    outline_items = parameters.get("outline_items") or []
    result = review_deck(markdown=markdown, outline_items=outline_items)
    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


def review_deck(*, markdown: str, outline_items: Any) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    slides = _slide_chunks(markdown)
    if not slides:
        issues.append({"code": "empty_deck", "message": "Deck markdown does not contain any body slides."})
        return _result(False, issues, warnings, [])

    if isinstance(outline_items, list):
        if len(outline_items) != len(slides):
            warnings.append(
                {
                    "code": "outline_slide_count_mismatch",
                    "message": f"Deck has {len(slides)} slides, but outline tracks {len(outline_items)}.",
                }
            )
    else:
        warnings.append({"code": "missing_outline_context", "message": "Deck review ran without a valid outline context."})

    bullet_heavy = sum(1 for slide in slides if _bullet_count(slide) >= 4)
    if len(slides) >= 4 and bullet_heavy / len(slides) >= 0.75:
        warnings.append(
            {
                "code": "bullet_dominant_deck",
                "message": "Deck is dominated by bullet-heavy slides; mix in compare/framework/quote/diagram structures.",
            }
        )

    signatures = [_slide_signature(slide) for slide in slides]
    if _has_repeated_run(signatures, threshold=3):
        warnings.append(
            {
                "code": "repetitive_deck_structure",
                "message": "Three or more consecutive slides reuse the same structural signature.",
            }
        )

    if not _looks_like_closing(slides[-1]):
        warnings.append(
            {
                "code": "weak_closing",
                "message": "Closing slide lacks a strong takeaway/next-step structure.",
            }
        )

    if isinstance(outline_items, list):
        for slide, item in zip(slides, outline_items, strict=False):
            if not isinstance(item, dict):
                continue
            role = str(item.get("slide_role") or "").strip().lower()
            title = str(item.get("title") or "").strip()
            if role == "comparison" and not _looks_comparison_like(slide):
                warnings.append(
                    {
                        "code": "comparison_role_mismatch",
                        "message": f"Slide `{title or 'comparison'}` is tagged comparison but lacks a clear compare structure.",
                    }
                )
            if role == "framework" and _bullet_count(slide) >= 5 and not _has_visual_structure(slide):
                warnings.append(
                    {
                        "code": "framework_role_too_flat",
                        "message": f"Slide `{title or 'framework'}` reads like a flat bullet dump instead of a framework page.",
                    }
                )

    return _result(not issues, issues, warnings, signatures)


def _result(ok: bool, issues: list[dict[str, str]], warnings: list[dict[str, str]], signatures: list[str]) -> dict[str, Any]:
    return {
        "ok": ok,
        "issues": issues,
        "warnings": warnings,
        "signatures": signatures,
    }


def _slide_chunks(markdown: str) -> list[str]:
    text = markdown.strip()
    if not text:
        return []
    body = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", text, count=1, flags=re.DOTALL)
    return [chunk.strip() for chunk in re.split(r"\n---\n", body) if chunk.strip()]


def _bullet_count(slide: str) -> int:
    return sum(1 for line in slide.splitlines() if line.strip().startswith(("- ", "* ")))


def _slide_signature(slide: str) -> str:
    heading = "heading" if re.search(r"^\s{0,3}#{1,3}\s+", slide, re.MULTILINE) else "plain"
    bullet = "bullet" if _bullet_count(slide) >= 3 else "non-bullet"
    visual = "visual" if _has_visual_structure(slide) else ""
    return "|".join(part for part in (heading, bullet, visual) if part)


def _has_visual_structure(slide: str) -> bool:
    markers = (
        "```mermaid",
        "layout:",
        "class:",
        "> ",
        "|",
        "::",
        "<div",
    )
    return any(marker in slide for marker in markers)


def _has_repeated_run(signatures: list[str], *, threshold: int) -> bool:
    run = 1
    for index in range(1, len(signatures)):
        if signatures[index] == signatures[index - 1]:
            run += 1
            if run >= threshold:
                return True
        else:
            run = 1
    return False


def _looks_like_closing(slide: str) -> bool:
    lower = slide.lower()
    return any(token in lower for token in ("总结", "展望", "下一步", "结论", "next step", "takeaway", "summary"))


def _looks_comparison_like(slide: str) -> bool:
    return "|" in slide or "vs" in slide.lower() or "对比" in slide or "before" in slide.lower()


if __name__ == "__main__":
    raise SystemExit(main())

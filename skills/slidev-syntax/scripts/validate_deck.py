#!/usr/bin/env python3
"""Static validation for generated Slidev markdown decks."""

from __future__ import annotations

import json
import re
import sys
from typing import Any


def main() -> int:
    payload = json.load(sys.stdin)
    parameters = payload.get("parameters") or {}
    markdown = str(parameters.get("markdown") or "")
    expected_pages = parameters.get("expected_pages")
    result = validate_deck(markdown=markdown, expected_pages=expected_pages)
    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


def validate_deck(*, markdown: str, expected_pages: Any = None) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    text = markdown.strip()

    if not text:
        issues.append({"code": "empty_markdown", "message": "Deck markdown is empty."})
        return _result(False, 0, issues, warnings)

    if not _has_frontmatter(text):
        issues.append({"code": "missing_frontmatter", "message": "The first slide is missing global frontmatter."})

    slide_count = _count_slides(text)
    if slide_count < 2:
        issues.append({"code": "too_few_slides", "message": "Slidev MVP deck should contain at least 2 slides."})

    if "\n---\n" not in _strip_frontmatter(text):
        issues.append({"code": "missing_separator", "message": "Deck is missing Slidev slide separators (`---`)."})

    expected_count = _coerce_expected_pages(expected_pages)
    if expected_count is not None and slide_count < expected_count:
        warnings.append(
            {
                "code": "fewer_than_expected",
                "message": f"Deck has {slide_count} slides, below expected {expected_count}.",
            }
        )

    fence_issues = _validate_fences(text)
    issues.extend(fence_issues)
    warnings.extend(_structure_warnings(text))

    return _result(not issues, slide_count, issues, warnings)


def _result(
    ok: bool,
    slide_count: int,
    issues: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "ok": ok,
        "slide_count": slide_count,
        "issues": issues,
        "warnings": warnings,
    }


def _has_frontmatter(text: str) -> bool:
    return re.match(r"^---\s*\n.*?\n---\s*(?:\n|$)", text, re.DOTALL) is not None


def _strip_frontmatter(text: str) -> str:
    match = re.match(r"^---\s*\n.*?\n---\s*\n?", text, re.DOTALL)
    if match:
        return text[match.end():]
    return text


def _count_slides(text: str) -> int:
    body = _strip_frontmatter(text).strip()
    if not body:
        return 1 if _has_frontmatter(text) else 0
    chunks = [chunk for chunk in re.split(r"\n---\n", body) if chunk.strip()]
    return max(1, len(chunks))


def _coerce_expected_pages(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        expected = int(value)
    except (TypeError, ValueError):
        return None
    return max(1, expected)


def _validate_fences(text: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if _count_fence_lines(text, "```") % 2 != 0:
        issues.append({"code": "unclosed_code_fence", "message": "Code fence blocks are not balanced."})
    if _count_fence_lines(text, "~~~") % 2 != 0:
        issues.append({"code": "unclosed_tilde_fence", "message": "Tilde fence blocks are not balanced."})
    return issues


def _count_fence_lines(text: str, marker: str) -> int:
    count = 0
    for line in text.splitlines():
        if line.strip().startswith(marker):
            count += 1
    return count


def _structure_warnings(text: str) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    slides = _slide_chunks(text)
    if not slides:
        return warnings

    if len(slides) >= 3:
        bullet_heavy = sum(1 for slide in slides if _bullet_count(slide) >= 3)
        if bullet_heavy / len(slides) >= 0.75:
            warnings.append(
                {
                    "code": "bullet_dominant_deck",
                    "message": "Most slides are bullet-heavy; consider mixing layouts, quotes, diagrams, or compare structures.",
                }
            )

    if len(slides) >= 4 and _native_structure_count(slides) == 0:
        warnings.append(
            {
                "code": "low_slidev_native_usage",
                "message": "Deck barely uses Slidev-native layouts or richer structures; consider built-in layouts, columns, quotes, tables, or Mermaid.",
            }
        )

    signatures = [_slide_signature(slide) for slide in slides]
    if _has_repeated_run(signatures, threshold=3):
        warnings.append(
            {
                "code": "repetitive_structure",
                "message": "Three or more consecutive slides share the same structure signature.",
            }
        )

    if not _looks_like_cover(slides[0]):
        warnings.append(
            {
                "code": "weak_cover",
                "message": "Cover slide looks weak; prefer a clear title and short positioning line.",
            }
        )

    if not _looks_like_closing(slides[-1]):
        warnings.append(
            {
                "code": "weak_closing",
                "message": "Closing slide is weak or missing a clear takeaway/next-step structure.",
            }
        )

    return warnings


def _slide_chunks(text: str) -> list[str]:
    body = _strip_frontmatter(text).strip()
    if not body:
        return []
    return [chunk.strip() for chunk in re.split(r"\n---\n", body) if chunk.strip()]


def _bullet_count(slide: str) -> int:
    return sum(1 for line in slide.splitlines() if line.strip().startswith(("- ", "* ")))


def _slide_signature(slide: str) -> str:
    header = "heading" if re.search(r"^\s{0,3}#{1,3}\s+", slide, re.MULTILINE) else "plain"
    bullet = "bullet" if _bullet_count(slide) >= 2 else "non-bullet"
    mermaid = "mermaid" if "```mermaid" in slide else ""
    quote = "quote" if re.search(r"^\s*>\s+", slide, re.MULTILINE) else ""
    table = "table" if "|" in slide and re.search(r"^\s*\|.*\|\s*$", slide, re.MULTILINE) else ""
    layout = "layout" if re.search(r"^\s*layout:\s*", slide, re.MULTILINE) else ""
    klass = "class" if re.search(r"^\s*class:\s*", slide, re.MULTILINE) else ""
    return "|".join(part for part in [header, bullet, mermaid, quote, table, layout, klass] if part)


def _native_structure_count(slides: list[str]) -> int:
    count = 0
    for slide in slides:
        if any(
            marker in slide
            for marker in (
                "```mermaid",
                "layout:",
                "class:",
                "> ",
                "<div",
            )
        ):
            count += 1
            continue
        if "|" in slide and re.search(r"^\s*\|.*\|\s*$", slide, re.MULTILINE):
            count += 1
    return count


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


def _looks_like_cover(slide: str) -> bool:
    lines = [line.strip() for line in slide.splitlines() if line.strip()]
    if not lines:
        return False
    first = lines[0]
    heading_like = first.startswith("#")
    return heading_like and _bullet_count(slide) <= 1 and len(lines) <= 4


def _looks_like_closing(slide: str) -> bool:
    lower = slide.lower()
    if any(token in lower for token in ("next step", "takeaway", "closing", "summary", "展望", "总结", "下一步", "结论")):
        return True
    return _bullet_count(slide) <= 3 and len([line for line in slide.splitlines() if line.strip()]) <= 6


if __name__ == "__main__":
    raise SystemExit(main())

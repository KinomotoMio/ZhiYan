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
    normalized_markdown, normalization = _normalize_slidev_composition(markdown)
    text = normalized_markdown.strip()

    if not text:
        issues.append({"code": "empty_markdown", "message": "Deck markdown is empty."})
        return _result(
            False,
            0,
            issues,
            warnings,
            native_usage_summary={"layouts": [], "layout_counts": {}, "pattern_counts": {}, "class_counts": {}, "recipe_classes": {}, "native_slide_count": 0, "plain_slide_count": 0, "visual_recipe_slide_count": 0},
            blank_first_slide_detected=bool(normalization.get("blank_first_slide_detected")),
        )

    if normalization.get("blank_first_slide_detected"):
        warnings.append(
            {
                "code": "blank_first_slide_normalized",
                "message": "Detected an empty first-slide pattern; merged the first slide frontmatter into the opening headmatter.",
            }
        )
    if normalization.get("double_separator_frontmatter_detected"):
        warnings.append(
            {
                "code": "double_separator_frontmatter_normalized",
                "message": "Detected duplicated slide separator/frontmatter fences and normalized them before validation.",
            }
        )

    if not _has_frontmatter(text):
        issues.append({"code": "missing_frontmatter", "message": "The first slide is missing global frontmatter."})

    slides = _slide_chunks(text)
    slide_count = len(slides)
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
    issues.extend(_validate_slide_frontmatter_blocks(slides))
    native_usage_summary = _native_usage_summary(slides)
    warnings.extend(_structure_warnings(slides, native_usage_summary))

    return _result(
        not issues,
        slide_count,
        issues,
        warnings,
        native_usage_summary=native_usage_summary,
        blank_first_slide_detected=bool(normalization.get("blank_first_slide_detected")),
    )


def _result(
    ok: bool,
    slide_count: int,
    issues: list[dict[str, str]],
    warnings: list[dict[str, str]],
    *,
    native_usage_summary: dict[str, Any],
    blank_first_slide_detected: bool,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "slide_count": slide_count,
        "issues": issues,
        "warnings": warnings,
        "native_usage_summary": native_usage_summary,
        "blank_first_slide_detected": blank_first_slide_detected,
    }


def _has_frontmatter(text: str) -> bool:
    return re.match(r"^---\s*\n.*?\n---\s*(?:\n|$)", text, re.DOTALL) is not None


def _strip_frontmatter(text: str) -> str:
    match = re.match(r"^---\s*\n.*?\n---\s*\n?", text, re.DOTALL)
    if match:
        return text[match.end():]
    return text


def _count_slides(text: str) -> int:
    return len(_slide_chunks(text))


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


def _validate_slide_frontmatter_blocks(slides: list[str]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for index, slide in enumerate(slides, start=1):
        if _starts_with_unfenced_slide_frontmatter(slide):
            issues.append(
                {
                    "code": "unfenced_slide_frontmatter",
                    "message": f"Slide {index} starts with `layout:`/`class:` lines but does not wrap them in a Slidev frontmatter fence.",
                }
            )
    return issues


def _count_fence_lines(text: str, marker: str) -> int:
    count = 0
    for line in text.splitlines():
        if line.strip().startswith(marker):
            count += 1
    return count


def _structure_warnings(slides: list[str], native_usage_summary: dict[str, Any]) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
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

    if len(slides) >= 4 and int(native_usage_summary.get("native_slide_count") or 0) == 0:
        warnings.append(
            {
                "code": "low_slidev_native_usage",
                "message": "Deck barely uses Slidev-native layouts or richer structures; consider built-in layouts, columns, quotes, tables, or Mermaid.",
            }
        )

    if len(slides) >= 4 and int(native_usage_summary.get("visual_recipe_slide_count") or 0) < max(2, len(slides) // 2):
        warnings.append(
            {
                "code": "low_visual_recipe_usage",
                "message": "Deck uses too few stable visual recipe classes; key pages still look closer to markdown document sections than presentation slides.",
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
    first_slide_frontmatter = _extract_first_slide_frontmatter_from_global(text)
    body = _strip_frontmatter(text).strip()
    if not body:
        return []

    slides: list[str] = []
    current: list[str] = []
    lines = body.splitlines()
    index = 0
    inside_fence = False
    pending_frontmatter: list[str] | None = None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            inside_fence = not inside_fence

        if not inside_fence and stripped == "---":
            if current:
                slide = "\n".join(current).strip()
                if slide:
                    slides.append(slide)
                current = []
            frontmatter_block, next_index = _consume_slide_frontmatter(lines, index + 1)
            if frontmatter_block is not None:
                pending_frontmatter = frontmatter_block
                index = next_index
                continue
            index += 1
            continue

        if pending_frontmatter:
            current.extend(["---", *pending_frontmatter, "---"])
            pending_frontmatter = None
        current.append(line)
        index += 1

    if pending_frontmatter:
        current.extend(["---", *pending_frontmatter, "---"])
    slide = "\n".join(current).strip()
    if slide:
        slides.append(slide)
    if slides and first_slide_frontmatter:
        slides[0] = "\n".join(["---", *first_slide_frontmatter, "---", slides[0]])
    return slides


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


def _native_usage_summary(slides: list[str]) -> dict[str, Any]:
    layout_counts: dict[str, int] = {}
    pattern_counts: dict[str, int] = {
        "mermaid": 0,
        "quote": 0,
        "table": 0,
        "div_grid": 0,
        "class": 0,
        "callout": 0,
    }
    class_counts: dict[str, int] = {}
    recipe_classes: dict[str, int] = {}
    native_slide_count = 0
    visual_recipe_slide_count = 0

    for slide in slides:
        native_found = False
        layout_name = _extract_layout_name(slide)
        if layout_name:
            layout_counts[layout_name] = layout_counts.get(layout_name, 0) + 1
            native_found = True
        classes = _extract_classes(slide)
        if classes:
            pattern_counts["class"] += 1
            native_found = True
            for name in classes:
                class_counts[name] = class_counts.get(name, 0) + 1
                if name.startswith("deck-"):
                    recipe_classes[name] = recipe_classes.get(name, 0) + 1
        if "```mermaid" in slide:
            pattern_counts["mermaid"] += 1
            native_found = True
        if re.search(r"^\s*>\s+", slide, re.MULTILINE):
            pattern_counts["quote"] += 1
            native_found = True
        if "|" in slide and re.search(r"^\s*\|.*\|\s*$", slide, re.MULTILINE):
            pattern_counts["table"] += 1
            native_found = True
        if "<div" in slide and "grid" in slide:
            pattern_counts["div_grid"] += 1
            native_found = True
        if "::" in slide:
            pattern_counts["callout"] += 1
            native_found = True
        if recipe_classes and any(name in recipe_classes for name in classes):
            visual_recipe_slide_count += 1
        if native_found:
            native_slide_count += 1

    return {
        "layouts": sorted(layout_counts),
        "layout_counts": layout_counts,
        "pattern_counts": pattern_counts,
        "class_counts": class_counts,
        "recipe_classes": recipe_classes,
        "native_slide_count": native_slide_count,
        "plain_slide_count": max(0, len(slides) - native_slide_count),
        "visual_recipe_slide_count": visual_recipe_slide_count,
    }


def _extract_layout_name(slide: str) -> str | None:
    frontmatter = _frontmatter_block(slide)
    if not frontmatter:
        return None
    match = re.search(r"^\s*layout:\s*([A-Za-z0-9_-]+)\s*$", frontmatter, re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


def _extract_classes(slide: str) -> list[str]:
    classes: set[str] = set()
    frontmatter = _frontmatter_block(slide)
    for match in re.finditer(r"^\s*class:\s*(.+?)\s*$", frontmatter, re.MULTILINE):
        classes.update(_split_classes(match.group(1)))
    for match in re.finditer(r'class="([^"]+)"', slide):
        classes.update(_split_classes(match.group(1)))
    return sorted(classes)


def _split_classes(raw: str) -> list[str]:
    return [token.strip() for token in re.split(r"\s+", raw.strip()) if token.strip()]


def _consume_slide_frontmatter(lines: list[str], start_index: int) -> tuple[list[str] | None, int]:
    index = start_index
    block: list[str] = []
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped == "---":
            return (block if _looks_like_slide_frontmatter(block) else None, index + 1)
        block.append(lines[index])
        index += 1
    return None, start_index


def _looks_like_slide_frontmatter(lines: list[str]) -> bool:
    meaningful = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    if not meaningful:
        return False
    return all(":" in line and not line.startswith("::") for line in meaningful)


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
    body = _strip_slide_frontmatter(slide)
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return False
    first = lines[0]
    heading_like = first.startswith("#")
    return heading_like and _bullet_count(slide) <= 1 and len(lines) <= 4


def _looks_like_closing(slide: str) -> bool:
    body = _strip_slide_frontmatter(slide)
    lower = body.lower()
    if any(token in lower for token in ("next step", "takeaway", "closing", "summary", "展望", "总结", "下一步", "结论")):
        return True
    return _bullet_count(body) <= 3 and len([line for line in body.splitlines() if line.strip()]) <= 6


def _strip_slide_frontmatter(slide: str) -> str:
    return re.sub(r"^---\s*\n.*?\n---\s*\n?", "", slide, count=1, flags=re.DOTALL)


def _frontmatter_block(slide: str) -> str:
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", slide, re.DOTALL)
    if not match:
        return ""
    return match.group(1)


def _starts_with_unfenced_slide_frontmatter(slide: str) -> bool:
    stripped = slide.lstrip()
    if stripped.startswith("---"):
        return False
    allowed = {"layout", "class", "transition", "background"}
    nonempty = [line.strip() for line in slide.splitlines() if line.strip()]
    if not nonempty:
        return False
    candidate_lines = nonempty[:3]
    keys = [_frontmatter_key(line) for line in candidate_lines]
    return any(key in allowed for key in keys if key)


def _extract_first_slide_frontmatter_from_global(text: str) -> list[str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not match:
        return []
    allowed = {"layout", "class", "transition", "background"}
    lines: list[str] = []
    for raw_line in match.group(1).splitlines():
        key = _frontmatter_key(raw_line.rstrip())
        if key in allowed:
            lines.append(raw_line.rstrip())
    return lines


def _normalize_slidev_composition(markdown: str) -> tuple[str, dict[str, bool | int]]:
    normalized, metadata = _normalize_leading_first_slide_frontmatter(markdown)
    normalized, separator_metadata = _normalize_double_separator_slide_frontmatter(normalized)
    metadata.update(separator_metadata)
    return normalized, metadata


def _normalize_leading_first_slide_frontmatter(markdown: str) -> tuple[str, dict[str, bool]]:
    text = str(markdown or "")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not match:
        return text, {"blank_first_slide_detected": False, "normalized_first_slide_frontmatter": False}

    global_frontmatter = match.group(1)
    body = match.group(2)
    body_match = re.match(r"^\s*---\s*\n(.*?)\n---\s*\n?(.*)$", body, re.DOTALL)
    if not body_match:
        return text, {"blank_first_slide_detected": False, "normalized_first_slide_frontmatter": False}

    slide_frontmatter = body_match.group(1)
    if not _looks_like_slide_frontmatter(slide_frontmatter.splitlines()):
        return text, {"blank_first_slide_detected": False, "normalized_first_slide_frontmatter": False}

    remaining = body_match.group(2)
    if not remaining.strip():
        return text, {"blank_first_slide_detected": False, "normalized_first_slide_frontmatter": False}

    merged = _merge_frontmatter_blocks(global_frontmatter, slide_frontmatter)
    normalized = f"---\n{merged}\n---\n\n{remaining.lstrip()}".rstrip() + "\n"
    return normalized, {"blank_first_slide_detected": True, "normalized_first_slide_frontmatter": True}


def _normalize_double_separator_slide_frontmatter(markdown: str) -> tuple[str, dict[str, bool | int]]:
    text = str(markdown or "")
    prefix, body = _split_global_frontmatter_block(text)
    if not body.strip():
        return text, {"double_separator_frontmatter_detected": False, "normalized_double_separator_frontmatter_count": 0}

    lines = body.splitlines()
    normalized_lines: list[str] = []
    index = 0
    inside_fence = False
    normalized_count = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            inside_fence = not inside_fence

        if not inside_fence and stripped == "---":
            probe_index = index + 1
            while probe_index < len(lines) and not lines[probe_index].strip():
                probe_index += 1
            if probe_index < len(lines) and lines[probe_index].strip() == "---":
                frontmatter_block, next_index = _consume_slide_frontmatter(lines, probe_index + 1)
                if frontmatter_block is not None:
                    normalized_lines.extend(["---", *frontmatter_block, "---"])
                    normalized_count += 1
                    index = next_index
                    continue

        normalized_lines.append(line)
        index += 1

    normalized_body = "\n".join(normalized_lines).strip()
    normalized = prefix + normalized_body
    if normalized_body:
        normalized = normalized.rstrip() + "\n"
    return normalized, {
        "double_separator_frontmatter_detected": normalized_count > 0,
        "normalized_double_separator_frontmatter_count": normalized_count,
    }


def _merge_frontmatter_blocks(base: str, extra: str) -> str:
    merged: list[str] = []
    key_positions: dict[str, int] = {}

    def _register(lines: list[str], *, replace_existing: bool) -> None:
        for raw_line in lines:
            line = raw_line.rstrip()
            key = _frontmatter_key(line)
            if key and key in key_positions and replace_existing:
                merged[key_positions[key]] = line
                continue
            if key:
                key_positions[key] = len(merged)
            merged.append(line)

    _register(base.splitlines(), replace_existing=False)
    _register(extra.splitlines(), replace_existing=True)
    return "\n".join(merged).strip()


def _frontmatter_key(line: str) -> str | None:
    if not line or line.startswith((" ", "\t", "-", "#")) or ":" not in line:
        return None
    return line.split(":", 1)[0].strip() or None


def _split_global_frontmatter_block(text: str) -> tuple[str, str]:
    match = re.match(r"^(---\s*\n.*?\n---\s*\n?)(.*)$", text, re.DOTALL)
    if not match:
        return "", text
    return match.group(1), match.group(2)


if __name__ == "__main__":
    raise SystemExit(main())

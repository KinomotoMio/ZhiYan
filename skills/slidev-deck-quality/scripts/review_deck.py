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
    slide_reports: list[dict[str, Any]] = []
    normalized_markdown, normalization = _normalize_leading_first_slide_frontmatter(markdown)
    if normalization.get("blank_first_slide_detected"):
        warnings.append(
            {
                "code": "blank_first_slide_normalized",
                "message": "Detected an empty first-slide pattern and normalized the first slide frontmatter before review.",
            }
        )

    slides = _slide_chunks(normalized_markdown)
    if not slides:
        issues.append({"code": "empty_deck", "message": "Deck markdown does not contain any body slides."})
        return _result(
            False,
            issues,
            warnings,
            [],
            slide_reports,
            expected_slide_count=0,
            actual_slide_count=0,
            blank_first_slide_detected=bool(normalization.get("blank_first_slide_detected")),
        )

    if not isinstance(outline_items, list) or not outline_items:
        issues.append({"code": "missing_outline_context", "message": "Deck review requires a valid outline context."})
        return _result(
            False,
            issues,
            warnings,
            _deck_signatures(slides),
            slide_reports,
            expected_slide_count=0,
            actual_slide_count=len(slides),
            blank_first_slide_detected=bool(normalization.get("blank_first_slide_detected")),
        )

    if len(outline_items) != len(slides):
        issues.append(
            {
                "code": "outline_slide_count_mismatch",
                "message": f"Deck has {len(slides)} slides, but outline tracks {len(outline_items)}.",
            }
        )

    for slide_number, slide in enumerate(slides, start=1):
        item = outline_items[slide_number - 1] if slide_number - 1 < len(outline_items) else {}
        slide_reports.append(_review_slide(slide_number=slide_number, slide=slide, item=item, issues=issues, warnings=warnings))

    bullet_heavy = sum(1 for slide in slides if _bullet_count(slide) >= 4)
    if len(slides) >= 4 and bullet_heavy / len(slides) >= 0.75:
        warnings.append(
            {
                "code": "bullet_dominant_deck",
                "message": "Deck is dominated by bullet-heavy slides; mix in compare/framework/quote/diagram structures.",
            }
        )

    signatures = _deck_signatures(slides)
    if _has_repeated_run(signatures, threshold=3):
        warnings.append(
            {
                "code": "repetitive_deck_structure",
                "message": "Three or more consecutive slides reuse the same structural signature.",
            }
        )

    return _result(
        not issues,
        issues,
        warnings,
        signatures,
        slide_reports,
        expected_slide_count=len(outline_items),
        actual_slide_count=len(slides),
        blank_first_slide_detected=bool(normalization.get("blank_first_slide_detected")),
    )


def _result(
    ok: bool,
    issues: list[dict[str, str]],
    warnings: list[dict[str, str]],
    signatures: list[str],
    slide_reports: list[dict[str, Any]],
    *,
    expected_slide_count: int,
    actual_slide_count: int,
    blank_first_slide_detected: bool,
) -> dict[str, Any]:
    passed_slides = sum(1 for report in slide_reports if report.get("status") == "pass")
    failed_slides = sum(1 for report in slide_reports if report.get("status") == "failed")
    warning_slides = sum(1 for report in slide_reports if report.get("status") == "warning")
    visual_recipe_summary = _visual_recipe_summary(slide_reports)
    return {
        "ok": ok,
        "issues": issues,
        "warnings": warnings,
        "signatures": signatures,
        "slide_reports": slide_reports,
        "visual_recipe_summary": visual_recipe_summary,
        "blank_first_slide_detected": blank_first_slide_detected,
        "contract_summary": {
            "expected_slide_count": expected_slide_count,
            "actual_slide_count": actual_slide_count,
            "hard_issue_count": len(issues),
            "warning_count": len(warnings),
            "passed_slides": passed_slides,
            "warning_slides": warning_slides,
            "failed_slides": failed_slides,
            "matched_visual_recipes": visual_recipe_summary["matched_recipe_count"],
            "weak_visual_recipes": visual_recipe_summary["weak_recipe_count"],
        },
    }


def _review_slide(
    *,
    slide_number: int,
    slide: str,
    item: Any,
    issues: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    role = str(item.get("slide_role") or "").strip().lower() if isinstance(item, dict) else ""
    content_shape = str(item.get("content_shape") or "").strip().lower() if isinstance(item, dict) else ""
    title = str(item.get("title") or f"Slide {slide_number}").strip() if isinstance(item, dict) else f"Slide {slide_number}"
    pattern_hint = item.get("slidev_pattern_hint") if isinstance(item, dict) else {}
    if not isinstance(pattern_hint, dict):
        pattern_hint = {}
    visual_hint = item.get("slidev_visual_hint") if isinstance(item, dict) else {}
    if not isinstance(visual_hint, dict):
        visual_hint = {}
    preferred_layouts = [str(name).strip() for name in (pattern_hint.get("preferred_layouts") or []) if str(name).strip()]
    preferred_patterns = [str(name).strip() for name in (pattern_hint.get("preferred_patterns") or []) if str(name).strip()]
    observed_layout = _extract_layout_name(slide)
    observed_patterns = _observed_patterns(slide)
    observed_classes = _extract_classes(slide)
    observed_signals = _observed_signals(slide, observed_layout, observed_patterns, observed_classes)
    expected_recipe_name = str(visual_hint.get("name") or "")
    expected_recipe_classes = [str(name).strip() for name in (visual_hint.get("preferred_classes") or []) if str(name).strip()]
    expected_recipe_signals = [str(name).strip() for name in (visual_hint.get("required_signals") or []) if str(name).strip()]
    visual_recipe_status = _visual_recipe_status(
        role=role,
        expected_classes=expected_recipe_classes,
        expected_signals=expected_recipe_signals,
        observed_classes=observed_classes,
        observed_signals=observed_signals,
    )
    findings: list[dict[str, str]] = []

    def add_issue(code: str, message: str) -> None:
        finding = {"severity": "issue", "code": code, "message": message}
        findings.append(finding)
        issues.append({"code": code, "message": message})

    def add_warning(code: str, message: str) -> None:
        finding = {"severity": "warning", "code": code, "message": message}
        findings.append(finding)
        warnings.append({"code": code, "message": message})

    if _starts_with_unfenced_slide_frontmatter(slide):
        add_issue(
            "unfenced_slide_frontmatter",
            f"Slide `{title}` starts with bare `layout:`/`class:` lines instead of a fenced Slidev frontmatter block.",
        )

    if role == "cover":
        if not _looks_like_cover(slide):
            add_issue("cover_role_mismatch", f"Slide `{title}` is tagged cover but does not read like a cover slide.")
        elif observed_layout not in {"cover", "center"}:
            add_warning("cover_native_layout_missing", f"Slide `{title}` reads like cover but does not use `layout: cover` or `layout: center`.")
    elif role == "closing":
        if not _looks_like_closing(slide):
            add_issue(
                "closing_role_mismatch",
                f"Slide `{title}` is tagged closing but lacks a takeaway, summary, or next-step structure.",
            )
        elif not _has_strong_closing_signal(slide):
            add_warning("weak_closing", f"Slide `{title}` closes the deck but the closing signal is still weak.")
        elif observed_layout not in {"end", "center"}:
            add_warning("closing_native_layout_missing", f"Slide `{title}` closes correctly but does not use `layout: end` or `layout: center`.")
    elif role == "comparison":
        if not _looks_comparison_like(slide):
            add_issue(
                "comparison_role_mismatch",
                f"Slide `{title}` is tagged comparison but lacks a clear compare structure.",
            )
        elif observed_layout != "two-cols" and "table" not in observed_patterns:
            add_issue(
                "comparison_native_pattern_missing",
                f"Slide `{title}` should use `layout: two-cols` or an explicit compare table.",
            )
    elif role == "framework":
        if _looks_flat_framework(slide):
            add_issue(
                "framework_role_too_flat",
                f"Slide `{title}` is tagged framework but reads like a flat bullet dump instead of a structured model.",
            )
        elif _bullet_count(slide) >= 3 and not _has_visual_structure(slide):
            add_warning(
                "framework_role_weakened",
                f"Slide `{title}` is a framework page but could use a clearer visual or native Slidev structure.",
            )
        elif not {"mermaid", "table", "div-grid"}.intersection(observed_patterns):
            add_warning(
                "framework_native_pattern_missing",
                f"Slide `{title}` is a framework page but does not yet use a strong native structure such as Mermaid, table, or grid.",
            )
    elif role in {"context", "detail"} and _bullet_count(slide) >= 5 and not _has_visual_structure(slide):
        add_warning(
            "dense_context_or_detail",
            f"Slide `{title}` is dense and mostly flat bullets; consider trimming or adding one structural cue.",
        )
    elif role == "recommendation" and "callout" not in observed_patterns and _bullet_count(slide) >= 4:
        add_warning(
            "recommendation_native_pattern_missing",
            f"Slide `{title}` would benefit from a clearer decision/callout structure instead of a flat action list.",
        )

    if expected_recipe_name and visual_recipe_status != "matched":
        code = f"{role or 'slide'}_visual_recipe_weak"
        message = f"Slide `{title}` is structurally acceptable but does not yet fully realize the `{expected_recipe_name}` visual recipe."
        add_warning(code, message)

    status = "pass"
    if any(finding["severity"] == "issue" for finding in findings):
        status = "failed"
    elif findings:
        status = "warning"

    return {
        "slide_number": slide_number,
        "title": title,
        "role": role or None,
        "content_shape": content_shape or None,
        "preferred_layouts": preferred_layouts,
        "preferred_patterns": preferred_patterns,
        "observed_layout": observed_layout,
        "observed_patterns": observed_patterns,
        "observed_classes": observed_classes,
        "observed_signals": observed_signals,
        "expected_visual_recipe": {
            "name": expected_recipe_name or None,
            "preferred_classes": expected_recipe_classes,
            "required_signals": expected_recipe_signals,
        },
        "observed_visual_recipe": {
            "matched_classes": [name for name in observed_classes if name in expected_recipe_classes],
            "matched_signals": [name for name in observed_signals if name in expected_recipe_signals],
        },
        "visual_recipe_status": visual_recipe_status if expected_recipe_name else "n/a",
        "status": status,
        "findings": findings,
    }


def _slide_chunks(markdown: str) -> list[str]:
    text = markdown.strip()
    if not text:
        return []
    first_slide_frontmatter = _extract_first_slide_frontmatter_from_global(text)
    body = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", text, count=1, flags=re.DOTALL)
    if not body.strip():
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


def _deck_signatures(slides: list[str]) -> list[str]:
    return [_slide_signature(slide) for slide in slides]


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


def _extract_layout_name(slide: str) -> str | None:
    frontmatter = _frontmatter_block(slide)
    if not frontmatter:
        return None
    match = re.search(r"^\s*layout:\s*([A-Za-z0-9_-]+)\s*$", frontmatter, re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


def _observed_patterns(slide: str) -> list[str]:
    patterns: list[str] = []
    layout_name = _extract_layout_name(slide)
    if layout_name:
        patterns.append(layout_name)
    if "```mermaid" in slide:
        patterns.append("mermaid")
    if re.search(r"^\s*>\s+", slide, re.MULTILINE):
        patterns.append("quote")
    if "|" in slide and re.search(r"^\s*\|.*\|\s*$", slide, re.MULTILINE):
        patterns.append("table")
    if "<div" in slide and "grid" in slide:
        patterns.append("div-grid")
    if "::" in slide:
        patterns.append("callout")
    return patterns


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


def _observed_signals(
    slide: str,
    observed_layout: str | None,
    observed_patterns: list[str],
    observed_classes: list[str],
) -> list[str]:
    body = _strip_slide_frontmatter(slide)
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    signals: set[str] = set()
    if observed_layout in {"cover", "center", "end", "two-cols"}:
        signals.add(observed_layout)
    if re.search(r"^\s*#\s+", body, re.MULTILINE):
        signals.add("hero-title")
    non_heading = [line for line in lines if not line.startswith("#")]
    if non_heading and len(non_heading[0]) <= 120:
        signals.add("short-subtitle")
    if any(name.startswith("deck-") for name in observed_classes):
        signals.add("recipe-class")
    if "quote" in observed_patterns or "callout" in observed_patterns:
        signals.add("quote-or-callout")
    if 2 <= _bullet_count(slide) <= 4:
        signals.add("compact-bullets")
    if any(name in observed_patterns for name in ("mermaid", "table", "div-grid")):
        signals.add("visual-structure")
        signals.add("focus-block")
    lower = body.lower()
    if any(token in lower for token in ("takeaway", "next step", "next steps", "下一步", "总结", "结论")):
        signals.add("next-step-or-takeaway")
        signals.add("closing-line")
    if any(token in lower for token in ("建议", "recommend", "decision")):
        signals.add("decision-headline")
    if _bullet_count(slide) >= 2:
        signals.add("action-list")
    if observed_layout == "two-cols" or "table" in observed_patterns or "::left::" in body or "::right::" in body:
        signals.add("split-compare")
    if re.search(r"^\s*###?\s+", body, re.MULTILINE) or "::left::" in body or "::right::" in body:
        signals.add("contrast-labels")
    if any(token in lower for token in ("要点", "核心", "takeaway", "why it matters")):
        signals.add("model-takeaway")
    return sorted(signals)


def _visual_recipe_status(
    *,
    role: str,
    expected_classes: list[str],
    expected_signals: list[str],
    observed_classes: list[str],
    observed_signals: list[str],
) -> str:
    matched_classes = [name for name in observed_classes if name in expected_classes]
    matched_signals = [name for name in observed_signals if name in expected_signals]
    if matched_classes and matched_signals:
        return "matched"
    if role == "cover" and "hero-title" in observed_signals and "short-subtitle" in observed_signals:
        return "weak"
    if role == "comparison" and "split-compare" in observed_signals:
        return "weak"
    if role == "closing" and "next-step-or-takeaway" in observed_signals:
        return "weak"
    if matched_classes or matched_signals:
        return "weak"
    return "missing"


def _visual_recipe_summary(slide_reports: list[dict[str, Any]]) -> dict[str, Any]:
    matched = 0
    weak = 0
    missing = 0
    expected: list[str] = []
    for report in slide_reports:
        recipe = report.get("expected_visual_recipe") or {}
        if isinstance(recipe, dict):
            name = str(recipe.get("name") or "").strip()
            if name:
                expected.append(name)
        status = str(report.get("visual_recipe_status") or "").strip().lower()
        if status == "matched":
            matched += 1
        elif status == "weak":
            weak += 1
        elif status == "missing":
            missing += 1
    return {
        "expected_recipe_names": expected,
        "matched_recipe_count": matched,
        "weak_recipe_count": weak,
        "missing_recipe_count": missing,
    }


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
    return heading_like and _bullet_count(slide) <= 1 and len(lines) <= 5


def _looks_like_closing(slide: str) -> bool:
    body = _strip_slide_frontmatter(slide)
    lower = body.lower()
    if any(token in lower for token in ("总结", "展望", "下一步", "结论", "next step", "takeaway", "summary")):
        return True
    return _bullet_count(body) <= 3 and len([line for line in body.splitlines() if line.strip()]) <= 6


def _has_strong_closing_signal(slide: str) -> bool:
    lower = _strip_slide_frontmatter(slide).lower()
    markers = ("下一步", "结论", "总结", "takeaway", "next step", "summary", "action", "decision")
    return any(marker in lower for marker in markers) or "layout: end" in slide.lower()


def _looks_comparison_like(slide: str) -> bool:
    body = _strip_slide_frontmatter(slide)
    return (
        "|" in body
        or "vs" in body.lower()
        or "对比" in body
        or "before" in body.lower()
        or _extract_layout_name(slide) == "two-cols"
        or "::left::" in body
        or "::right::" in body
    )


def _looks_flat_framework(slide: str) -> bool:
    return _bullet_count(slide) >= 4 and not _has_visual_structure(slide)


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


if __name__ == "__main__":
    raise SystemExit(main())

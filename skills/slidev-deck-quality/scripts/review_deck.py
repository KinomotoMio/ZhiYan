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

    slides = _slide_chunks(markdown)
    if not slides:
        issues.append({"code": "empty_deck", "message": "Deck markdown does not contain any body slides."})
        return _result(False, issues, warnings, [], slide_reports, expected_slide_count=0, actual_slide_count=0)

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
) -> dict[str, Any]:
    passed_slides = sum(1 for report in slide_reports if report.get("status") == "pass")
    failed_slides = sum(1 for report in slide_reports if report.get("status") == "failed")
    warning_slides = sum(1 for report in slide_reports if report.get("status") == "warning")
    return {
        "ok": ok,
        "issues": issues,
        "warnings": warnings,
        "signatures": signatures,
        "slide_reports": slide_reports,
        "contract_summary": {
            "expected_slide_count": expected_slide_count,
            "actual_slide_count": actual_slide_count,
            "hard_issue_count": len(issues),
            "warning_count": len(warnings),
            "passed_slides": passed_slides,
            "warning_slides": warning_slides,
            "failed_slides": failed_slides,
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
    title = str(item.get("title") or f"Slide {slide_number}").strip() if isinstance(item, dict) else f"Slide {slide_number}"
    findings: list[dict[str, str]] = []

    def add_issue(code: str, message: str) -> None:
        finding = {"severity": "issue", "code": code, "message": message}
        findings.append(finding)
        issues.append({"code": code, "message": message})

    def add_warning(code: str, message: str) -> None:
        finding = {"severity": "warning", "code": code, "message": message}
        findings.append(finding)
        warnings.append({"code": code, "message": message})

    if role == "cover":
        if not _looks_like_cover(slide):
            add_issue("cover_role_mismatch", f"Slide `{title}` is tagged cover but does not read like a cover slide.")
    elif role == "closing":
        if not _looks_like_closing(slide):
            add_issue(
                "closing_role_mismatch",
                f"Slide `{title}` is tagged closing but lacks a takeaway, summary, or next-step structure.",
            )
        elif not _has_strong_closing_signal(slide):
            add_warning("weak_closing", f"Slide `{title}` closes the deck but the closing signal is still weak.")
    elif role == "comparison":
        if not _looks_comparison_like(slide):
            add_issue(
                "comparison_role_mismatch",
                f"Slide `{title}` is tagged comparison but lacks a clear compare structure.",
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
    elif role in {"context", "detail"} and _bullet_count(slide) >= 5 and not _has_visual_structure(slide):
        add_warning(
            "dense_context_or_detail",
            f"Slide `{title}` is dense and mostly flat bullets; consider trimming or adding one structural cue.",
        )

    status = "pass"
    if any(finding["severity"] == "issue" for finding in findings):
        status = "failed"
    elif findings:
        status = "warning"

    return {
        "slide_number": slide_number,
        "title": title,
        "role": role or None,
        "status": status,
        "findings": findings,
    }


def _slide_chunks(markdown: str) -> list[str]:
    text = markdown.strip()
    if not text:
        return []
    body = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", text, count=1, flags=re.DOTALL)
    return [chunk.strip() for chunk in re.split(r"\n---\n", body) if chunk.strip()]


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
    return heading_like and _bullet_count(slide) <= 1 and len(lines) <= 5


def _looks_like_closing(slide: str) -> bool:
    lower = slide.lower()
    if any(token in lower for token in ("总结", "展望", "下一步", "结论", "next step", "takeaway", "summary")):
        return True
    return _bullet_count(slide) <= 3 and len([line for line in slide.splitlines() if line.strip()]) <= 6


def _has_strong_closing_signal(slide: str) -> bool:
    lower = slide.lower()
    markers = ("下一步", "结论", "总结", "takeaway", "next step", "summary", "action", "decision")
    return any(marker in lower for marker in markers) or "layout: end" in lower


def _looks_comparison_like(slide: str) -> bool:
    return "|" in slide or "vs" in slide.lower() or "对比" in slide or "before" in slide.lower()


def _looks_flat_framework(slide: str) -> bool:
    return _bullet_count(slide) >= 4 and not _has_visual_structure(slide)


if __name__ == "__main__":
    raise SystemExit(main())

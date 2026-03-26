#!/usr/bin/env python3
"""Review Slidev deck structure and selected-reference fidelity."""

from __future__ import annotations

import json
import re
import sys
from typing import Any

CONTRAST_FAIL_THRESHOLD = 3.0
CONTRAST_WARN_THRESHOLD = 4.5


def main() -> int:
    payload = json.load(sys.stdin)
    parameters = payload.get("parameters") or {}
    markdown = str(parameters.get("markdown") or "")
    outline_items = parameters.get("outline_items") or []
    selected_style = parameters.get("selected_style") or {}
    selected_theme = parameters.get("selected_theme") or {}
    selected_layouts = parameters.get("selected_layouts") or []
    selected_blocks = parameters.get("selected_blocks") or []
    page_briefs = parameters.get("page_briefs") or []
    deck_chrome = parameters.get("deck_chrome") or {}
    result = review_deck(
        markdown=markdown,
        outline_items=outline_items,
        selected_style=selected_style,
        selected_theme=selected_theme,
        selected_layouts=selected_layouts,
        selected_blocks=selected_blocks,
        page_briefs=page_briefs,
        deck_chrome=deck_chrome,
    )
    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


def review_deck(
    *,
    markdown: str,
    outline_items: Any,
    selected_style: Any = None,
    selected_theme: Any = None,
    selected_layouts: Any = None,
    selected_blocks: Any = None,
    page_briefs: Any = None,
    deck_chrome: Any = None,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    slide_reports: list[dict[str, Any]] = []
    normalized_markdown, normalization = _normalize_slidev_composition(markdown)
    if normalization.get("blank_first_slide_detected"):
        warnings.append(
            {
                "code": "blank_first_slide_normalized",
                "message": "Detected an empty first-slide pattern and normalized the first slide frontmatter before review.",
            }
        )
    if normalization.get("double_separator_frontmatter_detected"):
        warnings.append(
            {
                "code": "double_separator_frontmatter_normalized",
                "message": "Detected duplicated slide separator/frontmatter fences and normalized them before review.",
            }
        )
    if int(normalization.get("stray_metadata_repaired_count") or 0) > 0:
        warnings.append(
            {
                "code": "stray_metadata_slide_normalized",
                "message": "Detected metadata-only stray slides and compacted them into neighboring slides before review.",
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
            markdown=normalized_markdown,
            selected_style=_mapping(selected_style),
            selected_theme=_mapping(selected_theme),
            deck_chrome=_mapping(deck_chrome),
            expected_slide_count=0,
            actual_slide_count=0,
            contrast_summary=_empty_contrast_summary(),
            blank_first_slide_detected=bool(normalization.get("blank_first_slide_detected")),
            stray_metadata_repaired_count=int(normalization.get("stray_metadata_repaired_count") or 0),
            empty_slide_repaired_count=int(normalization.get("empty_slide_repaired_count") or 0),
        )

    if not isinstance(outline_items, list) or not outline_items:
        issues.append({"code": "missing_outline_context", "message": "Deck review requires a valid outline context."})
        contrast_summary = _contrast_summary(
            slides=slides,
            selected_style=_mapping(selected_style),
            selected_theme=_mapping(selected_theme),
            slide_reports=[],
        )
        return _result(
            False,
            issues,
            warnings,
            _deck_signatures(slides),
            slide_reports,
            markdown=normalized_markdown,
            selected_style=_mapping(selected_style),
            selected_theme=_mapping(selected_theme),
            deck_chrome=_mapping(deck_chrome),
            expected_slide_count=0,
            actual_slide_count=len(slides),
            contrast_summary=contrast_summary,
            blank_first_slide_detected=bool(normalization.get("blank_first_slide_detected")),
            stray_metadata_repaired_count=int(normalization.get("stray_metadata_repaired_count") or 0),
            empty_slide_repaired_count=int(normalization.get("empty_slide_repaired_count") or 0),
        )

    selected_layout_map = _selected_layout_map(selected_layouts)
    selected_block_map = _selected_block_map(selected_blocks)
    page_brief_map = _page_brief_map(page_briefs)

    if len(outline_items) != len(slides):
        issues.append(
            {
                "code": "outline_slide_count_mismatch",
                "message": f"Deck has {len(slides)} slides, but outline tracks {len(outline_items)}.",
            }
        )

    for slide_number, slide in enumerate(slides, start=1):
        item = outline_items[slide_number - 1] if slide_number - 1 < len(outline_items) else {}
        slide_reports.append(
            _review_slide(
                slide_number=slide_number,
                slide=slide,
                item=item,
                selected_layout=selected_layout_map.get(slide_number, {}),
                selected_blocks=selected_block_map.get(slide_number, []),
                page_brief=page_brief_map.get(slide_number, {}),
                issues=issues,
                warnings=warnings,
            )
        )

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

    theme_fidelity_summary = _theme_fidelity_summary(
        markdown=normalized_markdown,
        slide_reports=slide_reports,
        selected_style=_mapping(selected_style),
        selected_theme=_mapping(selected_theme),
        deck_chrome=_mapping(deck_chrome),
    )
    if str(theme_fidelity_summary.get("status") or "") == "weak":
        warnings.append(
            {
                "code": "theme_recipe_weak",
                "message": "Deck stays structurally valid, but the selected theme baseline and recipe scaffold still read weakly.",
            }
        )
    if (_mapping(selected_style) or _mapping(deck_chrome)) and not bool(
        (theme_fidelity_summary.get("observed_theme_markers") or {}).get("shared_visual_scaffold_present")
    ):
        warnings.append(
            {
                "code": "shared_visual_scaffold_missing",
                "message": "Deck is missing the shared visual scaffold block, so semantic recipe classes may still render like plain markdown.",
            }
        )
    if int((theme_fidelity_summary.get("observed_theme_markers") or {}).get("ad_hoc_inline_style_count") or 0) > 2:
        warnings.append(
            {
                "code": "too_much_ad_hoc_inline_style",
                "message": "Deck relies on too many ad-hoc inline styles; prefer theme/layout/class-driven presentation structure.",
            }
        )
    contrast_summary = _contrast_summary(
        slides=slides,
        selected_style=_mapping(selected_style),
        selected_theme=_mapping(selected_theme),
        slide_reports=slide_reports,
    )
    fail_slides = [entry for entry in (contrast_summary.get("slides") or []) if entry.get("status") == "fail"]
    warn_slides = [entry for entry in (contrast_summary.get("slides") or []) if entry.get("status") == "warn"]
    if fail_slides:
        issues.append(
            {
                "code": "low_contrast_fail",
                "message": (
                    f"{len(fail_slides)} slide(s) have insufficient text/background contrast "
                    f"(< {CONTRAST_FAIL_THRESHOLD:.1f}): {_contrast_slide_examples(fail_slides)}."
                ),
            }
        )
    if warn_slides:
        warnings.append(
            {
                "code": "low_contrast_warn",
                "message": (
                    f"{len(warn_slides)} slide(s) have borderline text/background contrast "
                    f"({CONTRAST_FAIL_THRESHOLD:.1f}-{CONTRAST_WARN_THRESHOLD:.1f}): {_contrast_slide_examples(warn_slides)}."
                ),
            }
        )

    return _result(
        not issues,
        issues,
        warnings,
        signatures,
        slide_reports,
        markdown=normalized_markdown,
        selected_style=_mapping(selected_style),
        selected_theme=_mapping(selected_theme),
        deck_chrome=_mapping(deck_chrome),
        expected_slide_count=len(outline_items),
        actual_slide_count=len(slides),
        contrast_summary=contrast_summary,
        blank_first_slide_detected=bool(normalization.get("blank_first_slide_detected")),
        stray_metadata_repaired_count=int(normalization.get("stray_metadata_repaired_count") or 0),
        empty_slide_repaired_count=int(normalization.get("empty_slide_repaired_count") or 0),
    )


def _result(
    ok: bool,
    issues: list[dict[str, str]],
    warnings: list[dict[str, str]],
    signatures: list[str],
    slide_reports: list[dict[str, Any]],
    *,
    markdown: str,
    selected_style: dict[str, Any],
    selected_theme: dict[str, Any],
    deck_chrome: dict[str, Any],
    expected_slide_count: int,
    actual_slide_count: int,
    contrast_summary: dict[str, Any],
    blank_first_slide_detected: bool,
    stray_metadata_repaired_count: int,
    empty_slide_repaired_count: int,
) -> dict[str, Any]:
    passed_slides = sum(1 for report in slide_reports if report.get("status") == "pass")
    failed_slides = sum(1 for report in slide_reports if report.get("status") == "failed")
    warning_slides = sum(1 for report in slide_reports if report.get("status") == "warning")
    visual_recipe_summary = _visual_recipe_summary(slide_reports)
    reference_fidelity_summary = _reference_fidelity_summary(slide_reports)
    page_brief_fidelity_summary = _page_brief_fidelity_summary(slide_reports)
    deck_chrome_usage_summary = _deck_chrome_usage_summary(slide_reports, deck_chrome)
    presentation_feel_summary = _presentation_feel_summary(slide_reports, warnings)
    theme_fidelity_summary = _theme_fidelity_summary(
        markdown=markdown,
        slide_reports=slide_reports,
        selected_style=selected_style,
        selected_theme=selected_theme,
        deck_chrome=deck_chrome,
    )
    return {
        "ok": ok,
        "issues": issues,
        "warnings": warnings,
        "signatures": signatures,
        "slide_reports": slide_reports,
        "visual_recipe_summary": visual_recipe_summary,
        "reference_fidelity_summary": reference_fidelity_summary,
        "page_brief_fidelity_summary": page_brief_fidelity_summary,
        "deck_chrome_usage_summary": deck_chrome_usage_summary,
        "presentation_feel_summary": presentation_feel_summary,
        "theme_fidelity_summary": theme_fidelity_summary,
        "contrast_summary": contrast_summary,
        "blank_first_slide_detected": blank_first_slide_detected,
        "stray_metadata_repaired_count": stray_metadata_repaired_count,
        "empty_slide_repaired_count": empty_slide_repaired_count,
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
            "matched_reference_recipes": reference_fidelity_summary["matched_slide_count"],
            "weak_reference_recipes": reference_fidelity_summary["weak_slide_count"],
            "matched_page_briefs": page_brief_fidelity_summary["matched_slide_count"],
            "weak_page_briefs": page_brief_fidelity_summary["weak_slide_count"],
            "contrast_status": str(contrast_summary.get("status") or "unknown"),
            "contrast_fail_slides": int(contrast_summary.get("fail_slide_count") or 0),
            "contrast_warn_slides": int(contrast_summary.get("warn_slide_count") or 0),
        },
    }


def _presentation_feel_summary(
    slide_reports: list[dict[str, Any]],
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    warning_codes = [
        str(warning.get("code") or "").strip()
        for warning in warnings
        if str(warning.get("code") or "").strip()
    ]
    document_like_codes = [code for code in warning_codes if code.startswith("document_like_")]
    crowding_codes = [code for code in warning_codes if code in {"bullet_dominant_deck", "dense_context_or_detail"}]
    visual_anchor_codes = [
        code
        for code in warning_codes
        if code in {"selected_reference_recipe_weak", "selected_reference_recipe_missing", "theme_recipe_weak"}
    ]
    signal_codes = sorted(set(document_like_codes + crowding_codes + visual_anchor_codes))
    status = "weak" if signal_codes else "matched"
    return {
        "status": status,
        "slide_count": len(slide_reports),
        "document_like_warning_count": len(document_like_codes),
        "crowding_warning_count": len(crowding_codes),
        "visual_anchor_warning_count": len(visual_anchor_codes),
        "signal_count": len(signal_codes),
        "signal_codes": signal_codes,
    }


def _review_slide(
    *,
    slide_number: int,
    slide: str,
    item: Any,
    selected_layout: dict[str, Any],
    selected_blocks: list[dict[str, Any]],
    page_brief: dict[str, Any],
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
    preferred_composition = str(page_brief.get("preferred_composition") or "").strip()
    must_keep_signals = _string_list(page_brief.get("must_keep_signals"))
    must_avoid_patterns = _string_list(page_brief.get("must_avoid_patterns"))

    expected_recipe_name = str(selected_layout.get("recipe_name") or visual_hint.get("name") or "")
    expected_recipe_classes = _string_list(selected_layout.get("required_classes")) or [
        str(name).strip() for name in (visual_hint.get("preferred_classes") or []) if str(name).strip()
    ]
    expected_recipe_signals = _string_list(selected_layout.get("required_visual_signals")) or [
        str(name).strip() for name in (visual_hint.get("required_signals") or []) if str(name).strip()
    ]
    expected_patterns = _string_list(selected_layout.get("required_patterns"))
    expected_block_signals = sorted(
        {
            signal
            for block in selected_blocks
            if isinstance(block, dict)
            for signal in _string_list(block.get("required_signals"))
        }
    )
    forbidden_patterns = _string_list(selected_layout.get("forbidden_patterns"))
    forbidden_hits = _forbidden_pattern_hits(slide=slide, forbidden_patterns=forbidden_patterns)
    visual_recipe_status = _visual_recipe_status(
        role=role,
        expected_classes=expected_recipe_classes,
        expected_signals=expected_recipe_signals,
        observed_classes=observed_classes,
        observed_signals=observed_signals,
    )
    reference_fidelity = _reference_fidelity(
        preferred_layout=str(selected_layout.get("preferred_layout") or "").strip() or None,
        expected_patterns=expected_patterns,
        expected_classes=expected_recipe_classes,
        expected_block_signals=expected_block_signals,
        forbidden_hits=forbidden_hits,
        observed_layout=observed_layout,
        observed_patterns=observed_patterns,
        observed_classes=observed_classes,
        observed_signals=observed_signals,
    )
    page_brief_fidelity = _page_brief_fidelity(
        preferred_composition=preferred_composition,
        must_keep_signals=must_keep_signals,
        must_avoid_patterns=must_avoid_patterns,
        observed_patterns=observed_patterns,
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
            add_warning("cover_role_mismatch", f"Slide `{title}` is tagged cover but does not read like a cover slide.")
            add_warning("document_like_cover", f"Slide `{title}` still looks like a document title page instead of a strong presentation cover.")
        elif observed_layout not in {"cover", "center"}:
            if visual_recipe_status != "matched" and "recipe-class" not in observed_signals:
                add_warning("document_like_cover", f"Slide `{title}` still looks like a document title page instead of a strong presentation cover.")
            else:
                add_warning("cover_native_layout_missing", f"Slide `{title}` reads like cover but does not use `layout: cover` or `layout: center`.")
    elif role == "closing":
        if not _looks_like_closing(slide):
            add_issue(
                "closing_role_mismatch",
                f"Slide `{title}` is tagged closing but lacks a takeaway, summary, or next-step structure.",
            )
        elif "verdict-line" not in observed_signals:
            add_warning("document_like_closing", f"Slide `{title}` closes semantically, but still reads like a document ending instead of a presentation closing slide.")
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
        elif "contrast-labels" not in observed_signals or "verdict-line" not in observed_signals:
            add_warning("document_like_comparison", f"Slide `{title}` compares content, but still lacks the stronger split/contrast cues of a presentation comparison slide.")
    elif role == "framework":
        if _looks_flat_framework(slide):
            add_issue(
                "framework_role_too_flat",
                f"Slide `{title}` is tagged framework but reads like a flat bullet dump instead of a structured model.",
            )
        elif "section-kicker" not in observed_signals or "model-takeaway" not in observed_signals:
            add_warning("document_like_framework", f"Slide `{title}` is structurally valid, but still reads more like a document section than a framed model slide.")
        elif not {"mermaid", "table", "div-grid"}.intersection(observed_patterns):
            add_warning(
                "framework_native_pattern_missing",
                f"Slide `{title}` is a framework page but does not yet use a strong native structure such as Mermaid, table, or grid.",
            )
    elif role == "context":
        if not ({"quote-or-callout", "section-kicker"} & set(observed_signals)):
            add_warning("document_like_context", f"Slide `{title}` sets context semantically, but still reads like a report section instead of a presentation setup slide.")
        if "why-now-framing" not in observed_signals:
            add_warning("context_why_now_missing", f"Slide `{title}` lacks a clear why-now framing signal.")
        if _bullet_count(slide) >= 5 and not _has_visual_structure(slide):
            add_warning(
                "dense_context_or_detail",
                f"Slide `{title}` is dense and mostly flat bullets; consider trimming or adding one structural cue.",
            )
    elif role == "detail":
        if _detail_over_dense(slide):
            add_warning("detail_over_dense", f"Slide `{title}` is too dense for a detail page; reduce text density and keep one focus block.")
        if not _looks_detail_single_focus(slide):
            add_warning("detail_multi_claim_drift", f"Slide `{title}` drifts into multiple claims instead of a single-focus explainer.")
        if "single-claim" not in observed_signals or "focus-block" not in observed_signals:
            add_warning("document_like_detail", f"Slide `{title}` is structurally legal but still reads like document prose instead of a focused explainer.")
    elif role == "recommendation":
        if "decision-headline" not in observed_signals:
            add_warning("recommendation_decision_missing", f"Slide `{title}` lacks a clear decision headline before action items.")
        if "prioritized-actions" not in observed_signals:
            add_warning("recommendation_prioritization_missing", f"Slide `{title}` lists actions but does not show clear prioritization.")
        if _looks_plain_recommendation_list(slide):
            add_warning("document_like_recommendation", f"Slide `{title}` still reads like a plain list instead of a decision + action-path page.")

    if forbidden_hits:
        add_warning(
            "selected_reference_forbidden_pattern",
            f"Slide `{title}` violates selected reference anti-patterns: {', '.join(forbidden_hits)}.",
        )

    if expected_recipe_name and reference_fidelity["status"] != "matched":
        code = "selected_reference_recipe_weak" if reference_fidelity["status"] == "weak" else "selected_reference_recipe_missing"
        add_warning(
            code,
            f"Slide `{title}` does not yet fully realize selected layout/block recipe `{expected_recipe_name}`.",
        )

    if expected_recipe_name and visual_recipe_status != "matched":
        code = f"{role or 'slide'}_visual_recipe_weak"
        add_warning(
            code,
            f"Slide `{title}` is structurally acceptable but does not yet fully realize the `{expected_recipe_name}` visual recipe.",
        )

    if preferred_composition and page_brief_fidelity["status"] != "matched":
        add_warning(
            "missing_page_brief_composition",
            f"Slide `{title}` does not yet fully realize the page-brief composition `{preferred_composition}`.",
        )
        if preferred_composition == "metric-stack":
            add_warning(
                "document_like_metric_page",
                f"Slide `{title}` still reads like a document setup page instead of a metric-led urgency slide.",
            )
        elif preferred_composition == "map-with-insights":
            add_warning(
                "document_like_map_page",
                f"Slide `{title}` still reads flat; it should land as a map-with-insights / risk-map style page.",
            )
        elif preferred_composition == "action-path":
            add_warning(
                "document_like_action_page",
                f"Slide `{title}` still reads like bullets instead of an action-path / next-step slide.",
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
        "selected_layout": {
            "recipe_name": str(selected_layout.get("recipe_name") or "") or None,
            "preferred_layout": str(selected_layout.get("preferred_layout") or "") or None,
            "required_patterns": expected_patterns,
            "required_classes": expected_recipe_classes,
            "forbidden_patterns": forbidden_patterns,
        },
        "selected_blocks": [str(block.get("name") or "") for block in selected_blocks if isinstance(block, dict)],
        "page_brief": {
            "page_goal": str(page_brief.get("page_goal") or "") or None,
            "narrative_job": str(page_brief.get("narrative_job") or "") or None,
            "hero_fact_or_claim": str(page_brief.get("hero_fact_or_claim") or "") or None,
            "preferred_composition": preferred_composition or None,
            "must_keep": _string_list(page_brief.get("must_keep")),
            "must_avoid": _string_list(page_brief.get("must_avoid")),
        },
        "observed_visual_recipe": {
            "matched_classes": [name for name in observed_classes if name in expected_recipe_classes],
            "matched_signals": [name for name in observed_signals if name in expected_recipe_signals],
        },
        "visual_recipe_status": visual_recipe_status if expected_recipe_name else "n/a",
        "reference_fidelity": reference_fidelity,
        "page_brief_fidelity": page_brief_fidelity,
        "status": status,
        "findings": findings,
    }


def _selected_layout_map(selected_layouts: Any) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    if not isinstance(selected_layouts, list):
        return result
    for item in selected_layouts:
        if not isinstance(item, dict):
            continue
        result[int(item.get("slide_number") or 0)] = dict(item)
    return result


def _selected_block_map(selected_blocks: Any) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = {}
    if not isinstance(selected_blocks, list):
        return result
    for item in selected_blocks:
        if not isinstance(item, dict):
            continue
        result[int(item.get("slide_number") or 0)] = [
            dict(block) for block in (item.get("blocks") or []) if isinstance(block, dict)
        ]
    return result


def _page_brief_map(page_briefs: Any) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    if not isinstance(page_briefs, list):
        return result
    for item in page_briefs:
        if not isinstance(item, dict):
            continue
        result[int(item.get("slide_number") or 0)] = dict(item)
    return result


def _reference_fidelity(
    *,
    preferred_layout: str | None,
    expected_patterns: list[str],
    expected_classes: list[str],
    expected_block_signals: list[str],
    forbidden_hits: list[str],
    observed_layout: str | None,
    observed_patterns: list[str],
    observed_classes: list[str],
    observed_signals: list[str],
) -> dict[str, Any]:
    matched_layout = bool(preferred_layout) and observed_layout == preferred_layout
    matched_patterns = [pattern for pattern in expected_patterns if pattern in observed_patterns or pattern in observed_signals]
    matched_classes = [name for name in expected_classes if name in observed_classes]
    matched_block_signals = [signal for signal in expected_block_signals if signal in observed_signals]
    if forbidden_hits:
        status = "forbidden"
    elif (not preferred_layout or matched_layout) and (matched_classes or matched_patterns or matched_block_signals):
        status = "matched"
    elif matched_classes or matched_patterns or matched_block_signals or matched_layout:
        status = "weak"
    else:
        status = "missing"
    return {
        "status": status,
        "matched_layout": matched_layout,
        "matched_patterns": matched_patterns,
        "matched_classes": matched_classes,
        "matched_block_signals": matched_block_signals,
        "forbidden_patterns": forbidden_hits,
    }


def _reference_fidelity_summary(slide_reports: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"matched": 0, "weak": 0, "missing": 0, "forbidden": 0}
    layout_names: list[str] = []
    block_names: set[str] = set()
    plain_like = 0
    role_summary: dict[str, dict[str, int]] = {}
    for report in slide_reports:
        reference = report.get("reference_fidelity") or {}
        status = str(reference.get("status") or "missing")
        if status in counts:
            counts[status] += 1
        role = str(report.get("role") or "").strip()
        if role:
            bucket = role_summary.setdefault(role, {"matched": 0, "weak": 0, "missing": 0, "forbidden": 0, "total": 0})
            bucket["total"] += 1
            if status in {"matched", "weak", "missing", "forbidden"}:
                bucket[status] += 1
        layout = report.get("selected_layout") or {}
        if isinstance(layout, dict):
            name = str(layout.get("recipe_name") or "").strip()
            if name:
                layout_names.append(name)
        for name in report.get("selected_blocks") or []:
            if str(name).strip():
                block_names.add(str(name).strip())
        if status in {"missing", "forbidden"}:
            plain_like += 1
    return {
        "selected_layout_names": layout_names,
        "selected_block_names": sorted(block_names),
        "matched_slide_count": counts["matched"],
        "weak_slide_count": counts["weak"],
        "missing_slide_count": counts["missing"],
        "forbidden_slide_count": counts["forbidden"],
        "plain_like_slide_count": plain_like,
        "role_skeleton_summary": role_summary,
    }


def _page_brief_fidelity(
    *,
    preferred_composition: str,
    must_keep_signals: list[str],
    must_avoid_patterns: list[str],
    observed_patterns: list[str],
    observed_classes: list[str],
    observed_signals: list[str],
) -> dict[str, Any]:
    matched_keep = [signal for signal in must_keep_signals if signal in observed_signals or signal in observed_patterns]
    observed_compositions = set(observed_patterns) | set(observed_classes) | set(observed_signals)
    composition_matched = bool(preferred_composition) and preferred_composition in observed_compositions
    avoid_hits = [pattern for pattern in must_avoid_patterns if pattern in observed_patterns or pattern in observed_signals]
    if avoid_hits:
        status = "forbidden"
    elif composition_matched and matched_keep:
        status = "matched"
    elif composition_matched or matched_keep:
        status = "weak"
    elif preferred_composition:
        status = "missing"
    else:
        status = "n/a"
    return {
        "status": status,
        "preferred_composition": preferred_composition or None,
        "composition_matched": composition_matched,
        "matched_keep_signals": matched_keep,
        "avoid_hits": avoid_hits,
    }


def _page_brief_fidelity_summary(slide_reports: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"matched": 0, "weak": 0, "missing": 0, "forbidden": 0}
    composition_counts: dict[str, int] = {}
    role_summary: dict[str, dict[str, int]] = {}
    for report in slide_reports:
        fidelity = report.get("page_brief_fidelity") or {}
        status = str(fidelity.get("status") or "missing")
        if status in counts:
            counts[status] += 1
        role = str(report.get("role") or "").strip()
        if role:
            bucket = role_summary.setdefault(role, {"matched": 0, "weak": 0, "missing": 0, "forbidden": 0, "total": 0})
            bucket["total"] += 1
            if status in {"matched", "weak", "missing", "forbidden"}:
                bucket[status] += 1
        composition = str((report.get("page_brief") or {}).get("preferred_composition") or "")
        if composition:
            composition_counts[composition] = composition_counts.get(composition, 0) + 1
    return {
        "matched_slide_count": counts["matched"],
        "weak_slide_count": counts["weak"],
        "missing_slide_count": counts["missing"],
        "forbidden_slide_count": counts["forbidden"],
        "composition_counts": composition_counts,
        "role_skeleton_summary": role_summary,
    }


def _deck_chrome_usage_summary(slide_reports: list[dict[str, Any]], deck_chrome: dict[str, Any]) -> dict[str, Any]:
    cue_counts = {
        "slide_topline_count": 0,
        "section_kicker_count": 0,
        "slide_subtitle_count": 0,
        "slide_footer_count": 0,
        "metric_stack_count": 0,
        "map_with_insights_count": 0,
        "compare_panel_count": 0,
        "action_path_count": 0,
    }
    for report in slide_reports:
        observed = set(report.get("observed_signals") or []) | set(report.get("observed_classes") or []) | set(
            report.get("observed_patterns") or []
        )
        cue_counts["slide_topline_count"] += int("slide-topline" in observed)
        cue_counts["section_kicker_count"] += int("section-kicker" in observed)
        cue_counts["slide_subtitle_count"] += int("slide-subtitle" in observed)
        cue_counts["slide_footer_count"] += int("slide-footer" in observed or "source-or-takeaway" in observed)
        cue_counts["metric_stack_count"] += int("metric-stack" in observed)
        cue_counts["map_with_insights_count"] += int("map-with-insights" in observed)
        cue_counts["compare_panel_count"] += int("compare-panel" in observed)
        cue_counts["action_path_count"] += int("action-path" in observed)
    return {
        "deck_label": str(deck_chrome.get("deck_label") or "") or None,
        "cue_counts": cue_counts,
        "shared_cues": _string_list(deck_chrome.get("shared_cues")),
    }


def _theme_fidelity_summary(
    *,
    markdown: str,
    slide_reports: list[dict[str, Any]],
    selected_style: dict[str, Any],
    selected_theme: dict[str, Any],
    deck_chrome: dict[str, Any],
) -> dict[str, Any]:
    selected_theme_name = str(selected_theme.get("theme") or selected_style.get("theme") or "seriph")
    observed_theme = _global_frontmatter_value(markdown, "theme") or None
    observed_frontmatter = _frontmatter_block(markdown)
    recipe_class_slides = sum(
        1 for report in slide_reports if any(str(name).startswith("deck-") for name in (report.get("observed_classes") or []))
    )
    recipe_class_count = sum(
        1 for report in slide_reports for name in (report.get("observed_classes") or []) if str(name).startswith("deck-")
    )
    inline_style_count = len(re.findall(r'style\s*=\s*"', markdown)) + len(re.findall(r"style\s*=\s*'", markdown))
    deck_scaffold_class = str(selected_style.get("deck_scaffold_class") or "").strip()
    theme_config_present = "themeconfig:" in observed_frontmatter.lower()
    shared_visual_scaffold_present = "slidev-shared-visual-scaffold" in markdown
    expects_shared_visual_scaffold = bool(selected_style or deck_chrome)
    semantic_primitive_count = len(
        re.findall(r'class="[^"]*(?:metric-card|map-panel|insight-card|compare-side|action-step|verdict-line)[^"]*"', markdown)
    )
    status = "matched"
    if observed_theme and observed_theme != selected_theme_name:
        status = "weak"
    if inline_style_count > max(2, len(slide_reports) // 2):
        status = "weak"
    if not recipe_class_slides:
        status = "weak"
    if deck_scaffold_class and deck_scaffold_class not in markdown:
        status = "weak"
    if selected_theme.get("theme_config") and not theme_config_present:
        status = "weak"
    if expects_shared_visual_scaffold and not shared_visual_scaffold_present:
        status = "weak"
    if deck_chrome and not any(
        signal in {"slide-topline", "section-kicker", "slide-footer"}
        for report in slide_reports
        for signal in (report.get("observed_signals") or [])
    ):
        status = "weak"
    return {
        "selected_style": str(selected_style.get("name") or "") or None,
        "selected_theme": selected_theme_name,
        "observed_theme": observed_theme,
        "theme_mode": str(selected_theme.get("theme_mode") or selected_style.get("theme_mode") or "") or None,
        "status": status,
        "observed_theme_markers": {
            "recipe_class_slides": recipe_class_slides,
            "recipe_class_count": recipe_class_count,
            "ad_hoc_inline_style_count": inline_style_count,
            "deck_scaffold_class_present": bool(deck_scaffold_class and deck_scaffold_class in markdown),
            "theme_config_present": theme_config_present,
            "shared_visual_scaffold_expected": expects_shared_visual_scaffold,
            "shared_visual_scaffold_present": shared_visual_scaffold_present,
            "semantic_primitive_count": semantic_primitive_count,
            "deck_chrome_detected": any(
                signal in {"slide-topline", "section-kicker", "slide-footer"}
                for report in slide_reports
                for signal in (report.get("observed_signals") or [])
            ),
        },
    }


def _contrast_summary(
    *,
    slides: list[str],
    selected_style: dict[str, Any],
    selected_theme: dict[str, Any],
    slide_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    if not slides:
        return _empty_contrast_summary()

    default_pair = _theme_default_contrast_pair(selected_style=selected_style, selected_theme=selected_theme)
    report_by_number = {
        int(report.get("slide_number") or 0): report for report in slide_reports if isinstance(report, dict)
    }
    summary_slides: list[dict[str, Any]] = []
    pass_count = 0
    warn_count = 0
    fail_count = 0
    unknown_count = 0

    for slide_number, slide in enumerate(slides, start=1):
        report = report_by_number.get(slide_number) or {}
        title = str(report.get("title") or f"Slide {slide_number}")
        checks = _collect_slide_contrast_checks(slide=slide, default_pair=default_pair)
        if not checks:
            summary_slides.append(
                {
                    "slide_number": slide_number,
                    "title": title,
                    "status": "unknown",
                    "check_count": 0,
                    "worst_ratio": None,
                    "worst_pair": None,
                }
            )
            unknown_count += 1
            continue

        worst = min(checks, key=lambda item: float(item.get("ratio") or 999.0))
        worst_ratio = float(worst.get("ratio") or 0.0)
        status = "pass"
        if worst_ratio < CONTRAST_FAIL_THRESHOLD:
            status = "fail"
            fail_count += 1
        elif worst_ratio < CONTRAST_WARN_THRESHOLD:
            status = "warn"
            warn_count += 1
        else:
            pass_count += 1
        summary_slides.append(
            {
                "slide_number": slide_number,
                "title": title,
                "status": status,
                "check_count": len(checks),
                "worst_ratio": round(worst_ratio, 2),
                "worst_pair": {
                    "foreground": str(worst.get("foreground") or ""),
                    "background": str(worst.get("background") or ""),
                    "source": str(worst.get("source") or ""),
                },
            }
        )

    status = "unknown"
    if fail_count > 0:
        status = "fail"
    elif warn_count > 0:
        status = "warn"
    elif pass_count > 0:
        status = "pass"

    return {
        "status": status,
        "thresholds": {
            "fail_below": CONTRAST_FAIL_THRESHOLD,
            "warn_below": CONTRAST_WARN_THRESHOLD,
        },
        "slide_count": len(slides),
        "pass_slide_count": pass_count,
        "warn_slide_count": warn_count,
        "fail_slide_count": fail_count,
        "unknown_slide_count": unknown_count,
        "slides": summary_slides,
    }


def _collect_slide_contrast_checks(
    *,
    slide: str,
    default_pair: tuple[tuple[int, int, int], tuple[int, int, int], str] | None,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    if default_pair is not None:
        fg, bg, source = default_pair
        checks.append(_contrast_check(fg=fg, bg=bg, source=source))

    frontmatter_fg, frontmatter_bg = _frontmatter_contrast_pair(slide=slide, default_pair=default_pair)
    if frontmatter_fg is not None and frontmatter_bg is not None:
        checks.append(_contrast_check(fg=frontmatter_fg, bg=frontmatter_bg, source="slide-frontmatter"))

    for style in re.findall(r"style\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", slide, flags=re.IGNORECASE | re.DOTALL):
        raw_style = style[0] or style[1]
        if not raw_style.strip():
            continue
        declarations = _parse_css_declarations(raw_style)
        fg = _extract_css_color(declarations.get("color"))
        bg = _extract_css_color(declarations.get("background-color")) or _extract_css_color(declarations.get("background"))
        if fg is None and default_pair is not None:
            fg = default_pair[0]
        if bg is None and default_pair is not None:
            bg = default_pair[1]
        if fg is None or bg is None:
            continue
        checks.append(_contrast_check(fg=fg, bg=bg, source="inline-style"))

    class_pair = _class_inferred_contrast_pair(_extract_classes(slide))
    if class_pair is not None:
        checks.append(_contrast_check(fg=class_pair[0], bg=class_pair[1], source="class-inference"))

    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for check in checks:
        key = (
            str(check.get("foreground") or ""),
            str(check.get("background") or ""),
            str(check.get("source") or ""),
        )
        unique[key] = check
    return list(unique.values())


def _frontmatter_contrast_pair(
    *,
    slide: str,
    default_pair: tuple[tuple[int, int, int], tuple[int, int, int], str] | None,
) -> tuple[tuple[int, int, int] | None, tuple[int, int, int] | None]:
    frontmatter = _frontmatter_block(slide)
    if not frontmatter:
        return None, None
    color_value = _frontmatter_scalar_value(frontmatter, "color") or _frontmatter_scalar_value(frontmatter, "textColor")
    bg_value = (
        _frontmatter_scalar_value(frontmatter, "backgroundColor")
        or _frontmatter_scalar_value(frontmatter, "background")
        or _frontmatter_scalar_value(frontmatter, "bg")
    )
    fg = _extract_css_color(color_value)
    bg = _extract_css_color(bg_value)
    if fg is None and default_pair is not None:
        fg = default_pair[0]
    if bg is None and default_pair is not None:
        bg = default_pair[1]
    return fg, bg


def _theme_default_contrast_pair(
    *,
    selected_style: dict[str, Any],
    selected_theme: dict[str, Any],
) -> tuple[tuple[int, int, int], tuple[int, int, int], str] | None:
    scaffold_tokens = selected_style.get("scaffold_tokens") if isinstance(selected_style.get("scaffold_tokens"), dict) else {}
    if not isinstance(scaffold_tokens, dict):
        scaffold_tokens = {}
    fg = _extract_css_color(str(scaffold_tokens.get("text") or ""))
    bg = _extract_css_color(str(scaffold_tokens.get("surface") or "")) or _extract_css_color(
        str(scaffold_tokens.get("surface_alt") or "")
    )
    if fg is not None and bg is not None:
        return fg, bg, "style-scaffold-tokens"

    mode_hint = " ".join(
        str(value or "").strip().lower()
        for value in (
            selected_theme.get("theme_mode"),
            selected_style.get("theme_mode"),
            selected_theme.get("palette"),
            selected_style.get("name"),
        )
        if str(value or "").strip()
    )
    if "dark" in mode_hint:
        return (245, 245, 245), (23, 23, 23), "theme-mode-inference"
    if mode_hint:
        return (23, 23, 23), (250, 250, 250), "theme-mode-inference"
    return None


def _class_inferred_contrast_pair(classes: list[str]) -> tuple[tuple[int, int, int], tuple[int, int, int]] | None:
    class_tokens = {str(token).strip().lower() for token in classes if str(token).strip()}
    if not class_tokens:
        return None
    dark_markers = ("dark", "night", "inverse", "invert")
    light_markers = ("light", "day", "paper")
    if any(any(marker in token for marker in dark_markers) for token in class_tokens):
        return (245, 245, 245), (23, 23, 23)
    if any(any(marker in token for marker in light_markers) for token in class_tokens):
        return (23, 23, 23), (250, 250, 250)
    return None


def _contrast_check(*, fg: tuple[int, int, int], bg: tuple[int, int, int], source: str) -> dict[str, Any]:
    return {
        "foreground": _rgb_to_hex(fg),
        "background": _rgb_to_hex(bg),
        "ratio": round(_contrast_ratio(fg, bg), 3),
        "source": source,
    }


def _contrast_ratio(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    fg_luminance = _relative_luminance(fg)
    bg_luminance = _relative_luminance(bg)
    lighter = max(fg_luminance, bg_luminance)
    darker = min(fg_luminance, bg_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for channel in rgb:
        normalized = max(0.0, min(255.0, float(channel))) / 255.0
        channels.append(normalized / 12.92 if normalized <= 0.03928 else ((normalized + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    red, green, blue = [max(0, min(255, int(value))) for value in rgb]
    return f"#{red:02X}{green:02X}{blue:02X}"


def _extract_css_color(raw_value: Any) -> tuple[int, int, int] | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    direct = _parse_css_color(value)
    if direct is not None:
        return direct
    for match in re.findall(
        r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b|rgba?\([^)]+\)|hsla?\([^)]+\)|\b[a-zA-Z]+\b",
        value,
        flags=re.IGNORECASE,
    ):
        parsed = _parse_css_color(match)
        if parsed is not None:
            return parsed
    return None


def _parse_css_color(value: str) -> tuple[int, int, int] | None:
    raw = value.strip().lower()
    if not raw or raw.startswith("var("):
        return None
    if raw.startswith("#"):
        token = raw[1:]
        if len(token) == 3 and re.fullmatch(r"[0-9a-f]{3}", token):
            return tuple(int(char * 2, 16) for char in token)  # type: ignore[return-value]
        if len(token) == 6 and re.fullmatch(r"[0-9a-f]{6}", token):
            return (int(token[0:2], 16), int(token[2:4], 16), int(token[4:6], 16))
        return None
    rgb_match = re.fullmatch(r"rgba?\(([^)]+)\)", raw)
    if rgb_match:
        parts = [part.strip() for part in rgb_match.group(1).split(",")]
        if len(parts) < 3:
            return None
        channels: list[int] = []
        for part in parts[:3]:
            if part.endswith("%"):
                try:
                    channels.append(int(round(float(part[:-1]) * 2.55)))
                except ValueError:
                    return None
            else:
                try:
                    channels.append(int(round(float(part))))
                except ValueError:
                    return None
        return tuple(max(0, min(255, channel)) for channel in channels)  # type: ignore[return-value]
    hsl_match = re.fullmatch(r"hsla?\(([^)]+)\)", raw)
    if hsl_match:
        parts = [part.strip() for part in hsl_match.group(1).split(",")]
        if len(parts) < 3:
            return None
        try:
            hue = float(parts[0].rstrip("deg")) % 360.0
            saturation = float(parts[1].rstrip("%")) / 100.0
            lightness = float(parts[2].rstrip("%")) / 100.0
        except ValueError:
            return None
        return _hsl_to_rgb(hue, saturation, lightness)

    named_colors = {
        "black": (0, 0, 0),
        "white": (255, 255, 255),
        "gray": (128, 128, 128),
        "grey": (128, 128, 128),
        "red": (255, 0, 0),
        "green": (0, 128, 0),
        "blue": (0, 0, 255),
        "yellow": (255, 255, 0),
        "orange": (255, 165, 0),
        "purple": (128, 0, 128),
        "teal": (0, 128, 128),
        "navy": (0, 0, 128),
    }
    return named_colors.get(raw)


def _hsl_to_rgb(hue: float, saturation: float, lightness: float) -> tuple[int, int, int]:
    chroma = (1.0 - abs(2.0 * lightness - 1.0)) * saturation
    hue_section = hue / 60.0
    secondary = chroma * (1.0 - abs(hue_section % 2.0 - 1.0))
    red = green = blue = 0.0
    if 0 <= hue_section < 1:
        red, green = chroma, secondary
    elif 1 <= hue_section < 2:
        red, green = secondary, chroma
    elif 2 <= hue_section < 3:
        green, blue = chroma, secondary
    elif 3 <= hue_section < 4:
        green, blue = secondary, chroma
    elif 4 <= hue_section < 5:
        red, blue = secondary, chroma
    elif 5 <= hue_section < 6:
        red, blue = chroma, secondary
    offset = lightness - chroma / 2.0
    return (
        int(round((red + offset) * 255)),
        int(round((green + offset) * 255)),
        int(round((blue + offset) * 255)),
    )


def _parse_css_declarations(raw_style: str) -> dict[str, str]:
    declarations: dict[str, str] = {}
    for fragment in raw_style.split(";"):
        if ":" not in fragment:
            continue
        key, value = fragment.split(":", 1)
        name = key.strip().lower()
        if not name:
            continue
        declarations[name] = value.strip()
    return declarations


def _contrast_slide_examples(entries: list[dict[str, Any]], *, limit: int = 3) -> str:
    samples = []
    for entry in entries[:limit]:
        slide_number = int(entry.get("slide_number") or 0)
        title = str(entry.get("title") or f"Slide {slide_number}")
        ratio = entry.get("worst_ratio")
        ratio_text = f"{float(ratio):.2f}" if isinstance(ratio, (int, float)) else "n/a"
        samples.append(f"#{slide_number} `{title}` ({ratio_text})")
    return ", ".join(samples)


def _empty_contrast_summary() -> dict[str, Any]:
    return {
        "status": "unknown",
        "thresholds": {
            "fail_below": CONTRAST_FAIL_THRESHOLD,
            "warn_below": CONTRAST_WARN_THRESHOLD,
        },
        "slide_count": 0,
        "pass_slide_count": 0,
        "warn_slide_count": 0,
        "fail_slide_count": 0,
        "unknown_slide_count": 0,
        "slides": [],
    }


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in (value or []) if str(item).strip()]


def _forbidden_pattern_hits(*, slide: str, forbidden_patterns: list[str]) -> list[str]:
    hits: list[str] = []
    lower = _strip_slide_frontmatter(slide).lower()
    for pattern in forbidden_patterns:
        if pattern == "plain-bullet-dump" and _bullet_count(slide) >= 4 and not _has_visual_structure(slide):
            hits.append(pattern)
        elif pattern == "unstyled-document-section" and _bullet_count(slide) >= 3 and not _has_visual_structure(slide):
            hits.append(pattern)
        elif pattern == "generic-thanks" and any(token in lower for token in ("thank you", "thanks", "q&a", "谢谢")):
            hits.append(pattern)
        elif pattern == "too-much-inline-style" and len(re.findall(r"style\s*=", slide)) > 2:
            hits.append(pattern)
    return hits


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
    markers = ("```mermaid", "layout:", "class:", "> ", "|", "::", "<div")
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
    lower = slide.lower()
    for token in ("metric-stack", "map-with-insights", "focus-explainer", "compare-panel", "action-path"):
        if token in lower:
            patterns.append(token)
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
    lower = body.lower()
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    signals: set[str] = set()
    first_heading_index = next((index for index, line in enumerate(lines) if line.startswith("#")), None)
    if observed_layout in {"cover", "center", "end", "two-cols"}:
        signals.add(observed_layout)
    if re.search(r"^\s*#\s+", body, re.MULTILINE):
        signals.add("hero-title")
        signals.add("short-positioning-line")
    if first_heading_index is not None and first_heading_index > 0:
        kicker = lines[first_heading_index - 1]
        if kicker and len(kicker) <= 48:
            signals.add("launch-kicker")
            signals.add("section-kicker")
    elif lines and not lines[0].startswith("#") and len(lines[0]) <= 48:
        signals.add("section-kicker")
    non_heading = [line for line in lines if not line.startswith("#")]
    if non_heading and len(non_heading[0]) <= 120:
        signals.add("short-subtitle")
    if any(name.startswith("deck-") for name in observed_classes):
        signals.add("recipe-class")
    if "slide-topline" in observed_classes:
        signals.add("slide-topline")
    if "section-kicker" in observed_classes:
        signals.add("section-kicker")
    if "slide-subtitle" in observed_classes:
        signals.add("slide-subtitle")
    if "slide-footer" in observed_classes:
        signals.add("slide-footer")
    if "quote" in observed_patterns or "callout" in observed_patterns:
        signals.add("quote-or-callout")
    if any(token in lower for token in ("why now", "why-now", "why it matters now", "为什么现在", "当下", "紧迫")):
        signals.add("why-now-framing")
    if 2 <= _bullet_count(slide) <= 4:
        signals.add("compact-bullets")
    if any(name in observed_patterns for name in ("mermaid", "table", "div-grid")):
        signals.add("visual-structure")
        signals.add("focus-block")
    if any(token in lower for token in ("takeaway", "next step", "next steps", "下一步", "总结", "结论")):
        signals.add("next-step-or-takeaway")
        signals.add("closing-line")
    if any(token in lower for token in ("建议", "recommend", "decision")):
        signals.add("decision-headline")
    if _bullet_count(slide) >= 2:
        signals.add("action-list")
    if "metric-stack" in observed_patterns or "metric-card" in observed_classes:
        signals.add("metric-stack")
        signals.add("hero-metric")
    if "interpretation-card" in observed_classes or "interpretation" in lower or "why it matters" in lower:
        signals.add("interpretation-line")
    if observed_layout == "two-cols" or "table" in observed_patterns or "::left::" in body or "::right::" in body:
        signals.add("split-compare")
        signals.add("before-after")
    if "compare-panel" in observed_patterns:
        signals.add("compare-panel")
    if "map-with-insights" in observed_patterns or "map-panel" in observed_classes:
        signals.add("map-with-insights")
    if "action-path" in observed_patterns or "action-step" in observed_classes:
        signals.add("action-path")
    if "focus-explainer" in observed_patterns or "focus-card" in observed_classes:
        signals.add("focus-explainer")
        signals.add("single-claim")
        signals.add("focus-block")
    if re.search(r"^\s*###?\s+", body, re.MULTILINE) or "::left::" in body or "::right::" in body:
        signals.add("contrast-labels")
    if any(token in lower for token in ("要点", "核心", "takeaway", "why it matters")):
        signals.add("model-takeaway")
    if any(token in lower for token in ("结论", "核心判断", "bottom line", "verdict", "takeaway:", "so what")):
        signals.add("verdict-line")
    if any(token in lower for token in ("source", "来源", "数据来源")) or "slide-footer" in observed_classes:
        signals.add("source-or-takeaway")
    if "insight-card" in observed_classes or "metric-card" in observed_classes:
        signals.add("insight-card")
    if any(token in lower for token in ("p0", "p1", "p2", "priority", "prioritized", "优先级", "先做", "先后")):
        signals.add("prioritized-actions")
    if re.search(r"^\s*\d+\.\s+", body, re.MULTILINE) and _bullet_count(slide) <= 4:
        signals.add("prioritized-actions")
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
    if role == "detail" and {"single-claim", "focus-block"} & set(observed_signals):
        return "weak"
    if role == "recommendation" and {"decision-headline", "prioritized-actions"} & set(observed_signals):
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
    heading_index = next((index for index, line in enumerate(lines) if line.startswith("#")), None)
    if heading_index is None:
        return False
    if heading_index > 1:
        return False
    if heading_index == 1 and len(lines[0]) > 48:
        return False
    return _bullet_count(slide) <= 1 and len(lines) <= 6


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


def _detail_over_dense(slide: str) -> bool:
    body = _strip_slide_frontmatter(slide)
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if len(lines) >= 10 and _bullet_count(slide) >= 5:
        return True
    paragraph_lines = [line for line in lines if not line.startswith(("#", "-", "*", ">", "|", "<"))]
    return len(paragraph_lines) >= 6 and not _has_visual_structure(slide)


def _looks_detail_single_focus(slide: str) -> bool:
    body = _strip_slide_frontmatter(slide)
    lower = body.lower()
    heading_count = len(re.findall(r"^\s*##+\s+", body, re.MULTILINE))
    cue_hits = sum(
        1
        for token in ("single-claim", "核心判断", "key claim", "focus-card", "focus-explainer", "so what", "implication")
        if token in lower
    )
    return cue_hits >= 1 and heading_count <= 2 and _bullet_count(slide) <= 4


def _looks_plain_recommendation_list(slide: str) -> bool:
    body = _strip_slide_frontmatter(slide)
    lower = body.lower()
    has_decision = any(token in lower for token in ("decision", "建议", "结论", "recommendation", "verdict"))
    has_priority = any(token in lower for token in ("p0", "p1", "priority", "prioritized", "优先级", "先做", "先后"))
    has_action_path = any(token in lower for token in ("action-path", "action-step"))
    return _bullet_count(slide) >= 3 and not has_priority and not has_action_path and not has_decision


def _strip_slide_frontmatter(slide: str) -> str:
    body = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", slide, count=1, flags=re.DOTALL)
    return _strip_shared_visual_scaffold(body)


def _strip_shared_visual_scaffold(text: str) -> str:
    return re.sub(
        r"<style>\s*/\*\s*slidev-shared-visual-scaffold\s*\*/.*?</style>\s*",
        "",
        text,
        flags=re.DOTALL,
    ).strip()


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


def _global_frontmatter_value(markdown: str, key: str) -> str:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", markdown, re.DOTALL)
    if not match:
        return ""
    frontmatter = match.group(1)
    key_match = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", frontmatter, re.MULTILINE)
    if not key_match:
        return ""
    return key_match.group(1).strip()


def _normalize_slidev_composition(markdown: str) -> tuple[str, dict[str, bool | int]]:
    normalized, metadata = _normalize_leading_first_slide_frontmatter(markdown)
    normalized, separator_metadata = _normalize_double_separator_slide_frontmatter(normalized)
    metadata.update(separator_metadata)
    normalized, compaction = _compact_stray_metadata_deck(normalized)
    metadata.update(compaction)
    normalizer_actions = list(metadata.get("normalizer_actions") or [])
    if bool(metadata.get("blank_first_slide_detected")):
        normalizer_actions.append("blank_first_slide_normalized")
    if bool(metadata.get("double_separator_frontmatter_detected")):
        normalizer_actions.append("double_separator_frontmatter_normalized")
    if int(metadata.get("stray_metadata_repaired_count") or 0) > 0:
        normalizer_actions.append("stray_metadata_slide_compacted")
    metadata["normalizer_actions"] = sorted(set(normalizer_actions))
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
    normalized_body = re.sub(
        r"(?m)^---\s*\n\s*---\s*\n(?=(?:layout|class|transition|background):)",
        "---\n",
        normalized_body,
    )
    normalized = prefix + normalized_body
    if normalized_body:
        normalized = normalized.rstrip() + "\n"
    return normalized, {
        "double_separator_frontmatter_detected": normalized_count > 0,
        "normalized_double_separator_frontmatter_count": normalized_count,
    }


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


def _compact_stray_metadata_deck(markdown: str) -> tuple[str, dict[str, int]]:
    prefix, _body = _split_global_frontmatter_block(str(markdown or ""))
    slides = _slide_chunks(markdown)
    if not slides:
        return markdown, {"stray_metadata_repaired_count": 0, "empty_slide_repaired_count": 0}
    compacted, report = _compact_stray_metadata_slides(slides)
    if not compacted or int(report.get("stray_metadata_repaired_count") or 0) == 0:
        return markdown, report
    deck_body = _serialize_slidev_slides(compacted)
    return f"{prefix}{deck_body}\n", report


def _compact_stray_metadata_slides(slides: list[str]) -> tuple[list[str], dict[str, int]]:
    compacted = [slide.strip() for slide in slides if slide.strip()]
    repaired = 0
    index = 0
    while index < len(compacted):
        payload = _stray_metadata_payload(compacted[index])
        if not payload:
            index += 1
            continue
        if index + 1 < len(compacted):
            compacted[index + 1] = _merge_stray_metadata_into_slide(compacted[index + 1], payload)
            del compacted[index]
            repaired += 1
            continue
        if index > 0:
            compacted[index - 1] = _merge_stray_metadata_into_slide(compacted[index - 1], payload)
            del compacted[index]
            repaired += 1
            continue
        index += 1
    return compacted, {"stray_metadata_repaired_count": repaired, "empty_slide_repaired_count": repaired}


def _stray_metadata_payload(slide: str) -> dict[str, list[str]]:
    body = _strip_slide_frontmatter(slide)
    nonempty = [line.strip() for line in body.splitlines() if line.strip()]
    if not nonempty or len(nonempty) > 2:
        return {}
    allowed = {"container", "kicker", "subtitle", "eyebrow", "topline", "footer"}
    payload: dict[str, list[str]] = {}
    for line in nonempty:
        key = _frontmatter_key(line)
        if key in allowed:
            payload.setdefault(key, []).append(line.split(":", 1)[1].strip())
            continue
        html_match = re.match(r'^<div class="([^"]+)">(.*?)</div>$', line)
        if not html_match:
            return {}
        class_name = html_match.group(1).strip()
        html_value = html_match.group(2).strip()
        html_key = {
            "slide-topline": "topline",
            "section-kicker": "kicker",
            "slide-subtitle": "subtitle",
            "slide-footer": "footer",
        }.get(class_name)
        if html_key not in allowed or not html_value:
            return {}
        payload.setdefault(html_key, []).append(html_value)
    return payload


def _merge_stray_metadata_into_slide(slide: str, payload: dict[str, list[str]]) -> str:
    merged = slide
    for value in payload.get("container") or []:
        merged = _prepend_slide_frontmatter_classes(merged, value)
    cue_lines: list[str] = []
    for key, class_name in (
        ("topline", "slide-topline"),
        ("eyebrow", "section-kicker"),
        ("kicker", "section-kicker"),
        ("subtitle", "slide-subtitle"),
        ("footer", "slide-footer"),
    ):
        for value in payload.get(key) or []:
            text = str(value).strip()
            if text:
                cue_lines.append(f'<div class="{class_name}">{text}</div>')
    if not cue_lines:
        return merged
    frontmatter = _frontmatter_block(merged)
    body = _strip_slide_frontmatter(merged).strip()
    rebuilt = "\n\n".join(part for part in ("\n".join(cue_lines).strip(), body) if part).strip()
    if frontmatter:
        return "\n".join(["---", frontmatter, "---", "", rebuilt]).strip()
    return rebuilt


def _prepend_slide_frontmatter_classes(slide: str, class_value: str) -> str:
    frontmatter = _frontmatter_block(slide)
    body = _strip_slide_frontmatter(slide).strip()
    if frontmatter:
        merged = _merge_class_tokens(_frontmatter_scalar_value(frontmatter, "class"), class_value)
        updated = _replace_or_append_frontmatter_scalar(frontmatter, "class", merged)
        return "\n".join(["---", updated, "---", "", body]).strip()
    return "\n".join(["---", f"class: {class_value.strip()}", "---", "", body]).strip()


def _frontmatter_scalar_value(block: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", block, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _replace_or_append_frontmatter_scalar(block: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^\s*{re.escape(key)}:\s*.+?\s*$", re.MULTILINE)
    line = f"{key}: {value}"
    if pattern.search(block):
        return pattern.sub(line, block, count=1)
    return "\n".join([block.rstrip(), line]).strip()


def _merge_class_tokens(*raw_values: str) -> str:
    tokens: list[str] = []
    for raw in raw_values:
        for token in re.split(r"\s+", str(raw or "").strip()):
            if token and token not in tokens:
                tokens.append(token)
    return " ".join(tokens)


def _serialize_slidev_slides(slides: list[str]) -> str:
    serialized: list[str] = []
    for index, raw_slide in enumerate(slides):
        slide = raw_slide.strip()
        if not slide:
            continue
        if index == 0:
            serialized.append(slide)
        elif slide.startswith("---\n"):
            serialized.append(slide)
        else:
            serialized.append(f"---\n\n{slide}")
    return "\n\n".join(serialized).rstrip()


if __name__ == "__main__":
    raise SystemExit(main())

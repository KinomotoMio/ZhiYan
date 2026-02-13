"""Normalize presentation payloads to tolerate historical schema variants."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

DEFAULT_LEFT_HEADING = "要点 A"
DEFAULT_RIGHT_HEADING = "要点 B"
DEFAULT_FILLER_TEXT = "内容生成中"


def normalize_presentation_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], bool, dict[str, Any]]:
    """Normalize persisted presentation payload.

    Returns:
        normalized_payload: normalized payload copy (or original shape if untouched).
        changed: whether normalized payload differs from input payload.
        repair_report: summary of changes and unrecoverable slide count.
    """
    normalized = deepcopy(payload)
    slides = normalized.get("slides")
    if not isinstance(slides, list):
        return normalized, False, {
            "repaired_slide_count": 0,
            "repair_types": [],
            "invalid_slide_count": 0,
        }

    changed = False
    repair_reasons: list[str] = []
    invalid_slide_count = 0

    for slide in slides:
        if not isinstance(slide, dict):
            continue
        layout_id_raw = slide.get("layoutId") or slide.get("layoutType") or ""
        layout_id = str(layout_id_raw) if isinstance(layout_id_raw, str) else ""
        content = slide.get("contentData")
        if not isinstance(content, dict):
            continue

        repaired_content, repaired, recoverable, reason = _normalize_layout_content(layout_id, content)
        if repaired:
            slide["contentData"] = repaired_content
            changed = True
            if reason:
                repair_reasons.append(reason)

        if not recoverable:
            invalid_slide_count += 1

    report = {
        "repaired_slide_count": len(repair_reasons),
        "repair_types": sorted(set(repair_reasons)),
        "invalid_slide_count": invalid_slide_count,
    }
    return normalized, changed, report


def _normalize_layout_content(
    layout_id: str,
    data: dict[str, Any],
) -> tuple[dict[str, Any], bool, bool, str]:
    if layout_id == "two-column-compare":
        return _normalize_two_column_compare(data)
    if layout_id == "table-info":
        return _normalize_table_info(data)
    if layout_id == "challenge-outcome":
        return _normalize_challenge_outcome(data)
    return data, False, True, ""


def _normalize_two_column_compare(data: dict[str, Any]) -> tuple[dict[str, Any], bool, bool, str]:
    title = _as_text(data.get("title"), "对比分析")

    left = _normalize_compare_column(data.get("left"), DEFAULT_LEFT_HEADING)
    right = _normalize_compare_column(data.get("right"), DEFAULT_RIGHT_HEADING)

    if left is None and right is None:
        left = _normalize_compare_column(data.get("challenge"), DEFAULT_LEFT_HEADING)
        right = _normalize_compare_column(data.get("outcome"), DEFAULT_RIGHT_HEADING)

    if left is None and right is None:
        items = _extract_text_items(data.get("items"))
        if items:
            left_items, right_items = _split_two_columns(items)
            normalized = {
                "title": title,
                "left": {"heading": DEFAULT_LEFT_HEADING, "items": left_items},
                "right": {"heading": DEFAULT_RIGHT_HEADING, "items": right_items},
            }
            changed = normalized != data
            return normalized, changed, True, "two-column-compare-from-items" if changed else ""

        return data, False, False, "two-column-compare-unrecoverable"

    normalized = {
        "title": title,
        "left": left or {"heading": DEFAULT_LEFT_HEADING, "items": [DEFAULT_FILLER_TEXT]},
        "right": right or {"heading": DEFAULT_RIGHT_HEADING, "items": [DEFAULT_FILLER_TEXT]},
    }
    changed = normalized != data
    return normalized, changed, True, "two-column-compare-shape" if changed else ""


def _normalize_table_info(data: dict[str, Any]) -> tuple[dict[str, Any], bool, bool, str]:
    title = _as_text(data.get("title"), "信息表")
    headers = _extract_text_items(data.get("headers")) or _extract_text_items(data.get("columns"))

    rows_raw = data.get("rows")
    normalized_rows: list[list[str]] = []
    if isinstance(rows_raw, list):
        for row in rows_raw:
            if isinstance(row, list):
                normalized_rows.append([_as_text(cell, "") for cell in row])
            elif isinstance(row, dict):
                if not headers:
                    headers = [str(key) for key in row.keys() if str(key).strip()]
                normalized_rows.append([_as_text(row.get(header), "") for header in headers])

    if not headers and normalized_rows:
        headers = [f"列{i + 1}" for i in range(max(len(row) for row in normalized_rows))]

    if not headers or not normalized_rows:
        return data, False, False, "table-info-unrecoverable"

    aligned_rows = [_align_row(row, len(headers)) for row in normalized_rows]
    normalized: dict[str, Any] = {
        "title": title,
        "headers": headers,
        "rows": aligned_rows,
    }
    caption = _as_text(data.get("caption"))
    if caption:
        normalized["caption"] = caption

    changed = normalized != data
    return normalized, changed, True, "table-info-shape" if changed else ""


def _normalize_challenge_outcome(data: dict[str, Any]) -> tuple[dict[str, Any], bool, bool, str]:
    title = _as_text(data.get("title"), "问题与方案")

    items: list[dict[str, str]] = []
    raw_items = data.get("items")
    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, dict):
                challenge = _as_text(item.get("challenge"), "")
                outcome = _as_text(item.get("outcome"), "")
                if challenge or outcome:
                    items.append(
                        {
                            "challenge": challenge or DEFAULT_FILLER_TEXT,
                            "outcome": outcome or "待补充",
                        }
                    )
            elif isinstance(item, str):
                text = item.strip()
                if text:
                    items.append({"challenge": text, "outcome": "待补充"})

    if not items:
        challenges = _extract_side_texts(data.get("challenge"))
        outcomes = _extract_side_texts(data.get("outcome"))
        if challenges or outcomes:
            count = max(len(challenges), len(outcomes))
            for idx in range(count):
                items.append(
                    {
                        "challenge": challenges[idx] if idx < len(challenges) else DEFAULT_FILLER_TEXT,
                        "outcome": outcomes[idx] if idx < len(outcomes) else "待补充",
                    }
                )

    if not items:
        return data, False, False, "challenge-outcome-unrecoverable"

    normalized = {"title": title, "items": items}
    changed = normalized != data
    return normalized, changed, True, "challenge-outcome-shape" if changed else ""


def _normalize_compare_column(raw: Any, fallback_heading: str) -> dict[str, Any] | None:
    if isinstance(raw, str):
        items = _extract_text_items_from_text(raw)
        if not items:
            return None
        return {
            "heading": fallback_heading,
            "items": items,
        }

    if not isinstance(raw, dict):
        return None

    heading = _as_text(raw.get("heading") or raw.get("title"), fallback_heading)
    items = _extract_text_items(raw.get("items"))
    if not items:
        items = [DEFAULT_FILLER_TEXT]

    result: dict[str, Any] = {"heading": heading, "items": items}
    icon = _normalize_icon(raw.get("icon"))
    if icon is not None:
        result["icon"] = icon
    return result


def _extract_side_texts(raw: Any) -> list[str]:
    if not isinstance(raw, dict):
        return []
    return _extract_text_items(raw.get("items"))


def _extract_text_items(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []

    items: list[str] = []
    for item in raw:
        if isinstance(item, str):
            items.extend(_extract_text_items_from_text(item))
            continue

        if not isinstance(item, dict):
            continue

        text = _as_text(item.get("text"), "")
        if not text:
            text = _as_text(item.get("title"), "")
        if not text:
            text = _as_text(item.get("label"), "")
        if not text:
            text = _as_text(item.get("description"), "")

        if not text:
            challenge = _as_text(item.get("challenge"), "")
            outcome = _as_text(item.get("outcome"), "")
            if challenge and outcome:
                text = f"{challenge} / {outcome}"
            else:
                text = challenge or outcome

        if text:
            items.append(text)

    return items


def _extract_text_items_from_text(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    items: list[str] = []
    for line in lines:
        if line.startswith("|"):
            cells = [_clean_markdown_text(cell) for cell in line.strip("|").split("|")]
            for cell in cells:
                if _should_keep_cell(cell):
                    items.append(cell)
            continue

        cleaned = _clean_markdown_text(line)
        if _should_keep_cell(cleaned):
            items.append(cleaned)

    deduped: list[str] = []
    for item in items:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _clean_markdown_text(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"^\s*[-*•]+\s*", "", text)
    text = re.sub(r"^\s*\d+[.)]\s*", "", text)
    text = text.strip("| ")
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _should_keep_cell(text: str) -> bool:
    if not text:
        return False
    if re.fullmatch(r"[-:]+", text):
        return False
    if text in {"栏目", "新增内容"}:
        return False
    return True


def _normalize_icon(raw: Any) -> dict[str, str] | None:
    if isinstance(raw, dict):
        query = _as_text(raw.get("query"), "")
        if query:
            return {"query": query}
        return None

    if isinstance(raw, str):
        query = raw.strip()
        if query:
            return {"query": query}

    return None


def _split_two_columns(items: list[str]) -> tuple[list[str], list[str]]:
    midpoint = max(1, (len(items) + 1) // 2)
    left = items[:midpoint] or [DEFAULT_FILLER_TEXT]
    right = items[midpoint:] or [DEFAULT_FILLER_TEXT]
    return left, right


def _align_row(row: list[str], expected_len: int) -> list[str]:
    if len(row) < expected_len:
        return row + [""] * (expected_len - len(row))
    if len(row) > expected_len:
        return row[:expected_len]
    return row


def _as_text(value: Any, default: str | None = None) -> str:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    if value is None:
        return default or ""
    if isinstance(value, (int, float, bool)):
        return str(value)
    return default or ""

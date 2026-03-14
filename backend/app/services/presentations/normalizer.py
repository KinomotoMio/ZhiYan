"""Normalize presentation payloads to tolerate historical schema variants."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from app.services.fallback_semantics import (
    CONTENT_GENERATING,
    PENDING_SUPPLEMENT,
    STATUS_MESSAGE,
    STATUS_TITLE,
    are_all_placeholder_texts,
    canonicalize_fallback_text,
    get_bullet_fallback_status,
)
from app.services.image_semantics import normalize_image_content_data

_RE_UNORDERED_LIST_PREFIX = re.compile(r"^\s*[-*\u2022+]\s*")
_RE_ORDERED_LIST_PREFIX = re.compile(r"^\s*\d+[.)]\s*")
_RE_WHITESPACE = re.compile(r"\s+")
_RE_TABLE_SEPARATOR = re.compile(r"[-:]+")

DEFAULT_LEFT_HEADING = "\u8981\u70b9 A"
DEFAULT_RIGHT_HEADING = "\u8981\u70b9 B"
OUTLINE_FALLBACK_TITLES = (
    "\u80cc\u666f",
    "\u5206\u6790",
    "\u65b9\u6848",
    "\u7ed3\u8bba",
    "\u5b9e\u65bd",
    "\u603b\u7ed3",
)


def normalize_outline_slide_data(
    data: dict[str, Any],
    *,
    title_default: str = "\u76ee\u5f55",
    fallback_titles: tuple[str, ...] = OUTLINE_FALLBACK_TITLES,
) -> dict[str, Any]:
    title = _as_text(data.get("title"), title_default)
    subtitle = _as_text(data.get("subtitle"), "")
    raw_sections = data.get("sections") if isinstance(data.get("sections"), list) else data.get("items")
    raw_sections = raw_sections if isinstance(raw_sections, list) else []

    sections: list[dict[str, str]] = []
    for index, section in enumerate(raw_sections):
        normalized = _normalize_outline_section(section, index, fallback_titles=fallback_titles)
        if normalized is not None:
            sections.append(normalized)

    sections = sections[:6]
    while len(sections) < 4:
        sections.append({"title": fallback_titles[len(sections)]})

    normalized: dict[str, Any] = {"title": title, "sections": sections}
    if subtitle:
        normalized["subtitle"] = subtitle
    return normalized


def split_outline_sections(sections: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    midpoint = (len(sections) + 1) // 2
    return sections[:midpoint], sections[midpoint:]


def normalize_metrics_slide_data(
    data: dict[str, Any],
    *,
    title_default: str = "\u5173\u952e\u6307\u6807",
) -> dict[str, Any] | None:
    title = _as_text(data.get("title"), title_default)
    raw_metrics = data.get("metrics") if isinstance(data.get("metrics"), list) else []

    metrics: list[dict[str, Any]] = []
    for item in raw_metrics:
        metric = _normalize_metric_item(item)
        if metric is not None:
            metrics.append(metric)

    metrics = metrics[:4]
    if not metrics:
        return None

    normalized: dict[str, Any] = {
        "title": title,
        "metrics": metrics,
    }
    conclusion = _as_text(data.get("conclusion"), "")
    conclusion_brief = _as_text(data.get("conclusionBrief"), "")
    if conclusion:
        normalized["conclusion"] = conclusion
    if conclusion_brief:
        normalized["conclusionBrief"] = conclusion_brief
    return normalized


def normalize_presentation_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], bool, dict[str, Any]]:
    """Normalize persisted presentation payload."""
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
    data_with_image_source = normalize_image_content_data(layout_id, data)
    image_changed = data_with_image_source != data

    if layout_id in {"intro-slide", "intro-slide-left"}:
        return _normalize_intro_slide(data_with_image_source)
    if layout_id in {"metrics-slide", "metrics-slide-band"}:
        return _normalize_metrics_slide(data_with_image_source)
    if layout_id in {"bullet-with-icons", "bullet-with-icons-cards"}:
        return _normalize_bullet_with_icons(data_with_image_source)
    if layout_id in {"quote-slide", "quote-banner"}:
        return _normalize_quote_slide(data_with_image_source)
    if layout_id in {"thank-you", "thank-you-contact"}:
        return _normalize_thank_you(data_with_image_source)
    if layout_id in {"outline-slide", "outline-slide-rail"}:
        return _normalize_outline_slide(data_with_image_source)
    if layout_id == "two-column-compare":
        return _normalize_two_column_compare(data_with_image_source)
    if layout_id == "table-info":
        return _normalize_table_info(data_with_image_source)
    if layout_id == "challenge-outcome":
        return _normalize_challenge_outcome(data_with_image_source)
    if image_changed:
        return data_with_image_source, True, True, "image-ref-source"
    return data_with_image_source, False, True, ""


def _normalize_intro_slide(data: dict[str, Any]) -> tuple[dict[str, Any], bool, bool, str]:
    title = _as_text(data.get("title"), "\u672a\u547d\u540d\u6f14\u793a")
    subtitle = _as_text(data.get("subtitle"), "")
    author = _as_text(data.get("author") or data.get("presenter"), "")
    date = _as_text(data.get("date"), "")

    normalized: dict[str, Any] = {"title": title}
    if subtitle:
        normalized["subtitle"] = subtitle
    if author:
        normalized["author"] = author
    if date:
        normalized["date"] = date

    changed = normalized != data
    return normalized, changed, True, "intro-slide-shape" if changed else ""


def _normalize_quote_slide(data: dict[str, Any]) -> tuple[dict[str, Any], bool, bool, str]:
    quote = _as_text(data.get("quote"), "") or _as_text(data.get("title"), "")
    if not quote:
        return data, False, False, "quote-slide-unrecoverable"

    author = _as_text(data.get("author") or data.get("attribution"), "")
    context = _as_text(data.get("context"), "")

    normalized: dict[str, Any] = {"quote": quote}
    if author:
        normalized["author"] = author
    if context:
        normalized["context"] = context

    changed = normalized != data
    return normalized, changed, True, "quote-slide-shape" if changed else ""


def _normalize_thank_you(data: dict[str, Any]) -> tuple[dict[str, Any], bool, bool, str]:
    title = _as_text(data.get("title"), "\u8c22\u8c22")
    subtitle = _as_text(data.get("subtitle"), "")
    contact = _as_text(data.get("contact") or data.get("contact_info"), "")

    normalized: dict[str, Any] = {"title": title}
    if subtitle:
        normalized["subtitle"] = subtitle
    if contact:
        normalized["contact"] = contact

    changed = normalized != data
    return normalized, changed, True, "thank-you-shape" if changed else ""


def _normalize_outline_slide(data: dict[str, Any]) -> tuple[dict[str, Any], bool, bool, str]:
    normalized = normalize_outline_slide_data(data)
    changed = normalized != data
    return normalized, changed, True, "outline-slide-shape" if changed else ""


def _normalize_metrics_slide(data: dict[str, Any]) -> tuple[dict[str, Any], bool, bool, str]:
    normalized = normalize_metrics_slide_data(data)
    if normalized is None:
        return data, False, False, "metrics-slide-unrecoverable"

    changed = normalized != data
    return normalized, changed, True, "metrics-slide-shape" if changed else ""


def _normalize_status(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    title = _as_text(raw.get("title"), STATUS_TITLE)
    message = _as_text(raw.get("message"), STATUS_MESSAGE)
    return {"title": title, "message": message}


def _canonicalize_placeholder_sequence(items: list[str]) -> list[str]:
    if are_all_placeholder_texts(items):
        return [canonicalize_fallback_text(item) for item in items]
    return items


def _normalize_bullet_with_icons(data: dict[str, Any]) -> tuple[dict[str, Any], bool, bool, str]:
    title = _as_text(data.get("title"), "\u8981\u70b9\u6982\u89c8")
    raw_items = data.get("items") if isinstance(data.get("items"), list) else []

    placeholder_only = bool(raw_items) and all(
        isinstance(raw_item, dict)
        and (item_title := _as_text(raw_item.get("title"), ""))
        and (item_description := _as_text(raw_item.get("description"), ""))
        and are_all_placeholder_texts([item_title, item_description])
        and canonicalize_fallback_text(item_title) == canonicalize_fallback_text(item_description)
        for raw_item in raw_items
    )

    items: list[dict[str, Any]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        item_title = _as_text(raw_item.get("title"), "")
        item_description = _as_text(raw_item.get("description"), "")
        text = item_title or item_description
        if not text:
            continue
        if (
            item_title
            and item_description
            and are_all_placeholder_texts([item_title, item_description])
            and canonicalize_fallback_text(item_title) == canonicalize_fallback_text(item_description)
        ):
            continue

        icon = _normalize_icon(raw_item.get("icon")) or {"query": "star"}
        items.append(
            {
                "icon": icon,
                "title": item_title or text[:25],
                "description": item_description or text,
            }
        )

    normalized: dict[str, Any] = {
        "title": title,
        "items": items,
    }
    status = _normalize_status(data.get("status"))
    if status is None and (placeholder_only or len(items) == 0):
        status = get_bullet_fallback_status()
    if status is not None:
        normalized["status"] = status

    changed = normalized != data
    return normalized, changed, True, "bullet-with-icons-fallback-state" if changed else ""


def _normalize_two_column_compare(data: dict[str, Any]) -> tuple[dict[str, Any], bool, bool, str]:
    title = _as_text(data.get("title"), "\u5bf9\u6bd4\u5206\u6790")

    left = _normalize_compare_column(data.get("left"), DEFAULT_LEFT_HEADING)
    right = _normalize_compare_column(data.get("right"), DEFAULT_RIGHT_HEADING)

    if left is None and right is None:
        left = _normalize_compare_column(data.get("challenge"), DEFAULT_LEFT_HEADING)
        right = _normalize_compare_column(data.get("outcome"), DEFAULT_RIGHT_HEADING)

    if left is None and right is None:
        items = _canonicalize_placeholder_sequence(_extract_text_items(data.get("items")))
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
        "left": left or {"heading": DEFAULT_LEFT_HEADING, "items": [CONTENT_GENERATING]},
        "right": right or {"heading": DEFAULT_RIGHT_HEADING, "items": [CONTENT_GENERATING]},
    }
    changed = normalized != data
    return normalized, changed, True, "two-column-compare-shape" if changed else ""


def _normalize_table_info(data: dict[str, Any]) -> tuple[dict[str, Any], bool, bool, str]:
    title = _as_text(data.get("title"), "\u4fe1\u606f\u8868")
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
        headers = [f"\u5217 {i + 1}" for i in range(max(len(row) for row in normalized_rows))]

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
    title = _as_text(data.get("title"), "\u95ee\u9898\u4e0e\u65b9\u6848")

    items: list[dict[str, str]] = []
    raw_items = data.get("items")
    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, dict):
                challenge = _as_text(item.get("challenge"), "")
                outcome = _as_text(item.get("outcome"), "")
                if challenge or outcome:
                    placeholder_only_row = are_all_placeholder_texts([challenge, outcome])
                    items.append(
                        {
                            "challenge": canonicalize_fallback_text(challenge) if placeholder_only_row and challenge else challenge or CONTENT_GENERATING,
                            "outcome": canonicalize_fallback_text(outcome) if placeholder_only_row and outcome else outcome or PENDING_SUPPLEMENT,
                        }
                    )
            elif isinstance(item, str):
                text = item.strip()
                if text:
                    items.append(
                        {
                            "challenge": text,
                            "outcome": PENDING_SUPPLEMENT,
                        }
                    )

    if not items:
        challenges = _extract_side_texts(data.get("challenge"))
        outcomes = _extract_side_texts(data.get("outcome"))
        if are_all_placeholder_texts([*challenges, *outcomes]):
            challenges = [canonicalize_fallback_text(item) for item in challenges]
            outcomes = [canonicalize_fallback_text(item) for item in outcomes]
        if challenges or outcomes:
            count = max(len(challenges), len(outcomes))
            for idx in range(count):
                items.append(
                    {
                        "challenge": challenges[idx] if idx < len(challenges) else CONTENT_GENERATING,
                        "outcome": outcomes[idx] if idx < len(outcomes) else PENDING_SUPPLEMENT,
                    }
                )

    if not items:
        return data, False, False, "challenge-outcome-unrecoverable"

    normalized = {"title": title, "items": items}
    changed = normalized != data
    return normalized, changed, True, "challenge-outcome-shape" if changed else ""


def _normalize_outline_section(
    raw: Any,
    index: int,
    *,
    fallback_titles: tuple[str, ...] = OUTLINE_FALLBACK_TITLES,
) -> dict[str, str] | None:
    if isinstance(raw, str):
        title = raw.strip()
        return {"title": title} if title else None

    if not isinstance(raw, dict):
        return None

    title = (
        _as_text(raw.get("title"), "")
        or _as_text(raw.get("text"), "")
        or _as_text(raw.get("label"), "")
        or _as_text(raw.get("heading"), "")
        or _as_text(raw.get("name"), "")
    )
    description = (
        _as_text(raw.get("description"), "")
        or _as_text(raw.get("summary"), "")
        or _as_text(raw.get("detail"), "")
    )
    if not title and not description:
        return None

    normalized = {"title": title or fallback_titles[index]}
    if description:
        normalized["description"] = description
    return normalized


def _normalize_metric_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    value = _as_text(raw.get("value"), "") or _as_text(raw.get("metric"), "") or _as_text(raw.get("number"), "")
    label = _as_text(raw.get("label"), "") or _as_text(raw.get("title"), "") or _as_text(raw.get("name"), "")
    description = _as_text(raw.get("description"), "") or _as_text(raw.get("detail"), "")

    if not value and not label and not description:
        return None

    metric: dict[str, Any] = {
        "value": value or label,
        "label": label or value,
    }
    if description:
        metric["description"] = description
    icon = _normalize_icon(raw.get("icon"))
    if icon is not None:
        metric["icon"] = icon
    return metric


def _normalize_compare_column(raw: Any, fallback_heading: str) -> dict[str, Any] | None:
    if isinstance(raw, str):
        items = _canonicalize_placeholder_sequence(_extract_text_items_from_text(raw))
        if not items:
            return None
        return {
            "heading": fallback_heading,
            "items": items,
        }

    if not isinstance(raw, dict):
        return None

    heading = _as_text(raw.get("heading") or raw.get("title"), fallback_heading)
    items = _canonicalize_placeholder_sequence(_extract_text_items(raw.get("items")))
    if not items:
        items = [CONTENT_GENERATING]

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
    text = _RE_UNORDERED_LIST_PREFIX.sub("", text)
    text = _RE_ORDERED_LIST_PREFIX.sub("", text)
    text = text.strip("| ")
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = _RE_WHITESPACE.sub(" ", text).strip()
    return text


def _should_keep_cell(text: str) -> bool:
    if not text:
        return False
    if _RE_TABLE_SEPARATOR.fullmatch(text):
        return False
    if text in {"\u680f\u76ee", "\u65b0\u589e\u5185\u5bb9"}:
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
    left = items[:midpoint] or [CONTENT_GENERATING]
    right = items[midpoint:] or [CONTENT_GENERATING]
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

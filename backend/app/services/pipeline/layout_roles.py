"""Compatibility role helpers backed by the formal layout taxonomy."""

from __future__ import annotations

import re
from typing import Any, cast

from app.services.pipeline.layout_taxonomy import (
    LayoutGroup,
    get_group_order,
    get_layout_group_description,
    get_layout_group_label,
    get_layout_taxonomy,
    get_sub_groups_for_group,
)
LayoutRole = LayoutGroup

ROLE_ORDER: tuple[LayoutRole, ...] = get_group_order()

ROLE_LABELS: dict[LayoutRole, str] = {
    role: get_layout_group_label(role) for role in ROLE_ORDER
}

ROLE_DESCRIPTIONS: dict[LayoutRole, str] = {
    role: get_layout_group_description(role) for role in ROLE_ORDER
}

VARIANT_PILOT_ROLES: frozenset[LayoutRole] = frozenset(
    role
    for role in ROLE_ORDER
    if any(sub_group != "default" for sub_group in get_sub_groups_for_group(role))
)

LEGACY_CATEGORY_TO_ROLE: dict[str, LayoutRole] = {
    "intro": "cover",
    "section": "section-divider",
    "bullets": "narrative",
    "image": "narrative",
    "metrics": "evidence",
    "chart": "evidence",
    "table": "evidence",
    "comparison": "comparison",
    "challenge": "comparison",
    "timeline": "process",
    "quote": "highlight",
    "thankyou": "closing",
}

ROLE_TO_DEFAULT_LAYOUT: dict[LayoutRole, str] = {
    "cover": "intro-slide",
    "agenda": "outline-slide",
    "section-divider": "section-header",
    "narrative": "bullet-with-icons",
    "evidence": "metrics-slide",
    "comparison": "two-column-compare",
    "process": "numbered-bullets",
    "highlight": "quote-slide",
    "closing": "thank-you",
}

STRONG_LAYOUT_ROLES: frozenset[LayoutRole] = frozenset(
    {"cover", "agenda", "section-divider", "closing"}
)

CONTENT_LAYOUT_ROLES: frozenset[LayoutRole] = frozenset(
    {"narrative", "evidence", "comparison", "process", "highlight"}
)

_SECTION_DIVIDER_KEYWORDS: tuple[str, ...] = (
    "part",
    "chapter",
    "章节",
    "部分",
    "篇章",
    "模块",
)
_COMPARISON_KEYWORDS: tuple[str, ...] = (
    "对比",
    "比较",
    "差异",
    "优劣",
    "现状",
    "目标",
    "vs",
    "versus",
    "对照",
)
_PROCESS_KEYWORDS: tuple[str, ...] = (
    "流程",
    "步骤",
    "路径",
    "计划",
    "实施",
    "推进",
    "落地",
    "roadmap",
    "timeline",
    "milestone",
    "rollout",
)
_EVIDENCE_KEYWORDS: tuple[str, ...] = (
    "数据",
    "指标",
    "统计",
    "趋势",
    "实验",
    "结果",
    "分析",
    "图表",
    "chart",
    "metric",
    "kpi",
    "benchmark",
)
_HIGHLIGHT_KEYWORDS: tuple[str, ...] = (
    "结论",
    "总结",
    "启示",
    "建议",
    "观点",
    "takeaway",
    "summary",
    "key message",
)


def get_layout_role(layout_id: str) -> LayoutRole:
    taxonomy = get_layout_taxonomy(layout_id)
    return taxonomy.group if taxonomy else "narrative"


def get_layout_role_label(role: LayoutRole) -> str:
    return ROLE_LABELS[role]


def get_layout_role_description(role: str | None) -> str:
    normalized = normalize_slide_role(role)
    return ROLE_DESCRIPTIONS[normalized]


def is_variant_pilot_role(role: str | None) -> bool:
    normalized = normalize_slide_role(role)
    return normalized in VARIANT_PILOT_ROLES


def format_role_contract_for_prompt() -> str:
    lines: list[str] = []
    for role in ROLE_ORDER:
        pilot_note = "（存在正式 sub-group）" if role in VARIANT_PILOT_ROLES else ""
        lines.append(f"- `{role}`: {ROLE_LABELS[role]}，{ROLE_DESCRIPTIONS[role]}{pilot_note}")
    return "\n".join(lines)


def get_default_layout_for_role(role: str | None) -> str:
    normalized = normalize_slide_role(role)
    return ROLE_TO_DEFAULT_LAYOUT[normalized]


def normalize_slide_role(value: str | None) -> LayoutRole:
    token = (value or "").strip()
    if token in ROLE_TO_DEFAULT_LAYOUT:
        return cast(LayoutRole, token)

    legacy = token.lower().replace("_", "-")
    if legacy in ROLE_TO_DEFAULT_LAYOUT:
        return cast(LayoutRole, legacy)

    if legacy in LEGACY_CATEGORY_TO_ROLE:
        return LEGACY_CATEGORY_TO_ROLE[legacy]

    return "narrative"


def get_outline_item_role(item: dict[str, Any]) -> LayoutRole:
    raw_role = item.get("suggested_slide_role")
    if isinstance(raw_role, str) and raw_role.strip():
        return normalize_slide_role(raw_role)

    legacy_role = item.get("suggested_layout_category")
    if isinstance(legacy_role, str) and legacy_role.strip():
        return normalize_slide_role(legacy_role)

    return "narrative"


def normalize_outline_items_roles(
    items: list[dict[str, Any]],
    *,
    num_pages: int | None = None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        next_item = dict(item)
        raw_role = next_item.get("suggested_slide_role")
        legacy_role = next_item.get("suggested_layout_category")
        if isinstance(raw_role, str) and raw_role.strip():
            next_item["suggested_slide_role"] = get_outline_item_role(next_item)
        elif isinstance(legacy_role, str) and legacy_role.strip():
            next_item["suggested_slide_role"] = get_outline_item_role(next_item)
        else:
            next_item["suggested_slide_role"] = _infer_body_role_from_content(next_item)
        next_item.pop("suggested_layout_category", None)
        normalized.append(next_item)

    if not normalized:
        return normalized

    total = max(len(normalized), int(num_pages or 0))
    if len(normalized) == 1:
        normalized[0]["suggested_slide_role"] = "cover"
        return normalized

    normalized[0]["suggested_slide_role"] = "cover"
    normalized[-1]["suggested_slide_role"] = "closing"

    if total >= 5 and len(normalized) > 2:
        first_body_end = min(3, len(normalized) - 1)
        agenda_found = any(
            str(normalized[idx].get("suggested_slide_role")) == "agenda"
            for idx in range(1, first_body_end)
        )
        if not agenda_found:
            normalized[1]["suggested_slide_role"] = "agenda"

    for idx in range(1, len(normalized) - 1):
        role = normalize_slide_role(str(normalized[idx].get("suggested_slide_role")))

        if role == "agenda" and total < 5:
            normalized[idx]["suggested_slide_role"] = _fallback_body_role(normalized[idx])
            continue

        if role == "agenda" and idx > 2:
            normalized[idx]["suggested_slide_role"] = _fallback_body_role(normalized[idx])
            continue

        if role == "section-divider":
            if total < 7:
                normalized[idx]["suggested_slide_role"] = _fallback_body_role(normalized[idx])
                continue

            if not any(
                str(normalized[pos].get("suggested_slide_role")) == "agenda"
                for pos in range(1, idx)
            ):
                normalized[idx]["suggested_slide_role"] = _fallback_body_role(normalized[idx])
                continue

            if idx + 1 < len(normalized) - 1:
                next_role = normalize_slide_role(str(normalized[idx + 1].get("suggested_slide_role")))
                if next_role == "section-divider":
                    normalized[idx]["suggested_slide_role"] = _fallback_body_role(normalized[idx])
                    continue

    if total >= 7:
        divider_count = 0
        for idx in range(1, len(normalized) - 1):
            role = normalize_slide_role(str(normalized[idx].get("suggested_slide_role")))
            if role != "section-divider":
                continue
            divider_count += 1
            if divider_count > 2:
                normalized[idx]["suggested_slide_role"] = _fallback_body_role(normalized[idx])

    return normalized


def _fallback_body_role(item: dict[str, Any]) -> LayoutRole:
    role = get_outline_item_role(item)
    if role in CONTENT_LAYOUT_ROLES:
        return role
    return "narrative"


def _infer_body_role_from_content(item: dict[str, Any]) -> LayoutRole:
    title = str(item.get("title") or "").strip().lower()
    content_brief = str(item.get("content_brief") or "").strip().lower()
    key_points = [
        str(point).strip().lower()
        for point in item.get("key_points", [])
        if isinstance(point, str) and point.strip()
    ]
    combined = "\n".join([title, content_brief, "\n".join(key_points)])

    if _looks_like_section_divider(title, content_brief, key_points):
        return "section-divider"
    if any(token in combined for token in _COMPARISON_KEYWORDS):
        return "comparison"
    if any(token in combined for token in _PROCESS_KEYWORDS):
        return "process"
    if _looks_like_evidence(combined):
        return "evidence"
    if _looks_like_highlight(title, content_brief, key_points):
        return "highlight"
    return "narrative"


def _looks_like_section_divider(title: str, content_brief: str, key_points: list[str]) -> bool:
    if content_brief or len(key_points) > 1:
        return False
    if re.match(r"^(part|chapter)\s*\d+", title):
        return True
    if re.match(r"^第[一二三四五六七八九十0-9]+(部分|章|篇)", title):
        return True
    return any(token in title for token in _SECTION_DIVIDER_KEYWORDS)


def _looks_like_evidence(combined: str) -> bool:
    if any(token in combined for token in _EVIDENCE_KEYWORDS):
        return True
    return bool(re.search(r"\b\d+(?:\.\d+)?%|\d+[万亿kmb]?\b", combined))


def _looks_like_highlight(title: str, content_brief: str, key_points: list[str]) -> bool:
    combined = "\n".join([title, content_brief, "\n".join(key_points)])
    if not any(token in combined for token in _HIGHLIGHT_KEYWORDS):
        return False
    return len(key_points) <= 2

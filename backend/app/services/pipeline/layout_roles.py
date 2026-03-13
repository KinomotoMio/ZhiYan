"""Layout role helpers for outline normalization and layout selection."""

from __future__ import annotations

from typing import Any, Literal, cast

from app.services.pipeline.layout_metadata import load_layout_metadata

LayoutRole = Literal[
    "cover",
    "agenda",
    "section-divider",
    "narrative",
    "evidence",
    "comparison",
    "process",
    "highlight",
    "closing",
]

_SHARED_METADATA = load_layout_metadata()

ROLE_ORDER: tuple[LayoutRole, ...] = tuple(
    cast(LayoutRole, role) for role in _SHARED_METADATA["groupOrder"]
)

ROLE_LABELS: dict[LayoutRole, str] = {
    cast(LayoutRole, role): label
    for role, label in _SHARED_METADATA["groupLabels"].items()
}

ROLE_DESCRIPTIONS: dict[LayoutRole, str] = {
    cast(LayoutRole, role): description
    for role, description in _SHARED_METADATA["groupDescriptions"].items()
}

VARIANT_PILOT_ROLES: frozenset[LayoutRole] = frozenset(
    cast(LayoutRole, role)
    for role, sub_groups in _SHARED_METADATA["subGroupsByGroup"].items()
    if len(sub_groups) > 1 or any(key != "default" for key in sub_groups)
)

LAYOUT_ID_TO_ROLE: dict[str, LayoutRole] = {
    layout_id: cast(LayoutRole, metadata["group"])
    for layout_id, metadata in _SHARED_METADATA["layouts"].items()
}

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


def get_layout_role(layout_id: str) -> LayoutRole:
    return LAYOUT_ID_TO_ROLE.get(layout_id, "narrative")


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
        pilot_note = "（首个 variant 试点组）" if role in VARIANT_PILOT_ROLES else ""
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
        next_item["suggested_slide_role"] = get_outline_item_role(next_item)
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

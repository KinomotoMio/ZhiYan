"""Compatibility variant helpers backed by the formal layout taxonomy."""

from __future__ import annotations

from typing import TypeAlias, cast

from app.services.pipeline.layout_roles import LayoutRole, normalize_slide_role
from app.services.pipeline.layout_taxonomy import (
    get_group_order,
    get_layout_taxonomy,
    get_layout_variant_definition,
)

LayoutVariant: TypeAlias = str

_VARIANT_SUB_GROUPS: dict[LayoutRole, dict[LayoutVariant, str]] = {
    "cover": {"title-centered": "default", "title-left": "default"},
    "agenda": {"section-cards": "default", "chapter-rail": "default"},
    "section-divider": {"centered-divider": "default", "side-label": "default"},
    "narrative": {
        "icon-pillars": "icon-points",
        "feature-cards": "icon-points",
        "media-feature": "visual-explainer",
        "icon-matrix": "capability-grid",
    },
    "evidence": {
        "kpi-grid": "stat-summary",
        "summary-band": "stat-summary",
        "context-metrics": "visual-evidence",
        "chart-takeaways": "chart-analysis",
        "data-matrix": "table-matrix",
    },
    "comparison": {
        "balanced-columns": "side-by-side",
        "challenge-response": "response-mapping",
    },
    "process": {
        "numbered-steps": "step-flow",
        "progress-track": "step-flow",
        "timeline-band": "timeline-milestone",
    },
    "highlight": {"quote-focus": "default", "banner-highlight": "default"},
    "closing": {"closing-center": "default", "contact-card": "default"},
}


def _variant_entry(role: LayoutRole, variant: LayoutVariant) -> dict[str, str]:
    sub_group = _VARIANT_SUB_GROUPS[role][variant]
    definition = get_layout_variant_definition(role, sub_group, variant)
    return {
        "label": definition.label if definition else variant,
        "description": definition.description if definition else "",
    }


VARIANTS_BY_ROLE: dict[LayoutRole, dict[LayoutVariant, dict[str, str]]] = {
    role: {
        cast(LayoutVariant, variant): _variant_entry(role, cast(LayoutVariant, variant))
        for variant in _VARIANT_SUB_GROUPS[role]
    }
    for role in get_group_order()
}

ALL_LAYOUT_VARIANTS: frozenset[LayoutVariant] = frozenset(
    cast(LayoutVariant, variant)
    for role_variants in VARIANTS_BY_ROLE.values()
    for variant in role_variants
)

def normalize_layout_variant(value: str | None) -> LayoutVariant:
    token = (value or "").strip()
    if token in ALL_LAYOUT_VARIANTS:
        return cast(LayoutVariant, token)
    return ""


def get_layout_variant(layout_id: str) -> LayoutVariant:
    taxonomy = get_layout_taxonomy(layout_id)
    if taxonomy is None:
        return "title-centered"
    return cast(LayoutVariant, taxonomy.variant_id)


def get_layout_variant_label(role: str | None, variant: str | None) -> str:
    normalized_role = normalize_slide_role(role)
    normalized_variant = normalize_layout_variant(variant)
    if normalized_variant not in VARIANTS_BY_ROLE[normalized_role]:
        normalized_variant = next(iter(VARIANTS_BY_ROLE[normalized_role]))
    return VARIANTS_BY_ROLE[normalized_role][normalized_variant]["label"]


def get_layout_variant_description(role: str | None, variant: str | None) -> str:
    normalized_role = normalize_slide_role(role)
    normalized_variant = normalize_layout_variant(variant)
    if normalized_variant not in VARIANTS_BY_ROLE[normalized_role]:
        normalized_variant = next(iter(VARIANTS_BY_ROLE[normalized_role]))
    return VARIANTS_BY_ROLE[normalized_role][normalized_variant]["description"]


def get_variants_for_role(role: str | None) -> tuple[LayoutVariant, ...]:
    normalized_role = normalize_slide_role(role)
    return tuple(VARIANTS_BY_ROLE[normalized_role].keys())

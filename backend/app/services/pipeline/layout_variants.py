"""Compatibility variant helpers backed by the formal layout taxonomy."""

from __future__ import annotations

from typing import Literal, cast

from app.services.pipeline.layout_roles import LayoutRole, normalize_slide_role
from app.services.pipeline.layout_taxonomy import (
    get_group_order,
    get_layout_taxonomy,
    get_sub_group_description,
    get_sub_group_label,
    get_sub_groups_for_group,
)

LayoutVariant = Literal[
    "default",
    "icon-points",
    "visual-explainer",
    "capability-grid",
]

VARIANTS_BY_ROLE: dict[LayoutRole, dict[LayoutVariant, dict[str, str]]] = {
    role: {
        cast(LayoutVariant, variant): {
            "label": get_sub_group_label(role, variant),
            "description": get_sub_group_description(role, variant),
        }
        for variant in (
            get_sub_groups_for_group(role)
            if role == "narrative"
            else ("default",)
        )
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
    return "default"


def get_layout_variant(layout_id: str) -> LayoutVariant:
    taxonomy = get_layout_taxonomy(layout_id)
    if taxonomy is None:
        return "default"
    return cast(LayoutVariant, taxonomy.sub_group) if taxonomy.group == "narrative" else "default"


def get_layout_variant_label(role: str | None, variant: str | None) -> str:
    normalized_role = normalize_slide_role(role)
    normalized_variant = normalize_layout_variant(variant)
    return VARIANTS_BY_ROLE[normalized_role][normalized_variant]["label"]


def get_layout_variant_description(role: str | None, variant: str | None) -> str:
    normalized_role = normalize_slide_role(role)
    normalized_variant = normalize_layout_variant(variant)
    return VARIANTS_BY_ROLE[normalized_role][normalized_variant]["description"]


def get_variants_for_role(role: str | None) -> tuple[LayoutVariant, ...]:
    normalized_role = normalize_slide_role(role)
    return tuple(VARIANTS_BY_ROLE[normalized_role].keys())

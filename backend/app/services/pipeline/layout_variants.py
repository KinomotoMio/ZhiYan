"""Layout variant helpers backed by shared metadata."""

from __future__ import annotations

from typing import Literal, cast

from app.services.pipeline.layout_metadata import load_layout_metadata
from app.services.pipeline.layout_roles import LayoutRole, normalize_slide_role

LayoutVariant = Literal[
    "default",
    "icon-points",
    "visual-explainer",
    "capability-grid",
]

_SHARED_METADATA = load_layout_metadata()

VARIANTS_BY_ROLE: dict[LayoutRole, dict[LayoutVariant, dict[str, str]]] = {
    role: {
        cast(LayoutVariant, variant): {
            "label": str(definition["label"]),
            "description": str(definition["description"]),
        }
        for variant, definition in variants.items()
    }
    for role, variants in (
        (
            cast(LayoutRole, role),
            (
                sub_groups
                if role == "narrative"
                else {
                    "default": sub_groups.get(
                        "default",
                        {
                            "label": "默认变体",
                            "description": "当前组尚未展开正式的结构型兼容变体。",
                        },
                    )
                }
            ),
        )
        for role, sub_groups in _SHARED_METADATA["subGroupsByGroup"].items()
    )
}

ALL_LAYOUT_VARIANTS: frozenset[LayoutVariant] = frozenset(
    cast(LayoutVariant, variant)
    for role_variants in VARIANTS_BY_ROLE.values()
    for variant in role_variants
)

LAYOUT_ID_TO_VARIANT: dict[str, LayoutVariant] = {
    layout_id: cast(
        LayoutVariant,
        metadata.get("subGroup", "default")
        if metadata.get("group") == "narrative"
        else "default",
    )
    for layout_id, metadata in _SHARED_METADATA["layouts"].items()
}


def normalize_layout_variant(value: str | None) -> LayoutVariant:
    token = (value or "").strip()
    if token in ALL_LAYOUT_VARIANTS:
        return cast(LayoutVariant, token)
    return "default"


def get_layout_variant(layout_id: str) -> LayoutVariant:
    return LAYOUT_ID_TO_VARIANT.get(layout_id, "default")


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

"""Formal three-layer layout taxonomy helpers backed by shared metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from app.services.pipeline.layout_metadata import load_layout_metadata

LayoutGroup = Literal[
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

LayoutVariantAxis = Literal["composition", "tone", "style", "density"]

_SHARED_METADATA = load_layout_metadata()


@dataclass(frozen=True)
class LayoutVariantObject:
    composition: str
    tone: str
    style: str
    density: str


@dataclass(frozen=True)
class LayoutTaxonomyEntry:
    group: LayoutGroup
    sub_group: str
    variant: LayoutVariantObject


GROUP_ORDER: tuple[LayoutGroup, ...] = tuple(
    cast(LayoutGroup, group) for group in _SHARED_METADATA["groupOrder"]
)


def get_layout_taxonomy(layout_id: str) -> LayoutTaxonomyEntry | None:
    metadata = _SHARED_METADATA["layouts"].get(layout_id)
    if not isinstance(metadata, dict):
        return None

    variant = metadata.get("variant", {})
    return LayoutTaxonomyEntry(
        group=cast(LayoutGroup, metadata.get("group", "narrative")),
        sub_group=str(metadata.get("subGroup", "default")),
        variant=LayoutVariantObject(
            composition=str(variant.get("composition", "")),
            tone=str(variant.get("tone", "")),
            style=str(variant.get("style", "")),
            density=str(variant.get("density", "")),
        ),
    )


def get_group_order() -> tuple[LayoutGroup, ...]:
    return GROUP_ORDER


def get_layout_group_label(group: LayoutGroup) -> str:
    return str(_SHARED_METADATA["groupLabels"][group])


def get_layout_group_description(group: LayoutGroup) -> str:
    return str(_SHARED_METADATA["groupDescriptions"][group])


def get_sub_groups_for_group(group: LayoutGroup) -> tuple[str, ...]:
    return tuple(_SHARED_METADATA["subGroupsByGroup"].get(group, {}).keys())


def get_sub_group_label(group: LayoutGroup, sub_group: str) -> str:
    return str(
        _SHARED_METADATA["subGroupsByGroup"].get(group, {}).get(sub_group, {}).get("label", sub_group)
    )


def get_sub_group_description(group: LayoutGroup, sub_group: str) -> str:
    return str(
        _SHARED_METADATA["subGroupsByGroup"]
        .get(group, {})
        .get(sub_group, {})
        .get("description", "")
    )


def get_variant_axis_label(axis: LayoutVariantAxis, value: str) -> str:
    return str(_SHARED_METADATA["variantAxes"].get(axis, {}).get(value, {}).get("label", value))


def get_variant_axis_description(axis: LayoutVariantAxis, value: str) -> str:
    return str(
        _SHARED_METADATA["variantAxes"].get(axis, {}).get(value, {}).get("description", "")
    )

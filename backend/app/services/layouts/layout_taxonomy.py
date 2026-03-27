"""Formal three-layer layout taxonomy helpers backed by shared metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from app.services.layouts.layout_metadata import load_layout_metadata

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

LayoutDesignTraitAxis = Literal["tone", "style", "density"]

_SHARED_METADATA = load_layout_metadata()


@dataclass(frozen=True)
class LayoutDesignTraits:
    tone: str = ""
    style: str = ""
    density: str = ""


@dataclass(frozen=True)
class LayoutVariantDefinition:
    id: str
    label: str
    description: str
    usage: tuple[str, ...]
    usage_bias: str
    design_traits: LayoutDesignTraits


@dataclass(frozen=True)
class LayoutTemplateNotes:
    purpose: str
    structure_signal: str
    design_signal: str
    use_when: str
    avoid_when: str
    usage_bias: str


@dataclass(frozen=True)
class LayoutTaxonomyEntry:
    group: LayoutGroup
    sub_group: str
    variant_id: str
    is_variant_default: bool


GROUP_ORDER: tuple[LayoutGroup, ...] = tuple(
    cast(LayoutGroup, group) for group in _SHARED_METADATA["groupOrder"]
)


def get_layout_taxonomy(layout_id: str) -> LayoutTaxonomyEntry | None:
    metadata = _SHARED_METADATA["layouts"].get(layout_id)
    if not isinstance(metadata, dict):
        return None

    return LayoutTaxonomyEntry(
        group=cast(LayoutGroup, metadata.get("group", "narrative")),
        sub_group=str(metadata.get("subGroup", "default")),
        variant_id=str(metadata.get("variantId", "")),
        is_variant_default=bool(metadata.get("isVariantDefault", False)),
    )


def get_layout_notes(layout_id: str) -> LayoutTemplateNotes | None:
    metadata = _SHARED_METADATA["layouts"].get(layout_id)
    if not isinstance(metadata, dict):
        return None

    notes = metadata.get("notes", {})
    if not isinstance(notes, dict):
        return None

    return LayoutTemplateNotes(
        purpose=str(notes.get("purpose", "")),
        structure_signal=str(notes.get("structure_signal", "")),
        design_signal=str(notes.get("design_signal", "")),
        use_when=str(notes.get("use_when", "")),
        avoid_when=str(notes.get("avoid_when", "")),
        usage_bias=str(notes.get("usage_bias", "")),
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


def get_layout_variant_definition(
    group: LayoutGroup,
    sub_group: str,
    variant_id: str,
) -> LayoutVariantDefinition | None:
    definition = (
        _SHARED_METADATA["variantsBySubGroup"]
        .get(group, {})
        .get(sub_group, {})
        .get(variant_id)
    )
    if not isinstance(definition, dict):
        return None

    design_traits = definition.get("designTraits", {})
    return LayoutVariantDefinition(
        id=variant_id,
        label=str(definition.get("label", variant_id)),
        description=str(definition.get("description", "")),
        usage=tuple(str(tag) for tag in definition.get("usage", [])),
        usage_bias=str(definition.get("usageBias", "")),
        design_traits=LayoutDesignTraits(
            tone=str(design_traits.get("tone", "")),
            style=str(design_traits.get("style", "")),
            density=str(design_traits.get("density", "")),
        ),
    )


def get_variant_ids_for_sub_group(group: LayoutGroup, sub_group: str) -> tuple[str, ...]:
    return tuple(
        _SHARED_METADATA["variantsBySubGroup"].get(group, {}).get(sub_group, {}).keys()
    )


def get_design_trait_label(axis: LayoutDesignTraitAxis, value: str) -> str:
    return str(_SHARED_METADATA["designTraitAxes"].get(axis, {}).get(value, {}).get("label", value))


def get_design_trait_description(axis: LayoutDesignTraitAxis, value: str) -> str:
    return str(
        _SHARED_METADATA["designTraitAxes"].get(axis, {}).get(value, {}).get("description", "")
    )

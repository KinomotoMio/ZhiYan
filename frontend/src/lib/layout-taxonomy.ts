import layoutMetadataJson from "@/generated/layout-metadata.json";

type SharedLayoutMetadata = typeof layoutMetadataJson;
type SubGroupsByGroup = SharedLayoutMetadata["subGroupsByGroup"];
type VariantAxes = SharedLayoutMetadata["variantAxes"];
type LayoutRecord = Record<
  string,
  {
    group: LayoutGroup;
    subGroup: LayoutSubGroup;
    variant: LayoutVariantObject;
  }
>;
type SubGroupRecord = Record<
  LayoutGroup,
  Record<string, { label: string; description: string }>
>;
type VariantAxisRecord = Record<
  LayoutVariantAxis,
  Record<string, { label: string; description: string }>
>;

export type LayoutGroup = keyof SharedLayoutMetadata["groupLabels"];
export type LayoutSubGroup = {
  [G in keyof SubGroupsByGroup]: keyof SubGroupsByGroup[G];
}[keyof SubGroupsByGroup];
export type LayoutVariantAxis = keyof VariantAxes;
export type LayoutVariantComposition = keyof VariantAxes["composition"];
export type LayoutVariantTone = keyof VariantAxes["tone"];
export type LayoutVariantStyle = keyof VariantAxes["style"];
export type LayoutVariantDensity = keyof VariantAxes["density"];

export type LayoutVariantObject = {
  composition: LayoutVariantComposition;
  tone: LayoutVariantTone;
  style: LayoutVariantStyle;
  density: LayoutVariantDensity;
};

export type LayoutTaxonomyEntry = {
  group: LayoutGroup;
  subGroup: LayoutSubGroup;
  variant: LayoutVariantObject;
};

const layoutMetadata = layoutMetadataJson as SharedLayoutMetadata;
const layouts = layoutMetadata.layouts as LayoutRecord;
const subGroupsByGroup = layoutMetadata.subGroupsByGroup as SubGroupRecord;
const variantAxes = layoutMetadata.variantAxes as VariantAxisRecord;

export const LAYOUT_GROUP_ORDER = [...layoutMetadata.groupOrder] as LayoutGroup[];

export function getLayoutTaxonomy(layoutId: string): LayoutTaxonomyEntry | null {
  const metadata = layouts[layoutId];

  if (!metadata) {
    return null;
  }

  return {
    group: metadata.group,
    subGroup: metadata.subGroup as LayoutSubGroup,
    variant: metadata.variant,
  };
}

export function getLayoutGroupLabel(group: LayoutGroup): string {
  return layoutMetadata.groupLabels[group];
}

export function getLayoutGroupDescription(group: LayoutGroup): string {
  return layoutMetadata.groupDescriptions[group];
}

export function getLayoutSubGroupsForGroup(group: LayoutGroup): LayoutSubGroup[] {
  return Object.keys(subGroupsByGroup[group] ?? {}) as LayoutSubGroup[];
}

export function getLayoutSubGroupLabel(
  group: LayoutGroup,
  subGroup: LayoutSubGroup,
): string {
  return subGroupsByGroup[group]?.[subGroup]?.label ?? subGroup;
}

export function getLayoutSubGroupDescription(
  group: LayoutGroup,
  subGroup: LayoutSubGroup,
): string {
  return subGroupsByGroup[group]?.[subGroup]?.description ?? "";
}

export function getLayoutVariantAxisLabel(
  axis: LayoutVariantAxis,
  value: string,
): string {
  return variantAxes[axis]?.[value]?.label ?? value;
}

export function getLayoutVariantAxisDescription(
  axis: LayoutVariantAxis,
  value: string,
): string {
  return variantAxes[axis]?.[value]?.description ?? "";
}

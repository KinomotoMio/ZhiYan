import layoutMetadataJson from "@/generated/layout-metadata.json";

type SharedLayoutMetadata = typeof layoutMetadataJson;
type SubGroupsByGroup = SharedLayoutMetadata["subGroupsByGroup"];
type VariantsBySubGroup = SharedLayoutMetadata["variantsBySubGroup"];
type DesignTraitAxes = SharedLayoutMetadata["designTraitAxes"];
type LayoutRecord = Record<
  string,
  {
    group: LayoutGroup;
    subGroup: LayoutSubGroup;
    variantId: LayoutVariantId;
    isVariantDefault?: boolean;
    notes: LayoutTemplateNotes;
  }
>;
type SubGroupRecord = Record<
  LayoutGroup,
  Record<string, { label: string; description: string }>
>;
type VariantRecord = Record<
  LayoutGroup,
  Record<
    string,
    Record<
      string,
      {
        label: string;
        description: string;
        usage: string[];
        usageBias: string;
        designTraits?: LayoutDesignTraits;
      }
    >
  >
>;
type DesignTraitAxisRecord = Record<
  LayoutDesignTraitAxis,
  Record<string, { label: string; description: string }>
>;

export type LayoutGroup = keyof SharedLayoutMetadata["groupLabels"];
export type LayoutSubGroup = {
  [G in keyof SubGroupsByGroup]: keyof SubGroupsByGroup[G];
}[keyof SubGroupsByGroup];
export type LayoutVariantId = {
  [G in keyof VariantsBySubGroup]: {
    [S in keyof VariantsBySubGroup[G]]: keyof VariantsBySubGroup[G][S];
  }[keyof VariantsBySubGroup[G]];
}[keyof VariantsBySubGroup];
export type LayoutDesignTraitAxis = keyof DesignTraitAxes;
export type LayoutVariantTone = keyof DesignTraitAxes["tone"];
export type LayoutVariantStyle = keyof DesignTraitAxes["style"];
export type LayoutVariantDensity = keyof DesignTraitAxes["density"];

export type LayoutDesignTraits = {
  tone?: LayoutVariantTone;
  style?: LayoutVariantStyle;
  density?: LayoutVariantDensity;
};

export type LayoutVariantDefinition = {
  id: LayoutVariantId;
  label: string;
  description: string;
  usage: string[];
  usageBias: string;
  designTraits: LayoutDesignTraits;
};

export type LayoutTemplateNotes = {
  purpose: string;
  structure_signal: string;
  design_signal: string;
  use_when: string;
  avoid_when: string;
  usage_bias: string;
};

export type LayoutTaxonomyEntry = {
  group: LayoutGroup;
  subGroup: LayoutSubGroup;
  variantId: LayoutVariantId;
  isVariantDefault: boolean;
};

const layoutMetadata = layoutMetadataJson as SharedLayoutMetadata;
const layouts = layoutMetadata.layouts as LayoutRecord;
const subGroupsByGroup = layoutMetadata.subGroupsByGroup as SubGroupRecord;
const variantsBySubGroup = layoutMetadata.variantsBySubGroup as VariantRecord;
const designTraitAxes = layoutMetadata.designTraitAxes as DesignTraitAxisRecord;

export const LAYOUT_GROUP_ORDER = [...layoutMetadata.groupOrder] as LayoutGroup[];

export function getLayoutTaxonomy(layoutId: string): LayoutTaxonomyEntry | null {
  const metadata = layouts[layoutId];

  if (!metadata) {
    return null;
  }

  return {
    group: metadata.group,
    subGroup: metadata.subGroup as LayoutSubGroup,
    variantId: metadata.variantId,
    isVariantDefault: Boolean(metadata.isVariantDefault),
  };
}

export function getLayoutNotes(layoutId: string): LayoutTemplateNotes | null {
  return layouts[layoutId]?.notes ?? null;
}

export function getLayoutVariantId(layoutId: string): LayoutVariantId | null {
  return layouts[layoutId]?.variantId ?? null;
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

export function getVariantsForSubGroup(
  group: LayoutGroup,
  subGroup: LayoutSubGroup,
): LayoutVariantId[] {
  return Object.keys(
    variantsBySubGroup[group]?.[subGroup] ?? {},
  ) as LayoutVariantId[];
}

export function getVariantDefinition(
  group: LayoutGroup,
  subGroup: LayoutSubGroup,
  variantId: LayoutVariantId,
): LayoutVariantDefinition | null {
  const definition = variantsBySubGroup[group]?.[subGroup]?.[variantId];
  if (!definition) {
    return null;
  }
  return {
    id: variantId,
    label: definition.label,
    description: definition.description,
    usage: definition.usage,
    usageBias: definition.usageBias,
    designTraits: definition.designTraits ?? {},
  };
}

export function getVariantLabel(
  group: LayoutGroup,
  subGroup: LayoutSubGroup,
  variantId: LayoutVariantId,
): string {
  return getVariantDefinition(group, subGroup, variantId)?.label ?? variantId;
}

export function getVariantDescription(
  group: LayoutGroup,
  subGroup: LayoutSubGroup,
  variantId: LayoutVariantId,
): string {
  return getVariantDefinition(group, subGroup, variantId)?.description ?? "";
}

export function getVariantUsage(
  group: LayoutGroup,
  subGroup: LayoutSubGroup,
  variantId: LayoutVariantId,
): string[] {
  return getVariantDefinition(group, subGroup, variantId)?.usage ?? [];
}

export function getVariantUsageBias(
  group: LayoutGroup,
  subGroup: LayoutSubGroup,
  variantId: LayoutVariantId,
): string {
  return getVariantDefinition(group, subGroup, variantId)?.usageBias ?? "";
}

export function getVariantDesignTraits(
  group: LayoutGroup,
  subGroup: LayoutSubGroup,
  variantId: LayoutVariantId,
): LayoutDesignTraits {
  return getVariantDefinition(group, subGroup, variantId)?.designTraits ?? {};
}

export function getLayoutDesignTraitLabel(
  axis: LayoutDesignTraitAxis,
  value: string,
): string {
  return designTraitAxes[axis]?.[value]?.label ?? value;
}

export function getLayoutDesignTraitDescription(
  axis: LayoutDesignTraitAxis,
  value: string,
): string {
  return designTraitAxes[axis]?.[value]?.description ?? "";
}

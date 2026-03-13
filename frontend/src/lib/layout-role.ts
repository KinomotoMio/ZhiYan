import layoutMetadataJson from "@/generated/layout-metadata.json";

export type LayoutRole =
  | "cover"
  | "agenda"
  | "section-divider"
  | "narrative"
  | "evidence"
  | "comparison"
  | "process"
  | "highlight"
  | "closing";

type SharedLayoutMetadata = {
  groupOrder: LayoutRole[];
  groupLabels: Record<LayoutRole, string>;
  groupDescriptions: Record<LayoutRole, string>;
  subGroupsByGroup: Record<
    LayoutRole,
    Record<string, { label: string; description: string }>
  >;
  layouts: Record<
    string,
    {
      group: LayoutRole;
      subGroup: string;
      variant: {
        composition: string;
        tone: string;
        style: string;
        density: string;
      };
      usage: string[];
    }
  >;
};

const layoutMetadata = layoutMetadataJson as SharedLayoutMetadata;

export const LAYOUT_ROLE_ORDER: LayoutRole[] = [...layoutMetadata.groupOrder];

export const LAYOUT_ROLE_LABELS: Record<LayoutRole, string> = {
  ...layoutMetadata.groupLabels,
};

export const LAYOUT_ROLE_DESCRIPTIONS: Record<LayoutRole, string> = {
  ...layoutMetadata.groupDescriptions,
};

export const VARIANT_PILOT_ROLES = new Set<LayoutRole>(
  (Object.entries(layoutMetadata.subGroupsByGroup) as Array<
    [LayoutRole, Record<string, { label: string; description: string }>]
  >)
    .filter(([, subGroups]) => {
      const keys = Object.keys(subGroups);
      return keys.length > 1 || keys.some((key) => key !== "default");
    })
    .map(([group]) => group),
);

const LAYOUT_ID_TO_ROLE: Record<string, LayoutRole> = Object.fromEntries(
  Object.entries(layoutMetadata.layouts).map(([layoutId, metadata]) => [
    layoutId,
    metadata.group,
  ]),
) as Record<string, LayoutRole>;

const ROLE_RANK = new Map(
  LAYOUT_ROLE_ORDER.map((role, index) => [role, index]),
);

export function getLayoutRole(layoutId: string): LayoutRole {
  return LAYOUT_ID_TO_ROLE[layoutId] ?? "narrative";
}

export function getLayoutRoleLabel(role: LayoutRole): string {
  return LAYOUT_ROLE_LABELS[role];
}

export function getLayoutRoleDescription(role: LayoutRole): string {
  return LAYOUT_ROLE_DESCRIPTIONS[role];
}

export function isVariantPilotRole(role: LayoutRole): boolean {
  return VARIANT_PILOT_ROLES.has(role);
}

export function compareLayoutRoles(a: LayoutRole, b: LayoutRole): number {
  return (ROLE_RANK.get(a) ?? 0) - (ROLE_RANK.get(b) ?? 0);
}

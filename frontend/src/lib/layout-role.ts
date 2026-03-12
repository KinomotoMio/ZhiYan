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
  roleOrder: LayoutRole[];
  roleLabels: Record<LayoutRole, string>;
  roleDescriptions: Record<LayoutRole, string>;
  variantPilotRoles: LayoutRole[];
  variantsByRole: Record<
    LayoutRole,
    Record<string, { label: string; description: string }>
  >;
  layouts: Record<
    string,
    { role: LayoutRole; variant: string; usage: string[] }
  >;
};

const layoutMetadata = layoutMetadataJson as SharedLayoutMetadata;

export const LAYOUT_ROLE_ORDER: LayoutRole[] = [...layoutMetadata.roleOrder];

export const LAYOUT_ROLE_LABELS: Record<LayoutRole, string> = {
  ...layoutMetadata.roleLabels,
};

export const LAYOUT_ROLE_DESCRIPTIONS: Record<LayoutRole, string> = {
  ...layoutMetadata.roleDescriptions,
};

export const VARIANT_PILOT_ROLES = new Set<LayoutRole>(
  layoutMetadata.variantPilotRoles,
);

const LAYOUT_ID_TO_ROLE: Record<string, LayoutRole> = Object.fromEntries(
  Object.entries(layoutMetadata.layouts).map(([layoutId, metadata]) => [
    layoutId,
    metadata.role,
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

import {
  getLayoutGroupDescription,
  getLayoutGroupLabel,
  getLayoutSubGroupsForGroup,
  getLayoutTaxonomy,
  LAYOUT_GROUP_ORDER,
  type LayoutGroup,
} from "@/lib/layout-taxonomy";

export type LayoutRole = LayoutGroup;

export const LAYOUT_ROLE_ORDER: LayoutRole[] = [...LAYOUT_GROUP_ORDER];

export const LAYOUT_ROLE_LABELS: Record<LayoutRole, string> = Object.fromEntries(
  LAYOUT_ROLE_ORDER.map((role) => [role, getLayoutGroupLabel(role)]),
) as Record<LayoutRole, string>;

export const LAYOUT_ROLE_DESCRIPTIONS: Record<LayoutRole, string> = Object.fromEntries(
  LAYOUT_ROLE_ORDER.map((role) => [role, getLayoutGroupDescription(role)]),
) as Record<LayoutRole, string>;

export const VARIANT_PILOT_ROLES = new Set<LayoutRole>(
  LAYOUT_ROLE_ORDER.filter((group) =>
    getLayoutSubGroupsForGroup(group).some((subGroup) => subGroup !== "default"),
  ),
);

const ROLE_RANK = new Map(
  LAYOUT_ROLE_ORDER.map((role, index) => [role, index]),
);

export function getLayoutRole(layoutId: string): LayoutRole {
  return getLayoutTaxonomy(layoutId)?.group ?? "narrative";
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

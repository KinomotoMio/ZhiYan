import layoutMetadataJson from "../../../shared/layout-metadata.json";

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
  layouts: Record<string, { role: LayoutRole; usage: string[] }>;
};

const layoutMetadata = layoutMetadataJson as SharedLayoutMetadata;

export const LAYOUT_ROLE_ORDER: LayoutRole[] = [...layoutMetadata.roleOrder];

export const LAYOUT_ROLE_LABELS: Record<LayoutRole, string> = {
  ...layoutMetadata.roleLabels,
};

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

export function compareLayoutRoles(a: LayoutRole, b: LayoutRole): number {
  return (ROLE_RANK.get(a) ?? 0) - (ROLE_RANK.get(b) ?? 0);
}

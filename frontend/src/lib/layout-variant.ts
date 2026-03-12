import layoutMetadataJson from "@/generated/layout-metadata.json";
import type { LayoutRole } from "@/lib/layout-role";

// Keep this union in sync with shared/layout-metadata.json when new variants land.
export type LayoutVariant =
  | "default"
  | "icon-points"
  | "visual-explainer"
  | "capability-grid";

type VariantDefinition = {
  label: string;
  description: string;
};

type SharedLayoutMetadata = {
  variantsByRole: Record<LayoutRole, Record<string, VariantDefinition>>;
  layouts: Record<string, { role: LayoutRole; variant: LayoutVariant; usage: string[] }>;
};

const layoutMetadata = layoutMetadataJson as SharedLayoutMetadata;

const VARIANTS_BY_ROLE = layoutMetadata.variantsByRole;

const LAYOUT_ID_TO_VARIANT: Record<string, LayoutVariant> = Object.fromEntries(
  Object.entries(layoutMetadata.layouts).map(([layoutId, metadata]) => [
    layoutId,
    metadata.variant,
  ]),
) as Record<string, LayoutVariant>;

export function getLayoutVariant(layoutId: string): LayoutVariant {
  return LAYOUT_ID_TO_VARIANT[layoutId] ?? "default";
}

export function getLayoutVariantLabel(
  role: LayoutRole,
  variant: LayoutVariant,
): string {
  return VARIANTS_BY_ROLE[role]?.[variant]?.label ?? variant;
}

export function getLayoutVariantDescription(
  role: LayoutRole,
  variant: LayoutVariant,
): string {
  return VARIANTS_BY_ROLE[role]?.[variant]?.description ?? "";
}

export function getLayoutVariantsForRole(role: LayoutRole): LayoutVariant[] {
  return Object.keys(VARIANTS_BY_ROLE[role] ?? {}) as LayoutVariant[];
}

export function isDefaultLayoutVariant(variant: LayoutVariant): boolean {
  return variant === "default";
}

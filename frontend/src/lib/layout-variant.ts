import {
  getLayoutSubGroupDescription,
  getLayoutSubGroupLabel,
  getLayoutSubGroupsForGroup,
  getLayoutTaxonomy,
  type LayoutGroup,
  type LayoutSubGroup,
} from "@/lib/layout-taxonomy";
import { compareLayoutNames } from "@/lib/sort";

// Compatibility wrapper for callers that still expect a single taxonomy token.
// The formal taxonomy entrypoint is layout-taxonomy.ts.
export type LayoutVariant = string;

export function getLayoutVariant(layoutId: string): LayoutVariant {
  const taxonomy = getLayoutTaxonomy(layoutId);
  if (!taxonomy) return "default";
  return taxonomy.subGroup as LayoutVariant;
}

export function getLayoutVariantLabel(
  role: LayoutGroup,
  variant: LayoutVariant,
): string {
  return getLayoutSubGroupLabel(role, variant as LayoutSubGroup) ?? variant;
}

export function getLayoutVariantDescription(
  role: LayoutGroup,
  variant: LayoutVariant,
): string {
  return getLayoutSubGroupDescription(role, variant as LayoutSubGroup) ?? "";
}

export function getLayoutVariantsForRole(role: LayoutGroup): LayoutVariant[] {
  return getLayoutSubGroupsForGroup(role) as LayoutVariant[];
}

export function compareLayoutVariants(
  role: LayoutGroup,
  leftVariant: LayoutVariant,
  rightVariant: LayoutVariant,
): number {
  const variants = getLayoutVariantsForRole(role);
  const leftIndex = variants.indexOf(leftVariant);
  const rightIndex = variants.indexOf(rightVariant);

  if (leftIndex !== rightIndex) {
    if (leftIndex === -1) return 1;
    if (rightIndex === -1) return -1;
    return leftIndex - rightIndex;
  }

  return compareLayoutNames(leftVariant, rightVariant, leftVariant, rightVariant);
}

export function isDefaultLayoutVariant(variant: LayoutVariant): boolean {
  return variant === "default";
}

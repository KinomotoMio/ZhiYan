import {
  getLayoutTaxonomy,
  getVariantDescription,
  getVariantLabel,
  type LayoutTaxonomyEntry,
  type LayoutGroup,
  type LayoutSubGroup,
  type LayoutVariantId,
} from "@/lib/layout-taxonomy";
import layoutMetadataJson from "@/generated/layout-metadata.json";
import { compareLayoutNames } from "@/lib/sort";

// Compatibility wrapper for callers that still expect a single variant token.
// The formal taxonomy entrypoint is layout-taxonomy.ts.
export type LayoutVariant = LayoutVariantId;

export function getLayoutVariant(layoutId: string): LayoutVariant {
  const taxonomy = getLayoutTaxonomy(layoutId);
  if (!taxonomy) return "title-centered" as LayoutVariant;
  return taxonomy.variantId as LayoutVariant;
}

export function getLayoutVariantLabel(
  role: LayoutGroup,
  variant: LayoutVariant,
): string {
  const taxonomy = getLayoutTaxonomyByRole(role, variant);
  if (!taxonomy) return variant;
  return getVariantLabel(taxonomy.group, taxonomy.subGroup as LayoutSubGroup, variant);
}

export function getLayoutVariantDescription(
  role: LayoutGroup,
  variant: LayoutVariant,
): string {
  const taxonomy = getLayoutTaxonomyByRole(role, variant);
  if (!taxonomy) return "";
  return getVariantDescription(taxonomy.group, taxonomy.subGroup as LayoutSubGroup, variant);
}

export function getLayoutVariantsForRole(role: LayoutGroup): LayoutVariant[] {
  return Object.keys((VARIANTS_BY_ROLE[role] ?? {})) as LayoutVariant[];
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
  return DEFAULT_VARIANTS.has(variant);
}

const VARIANTS_BY_ROLE = Object.fromEntries(
  Object.entries(layoutMetadataJson.variantsBySubGroup).map(([group, subGroups]) => [
    group,
    Object.fromEntries(
      Object.entries(subGroups).flatMap(([subGroup, variants]) =>
        Object.keys(variants).map((variantId) => [variantId, subGroup]),
      ),
    ),
  ]),
) as Record<LayoutGroup, Record<string, string>>;

const DEFAULT_VARIANTS = new Set<LayoutVariant>(
  Object.values(layoutMetadataJson.layouts)
    .filter((entry): entry is typeof entry & { isVariantDefault: true; variantId: string } =>
      Boolean(entry.isVariantDefault && entry.variantId),
    )
    .map((entry) => entry.variantId as LayoutVariant),
);

function getLayoutTaxonomyByRole(role: LayoutGroup, variant: LayoutVariant) {
  const variants = VARIANTS_BY_ROLE[role] as Record<string, string> | undefined;
  const subGroup = variants?.[variant];
  if (!subGroup) {
    return null;
  }
  return { group: role, subGroup } as Pick<LayoutTaxonomyEntry, "group" | "subGroup">;
}

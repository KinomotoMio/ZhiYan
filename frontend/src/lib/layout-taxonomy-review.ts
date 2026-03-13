import {
  getLayoutTaxonomy,
  type LayoutSubGroup as ReviewedSubGroup,
  type LayoutTaxonomyEntry as ReviewedLayoutTaxonomy,
  type LayoutVariantComposition as ReviewedVariantComposition,
  type LayoutVariantDensity as ReviewedVariantDensity,
  type LayoutVariantObject as ReviewedLayoutVariant,
  type LayoutVariantStyle as ReviewedVariantStyle,
  type LayoutVariantTone as ReviewedVariantTone,
} from "@/lib/layout-taxonomy";

export type {
  ReviewedLayoutTaxonomy,
  ReviewedSubGroup,
  ReviewedLayoutVariant,
  ReviewedVariantComposition,
  ReviewedVariantTone,
  ReviewedVariantStyle,
  ReviewedVariantDensity,
};

export function getReviewedLayoutTaxonomy(layoutId: string) {
  return getLayoutTaxonomy(layoutId);
}

import {
  type LayoutDesignTraits as ReviewedLayoutDesignTraits,
  getLayoutTaxonomy,
  type LayoutSubGroup as ReviewedSubGroup,
  type LayoutTaxonomyEntry as ReviewedLayoutTaxonomy,
  type LayoutVariantDensity as ReviewedVariantDensity,
  type LayoutVariantId as ReviewedLayoutVariantId,
  type LayoutVariantStyle as ReviewedVariantStyle,
  type LayoutVariantTone as ReviewedVariantTone,
} from "@/lib/layout-taxonomy";

export type {
  ReviewedLayoutTaxonomy,
  ReviewedSubGroup,
  ReviewedLayoutDesignTraits,
  ReviewedLayoutVariantId,
  ReviewedVariantTone,
  ReviewedVariantStyle,
  ReviewedVariantDensity,
};

export function getReviewedLayoutTaxonomy(layoutId: string) {
  return getLayoutTaxonomy(layoutId);
}

import layoutMetadataJson from "@/generated/layout-metadata.json";
import type { LayoutRole } from "@/lib/layout-role";

export type ReviewedSubGroup = string;

export type ReviewedLayoutVariant = {
  composition: string;
  tone: string;
  style: string;
  density: string;
};

export type ReviewedLayoutTaxonomy = {
  group: LayoutRole;
  subGroup: ReviewedSubGroup;
  variant: ReviewedLayoutVariant;
};

type SharedLayoutMetadata = {
  layouts: Record<
    string,
    {
      group: LayoutRole;
      subGroup: string;
      variant: ReviewedLayoutVariant;
      usage: string[];
    }
  >;
};

// This adapter exists only so the catalog can read reviewed taxonomy values
// from shared metadata without keeping a second hardcoded source of truth.
const layoutMetadata = layoutMetadataJson as SharedLayoutMetadata;

export function getReviewedLayoutTaxonomy(
  layoutId: string,
): ReviewedLayoutTaxonomy | null {
  const metadata = layoutMetadata.layouts[layoutId];

  if (!metadata) {
    return null;
  }

  return {
    group: metadata.group,
    subGroup: metadata.subGroup,
    variant: metadata.variant,
  };
}

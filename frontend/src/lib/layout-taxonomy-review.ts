import type { LayoutRole } from "@/lib/layout-role";

export type ReviewedSubGroup =
  | "default"
  | "icon-points"
  | "visual-explainer"
  | "capability-grid";

export type ReviewedVariantComposition =
  | "hero-center"
  | "card-grid"
  | "section-break"
  | "icon-columns"
  | "media-split"
  | "capability-grid"
  | "stat-grid"
  | "analysis-split"
  | "table-dominant"
  | "dual-columns"
  | "step-list"
  | "timeline-band"
  | "quote-focus"
  | "closing-hero";

export type ReviewedVariantTone =
  | "formal"
  | "neutral"
  | "assertive"
  | "approachable"
  | "celebratory";

export type ReviewedVariantStyle =
  | "minimal"
  | "card-based"
  | "editorial"
  | "icon-led"
  | "data-first"
  | "statement";

export type ReviewedVariantDensity = "low" | "medium" | "high";

export type ReviewedLayoutVariant = {
  composition: ReviewedVariantComposition;
  tone: ReviewedVariantTone;
  style: ReviewedVariantStyle;
  density: ReviewedVariantDensity;
};

export type ReviewedLayoutTaxonomy = {
  group: LayoutRole;
  subGroup: ReviewedSubGroup;
  variant: ReviewedLayoutVariant;
};

const REVIEWED_LAYOUT_TAXONOMY: Record<string, ReviewedLayoutTaxonomy> = {
  "intro-slide": {
    group: "cover",
    subGroup: "default",
    variant: {
      composition: "hero-center",
      tone: "formal",
      style: "editorial",
      density: "low",
    },
  },
  "outline-slide": {
    group: "agenda",
    subGroup: "default",
    variant: {
      composition: "card-grid",
      tone: "formal",
      style: "card-based",
      density: "medium",
    },
  },
  "section-header": {
    group: "section-divider",
    subGroup: "default",
    variant: {
      composition: "section-break",
      tone: "assertive",
      style: "minimal",
      density: "low",
    },
  },
  "bullet-with-icons": {
    group: "narrative",
    subGroup: "icon-points",
    variant: {
      composition: "icon-columns",
      tone: "assertive",
      style: "icon-led",
      density: "medium",
    },
  },
  "image-and-description": {
    group: "narrative",
    subGroup: "visual-explainer",
    variant: {
      composition: "media-split",
      tone: "approachable",
      style: "editorial",
      density: "medium",
    },
  },
  "bullet-icons-only": {
    group: "narrative",
    subGroup: "capability-grid",
    variant: {
      composition: "capability-grid",
      tone: "assertive",
      style: "icon-led",
      density: "high",
    },
  },
  "metrics-slide": {
    group: "evidence",
    subGroup: "default",
    variant: {
      composition: "stat-grid",
      tone: "formal",
      style: "data-first",
      density: "medium",
    },
  },
  "metrics-with-image": {
    group: "evidence",
    subGroup: "default",
    variant: {
      composition: "media-split",
      tone: "assertive",
      style: "data-first",
      density: "medium",
    },
  },
  "chart-with-bullets": {
    group: "evidence",
    subGroup: "default",
    variant: {
      composition: "analysis-split",
      tone: "formal",
      style: "data-first",
      density: "high",
    },
  },
  "table-info": {
    group: "evidence",
    subGroup: "default",
    variant: {
      composition: "table-dominant",
      tone: "formal",
      style: "data-first",
      density: "high",
    },
  },
  "two-column-compare": {
    group: "comparison",
    subGroup: "default",
    variant: {
      composition: "dual-columns",
      tone: "formal",
      style: "card-based",
      density: "medium",
    },
  },
  "challenge-outcome": {
    group: "comparison",
    subGroup: "default",
    variant: {
      composition: "dual-columns",
      tone: "assertive",
      style: "minimal",
      density: "medium",
    },
  },
  "numbered-bullets": {
    group: "process",
    subGroup: "default",
    variant: {
      composition: "step-list",
      tone: "neutral",
      style: "minimal",
      density: "medium",
    },
  },
  timeline: {
    group: "process",
    subGroup: "default",
    variant: {
      composition: "timeline-band",
      tone: "formal",
      style: "minimal",
      density: "medium",
    },
  },
  "quote-slide": {
    group: "highlight",
    subGroup: "default",
    variant: {
      composition: "quote-focus",
      tone: "assertive",
      style: "statement",
      density: "low",
    },
  },
  "thank-you": {
    group: "closing",
    subGroup: "default",
    variant: {
      composition: "closing-hero",
      tone: "celebratory",
      style: "minimal",
      density: "low",
    },
  },
};

export function getReviewedLayoutTaxonomy(
  layoutId: string,
): ReviewedLayoutTaxonomy | null {
  return REVIEWED_LAYOUT_TAXONOMY[layoutId] ?? null;
}

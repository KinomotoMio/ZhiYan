import {
  getLayoutTaxonomy,
  getVariantDescription,
  getVariantLabel,
  type LayoutGroup,
  type LayoutSubGroup,
  type LayoutVariantId,
} from "@/lib/layout-taxonomy";
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

const VARIANTS_BY_ROLE = {
  cover: {
    "title-centered": "default",
    "title-left": "default",
  },
  agenda: {
    "section-cards": "default",
    "chapter-rail": "default",
  },
  "section-divider": {
    "centered-divider": "default",
    "side-label": "default",
  },
  narrative: {
    "icon-pillars": "icon-points",
    "feature-cards": "icon-points",
    "media-feature": "visual-explainer",
    "icon-matrix": "capability-grid",
  },
  evidence: {
    "kpi-grid": "stat-summary",
    "summary-band": "stat-summary",
    "context-metrics": "visual-evidence",
    "chart-takeaways": "chart-analysis",
    "data-matrix": "table-matrix",
  },
  comparison: {
    "balanced-columns": "side-by-side",
    "challenge-response": "response-mapping",
  },
  process: {
    "numbered-steps": "step-flow",
    "progress-track": "step-flow",
    "timeline-band": "timeline-milestone",
  },
  highlight: {
    "quote-focus": "default",
    "banner-highlight": "default",
  },
  closing: {
    "closing-center": "default",
    "contact-card": "default",
  },
} as const satisfies Record<LayoutGroup, Record<string, string>>;

const DEFAULT_VARIANTS = new Set<LayoutVariant>([
  "title-centered",
  "section-cards",
  "centered-divider",
  "icon-pillars",
  "media-feature",
  "icon-matrix",
  "kpi-grid",
  "context-metrics",
  "chart-takeaways",
  "data-matrix",
  "balanced-columns",
  "challenge-response",
  "numbered-steps",
  "timeline-band",
  "quote-focus",
  "closing-center",
]);

function getLayoutTaxonomyByRole(role: LayoutGroup, variant: LayoutVariant) {
  const variants = VARIANTS_BY_ROLE[role] as Record<string, string> | undefined;
  const subGroup = variants?.[variant];
  if (!subGroup) {
    return null;
  }
  return { group: role, subGroup } as const;
}

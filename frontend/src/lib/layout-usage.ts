import layoutMetadataJson from "@/generated/layout-metadata.json";

export type LayoutUsageTag =
  | "academic-report"
  | "business-report"
  | "sales-pitch"
  | "investor-pitch"
  | "training-workshop"
  | "conference-keynote"
  | "project-status"
  | "product-demo";

export const usageLabels = layoutMetadataJson.usageLabels as Record<
  LayoutUsageTag,
  string
>;

const layoutUsageById = Object.fromEntries(
  Object.entries(layoutMetadataJson.layouts).map(([layoutId, metadata]) => [
    layoutId,
    metadata.usage,
  ]),
) as Record<string, LayoutUsageTag[]>;

export function getLayoutUsage(layoutId: string): LayoutUsageTag[] {
  return layoutUsageById[layoutId] ?? [];
}

export function getUsageLabel(tag: LayoutUsageTag): string {
  return usageLabels[tag];
}

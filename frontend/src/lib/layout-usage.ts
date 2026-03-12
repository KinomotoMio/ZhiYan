export const usageLabels = {
  "academic-report": "学术汇报",
  "business-report": "商业汇报",
  "sales-pitch": "销售提案",
  "investor-pitch": "融资路演",
  "training-workshop": "培训教学",
  "conference-keynote": "会议演讲",
  "project-status": "项目汇报",
  "product-demo": "产品演示",
} as const;

export type LayoutUsageTag = keyof typeof usageLabels;

const layoutUsageById: Record<string, LayoutUsageTag[]> = {
  "intro-slide": [
    "academic-report",
    "business-report",
    "sales-pitch",
    "investor-pitch",
    "training-workshop",
    "conference-keynote",
    "project-status",
    "product-demo",
  ],
  "section-header": [
    "academic-report",
    "business-report",
    "training-workshop",
    "conference-keynote",
    "project-status",
    "product-demo",
  ],
  "outline-slide": [
    "academic-report",
    "business-report",
    "training-workshop",
    "conference-keynote",
    "project-status",
    "investor-pitch",
  ],
  "bullet-with-icons": [
    "business-report",
    "sales-pitch",
    "investor-pitch",
    "product-demo",
    "conference-keynote",
  ],
  "numbered-bullets": [
    "training-workshop",
    "project-status",
    "business-report",
    "product-demo",
  ],
  "metrics-slide": [
    "academic-report",
    "business-report",
    "investor-pitch",
    "project-status",
  ],
  "metrics-with-image": [
    "business-report",
    "sales-pitch",
    "investor-pitch",
    "product-demo",
  ],
  "chart-with-bullets": [
    "academic-report",
    "business-report",
    "investor-pitch",
    "project-status",
  ],
  "table-info": [
    "academic-report",
    "business-report",
    "sales-pitch",
    "project-status",
  ],
  "two-column-compare": [
    "academic-report",
    "business-report",
    "sales-pitch",
    "investor-pitch",
    "product-demo",
  ],
  "image-and-description": [
    "business-report",
    "sales-pitch",
    "investor-pitch",
    "conference-keynote",
    "product-demo",
  ],
  timeline: [
    "academic-report",
    "business-report",
    "training-workshop",
    "conference-keynote",
    "project-status",
  ],
  "quote-slide": [
    "academic-report",
    "business-report",
    "investor-pitch",
    "conference-keynote",
  ],
  "bullet-icons-only": [
    "business-report",
    "training-workshop",
    "conference-keynote",
    "product-demo",
  ],
  "challenge-outcome": [
    "business-report",
    "sales-pitch",
    "investor-pitch",
    "project-status",
    "product-demo",
  ],
  "thank-you": [
    "academic-report",
    "business-report",
    "sales-pitch",
    "investor-pitch",
    "training-workshop",
    "conference-keynote",
    "project-status",
    "product-demo",
  ],
};

export function getLayoutUsage(layoutId: string): LayoutUsageTag[] {
  return layoutUsageById[layoutId] ?? [];
}

export function getUsageLabel(tag: LayoutUsageTag): string {
  return usageLabels[tag];
}

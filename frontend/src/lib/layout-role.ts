export type LayoutRole =
  | "cover"
  | "agenda"
  | "section-divider"
  | "narrative"
  | "evidence"
  | "comparison"
  | "process"
  | "highlight"
  | "closing";

export const LAYOUT_ROLE_ORDER: LayoutRole[] = [
  "cover",
  "agenda",
  "section-divider",
  "narrative",
  "evidence",
  "comparison",
  "process",
  "highlight",
  "closing",
];

export const LAYOUT_ROLE_LABELS: Record<LayoutRole, string> = {
  cover: "封面",
  agenda: "目录",
  "section-divider": "章节过渡",
  narrative: "叙述",
  evidence: "论据/数据",
  comparison: "对比",
  process: "流程",
  highlight: "强调",
  closing: "结尾",
};

const LAYOUT_ID_TO_ROLE: Record<string, LayoutRole> = {
  "intro-slide": "cover",
  "outline-slide": "agenda",
  "section-header": "section-divider",
  "bullet-with-icons": "narrative",
  "bullet-icons-only": "narrative",
  "image-and-description": "narrative",
  "metrics-slide": "evidence",
  "metrics-with-image": "evidence",
  "chart-with-bullets": "evidence",
  "table-info": "evidence",
  "two-column-compare": "comparison",
  "challenge-outcome": "comparison",
  "numbered-bullets": "process",
  timeline: "process",
  "quote-slide": "highlight",
  "thank-you": "closing",
};

const ROLE_RANK = new Map(
  LAYOUT_ROLE_ORDER.map((role, index) => [role, index]),
);

export function getLayoutRole(layoutId: string): LayoutRole {
  return LAYOUT_ID_TO_ROLE[layoutId] ?? "narrative";
}

export function compareLayoutRoles(a: LayoutRole, b: LayoutRole): number {
  return (ROLE_RANK.get(a) ?? 0) - (ROLE_RANK.get(b) ?? 0);
}

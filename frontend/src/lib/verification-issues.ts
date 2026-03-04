export type IssueTier = "hard" | "advisory";

export type IssueDecisionStatus =
  | "pending"
  | "applied"
  | "skipped"
  | "discarded";

export interface VerificationIssueView {
  slideId: string;
  severity: string;
  category: string;
  message: string;
  suggestion: string;
  source: string;
  tier: IssueTier;
  raw: Record<string, unknown>;
}

export interface SlideIssueGroup {
  slideId: string;
  hard: number;
  advisory: number;
  total: number;
  issues: VerificationIssueView[];
}

export function deriveTier(issue: Record<string, unknown>): IssueTier {
  const tierRaw = String(issue.tier ?? "").toLowerCase();
  if (tierRaw === "hard") return "hard";
  if (tierRaw === "advisory") return "advisory";
  const severity = String(issue.severity ?? "").toLowerCase();
  return severity === "error" ? "hard" : "advisory";
}

export function normalizeIssue(issue: Record<string, unknown>): VerificationIssueView | null {
  const slideId = String(issue.slide_id ?? "").trim();
  if (!slideId) return null;
  return {
    slideId,
    severity: String(issue.severity ?? "warning"),
    category: String(issue.category ?? "unknown"),
    message: String(issue.message ?? "未知问题"),
    suggestion: String(issue.suggestion ?? ""),
    source: String(issue.source ?? "unknown"),
    tier: deriveTier(issue),
    raw: issue,
  };
}

export function groupIssuesBySlide(
  issues: Array<Record<string, unknown>>
): Map<string, SlideIssueGroup> {
  const grouped = new Map<string, SlideIssueGroup>();
  for (const issue of issues) {
    const normalized = normalizeIssue(issue);
    if (!normalized) continue;
    const existing = grouped.get(normalized.slideId);
    if (!existing) {
      grouped.set(normalized.slideId, {
        slideId: normalized.slideId,
        hard: normalized.tier === "hard" ? 1 : 0,
        advisory: normalized.tier === "advisory" ? 1 : 0,
        total: 1,
        issues: [normalized],
      });
      continue;
    }
    existing.total += 1;
    if (normalized.tier === "hard") {
      existing.hard += 1;
    } else {
      existing.advisory += 1;
    }
    existing.issues.push(normalized);
  }
  return grouped;
}

export function collectIssueSlideIds(
  issues: Array<Record<string, unknown>>
): string[] {
  return Array.from(groupIssuesBySlide(issues).keys());
}

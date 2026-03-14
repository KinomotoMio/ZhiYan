import fallbackSemanticsJson from "@/generated/fallback-semantics.json";

type CanonicalFallbackSemantics = typeof fallbackSemanticsJson.canonical;

export const CONTENT_GENERATING = fallbackSemanticsJson.canonical.contentGenerating;
export const PENDING_SUPPLEMENT = fallbackSemanticsJson.canonical.pendingSupplement;
export const FALLBACK_GENERATED = fallbackSemanticsJson.canonical.fallbackGenerated;
export const STATUS_TITLE = fallbackSemanticsJson.canonical.statusTitle;
export const STATUS_MESSAGE = fallbackSemanticsJson.canonical.statusMessage;

const FALLBACK_CANONICAL_BY_KEY: CanonicalFallbackSemantics = fallbackSemanticsJson.canonical;

const FALLBACK_MATCH_MAP = new Map<string, string>();

function registerCanonical(
  canonicalText: string,
  aliases: readonly string[],
) {
  const values = [canonicalText, ...aliases];
  for (const value of values) {
    FALLBACK_MATCH_MAP.set(value.trim().toLowerCase(), canonicalText);
  }
}

registerCanonical(
  FALLBACK_CANONICAL_BY_KEY.contentGenerating,
  fallbackSemanticsJson.legacyAliases.contentGenerating,
);
registerCanonical(
  FALLBACK_CANONICAL_BY_KEY.pendingSupplement,
  fallbackSemanticsJson.legacyAliases.pendingSupplement,
);
registerCanonical(
  FALLBACK_CANONICAL_BY_KEY.fallbackGenerated,
  fallbackSemanticsJson.legacyAliases.fallbackGenerated,
);

export function canonicalizeFallbackText(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return trimmed;
  return FALLBACK_MATCH_MAP.get(trimmed.toLowerCase()) ?? trimmed;
}

export function isFallbackPlaceholderText(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed) return false;
  return FALLBACK_MATCH_MAP.has(trimmed.toLowerCase());
}

export function areAllFallbackPlaceholders(texts: readonly string[]): boolean {
  const populated = texts.map((text) => text.trim()).filter(Boolean);
  return populated.length > 0 && populated.every((text) => isFallbackPlaceholderText(text));
}

export function getBulletFallbackStatus(): { title: string; message: string } {
  return {
    title: STATUS_TITLE,
    message: STATUS_MESSAGE,
  };
}

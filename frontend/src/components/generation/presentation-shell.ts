import type { Slide } from "@/types/slide";

export interface OutlineTitleItem {
  slide_number: number;
  title: string;
}

type GenerationTier =
  | "shell"
  | "outline"
  | "content"
  | "assets"
  | "verify"
  | "fix"
  | string;

interface SlideGenerationMeta {
  seq?: number;
  engine_id?: string;
  tier?: GenerationTier;
  tier_rank?: number;
}

function normalizePageCount(pageCount: number): number {
  if (!Number.isFinite(pageCount)) return 1;
  return Math.max(1, Math.trunc(pageCount));
}

export function buildShellSlides(pageCount: number, baseTitle = "生成中..."): Slide[] {
  const total = normalizePageCount(pageCount);
  return Array.from({ length: total }, (_, idx) => ({
    slideId: `slide-${idx + 1}`,
    layoutType: "blank",
    layoutId: undefined,
    contentData: {
      title: baseTitle ? `${baseTitle} · 第 ${idx + 1} 页` : `第 ${idx + 1} 页`,
      _loading: true,
      _generation: { tier: "shell", tier_rank: 0, seq: 0 },
    },
    components: [],
  }));
}

export function mergeOutlineTitles(
  slides: Slide[],
  outlineItems: OutlineTitleItem[]
): Slide[] {
  if (!Array.isArray(slides) || slides.length === 0) {
    return slides;
  }
  const nextSlides = [...slides];
  for (const item of outlineItems) {
    const index = Math.trunc(item.slide_number) - 1;
    if (!Number.isFinite(index) || index < 0 || index >= nextSlides.length) {
      continue;
    }
    const title = typeof item.title === "string" ? item.title.trim() : "";
    if (!title) continue;
    const target = nextSlides[index];
    const data = (target.contentData ?? {}) as Record<string, unknown>;
    const existingMeta = readGenerationMeta(target);
    const existingRank = existingMeta ? asSafeInt(existingMeta.tier_rank, 0) : 0;
    const nextMeta: SlideGenerationMeta =
      existingRank >= 5
        ? existingMeta!
        : { tier: "outline", tier_rank: 5, seq: existingMeta?.seq ?? 0 };
    nextSlides[index] = {
      ...target,
      contentData: {
        ...data,
        title,
        _generation: nextMeta,
      },
    };
  }
  return nextSlides;
}

export function mergeGeneratedSlide(
  slides: Slide[],
  index: number,
  slide: Slide
): Slide[] {
  const safeIndex = Math.trunc(index);
  if (
    !Array.isArray(slides) ||
    safeIndex < 0 ||
    safeIndex >= slides.length ||
    !slide
  ) {
    return slides;
  }
  const prev = slides[safeIndex];
  if (!prev) return slides;

  const incoming = normalizeIncomingSlide(slide);
  const prevMeta = readGenerationMeta(prev) ?? { tier_rank: 0, seq: 0 };
  const nextMeta = readGenerationMeta(incoming) ?? { tier_rank: 0, seq: 0 };

  // Monotonic upgrade rules:
  // 1) Higher tier_rank always wins.
  // 2) Same tier_rank: higher seq wins (idempotent for duplicates/out-of-order).
  // 3) Never accept a loading shell as an "upgrade" over an already materialized slide.
  const prevRank = asSafeInt(prevMeta.tier_rank, 0);
  const nextRank = asSafeInt(nextMeta.tier_rank, 0);
  if (nextRank < prevRank) {
    return slides;
  }

  const prevSeq = asSafeInt(prevMeta.seq, 0);
  const nextSeq = asSafeInt(nextMeta.seq, 0);
  if (nextRank === prevRank && nextSeq <= prevSeq) {
    return slides;
  }

  const prevLoading = isLoadingSlide(prev);
  const nextLoading = isLoadingSlide(incoming);
  if (!prevLoading && nextLoading) {
    return slides;
  }

  const nextSlides = [...slides];
  nextSlides[safeIndex] = incoming;
  return nextSlides;
}

function asSafeInt(value: unknown, fallback = 0): number {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.trunc(n);
}

function isLoadingSlide(slide: Slide): boolean {
  const data = (slide.contentData ?? {}) as Record<string, unknown>;
  return data._loading === true;
}

function readGenerationMeta(slide: Slide): SlideGenerationMeta | null {
  const data = (slide.contentData ?? {}) as Record<string, unknown>;
  const raw = data._generation as SlideGenerationMeta | undefined;
  if (!raw || typeof raw !== "object") return null;
  const tier_rank = asSafeInt(raw.tier_rank, 0);
  const seq = asSafeInt(raw.seq, 0);
  return {
    tier: raw.tier,
    tier_rank,
    seq,
    engine_id: typeof raw.engine_id === "string" ? raw.engine_id : undefined,
  };
}

function normalizeIncomingSlide(slide: Slide): Slide {
  const data = (slide.contentData ?? {}) as Record<string, unknown>;
  const meta = readGenerationMeta(slide);
  // Ensure meta exists so merges are deterministic on replay.
  if (meta) return slide;
  return {
    ...slide,
    contentData: {
      ...data,
      _generation: { tier: "content", tier_rank: 20, seq: 0 },
    },
  };
}

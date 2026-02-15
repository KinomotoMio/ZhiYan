import type { Slide } from "@/types/slide";

export interface OutlineTitleItem {
  slide_number: number;
  title: string;
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
    nextSlides[index] = {
      ...target,
      contentData: {
        ...data,
        title,
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
  const nextSlides = [...slides];
  nextSlides[safeIndex] = slide;
  return nextSlides;
}

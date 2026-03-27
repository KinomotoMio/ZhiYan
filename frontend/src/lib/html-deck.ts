import type { HtmlDeckMeta, HtmlDeckSlideMeta } from "@/types/html-deck";
import type { Presentation, Slide, SpeakerAudio } from "@/types/slide";

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function normalizeSpeakerAudio(value: unknown): SpeakerAudio | undefined {
  const record = asRecord(value);
  if (!record) return undefined;
  const provider = typeof record.provider === "string" ? record.provider : "";
  const model = typeof record.model === "string" ? record.model : "";
  const voiceId = typeof record.voiceId === "string" ? record.voiceId : "";
  const textHash = typeof record.textHash === "string" ? record.textHash : "";
  const storagePath = typeof record.storagePath === "string" ? record.storagePath : "";
  const mimeType = typeof record.mimeType === "string" ? record.mimeType : "";
  const generatedAt = typeof record.generatedAt === "string" ? record.generatedAt : "";
  if (!provider || !model || !voiceId || !textHash || !storagePath || !mimeType || !generatedAt) {
    return undefined;
  }
  return {
    provider,
    model,
    voiceId,
    textHash,
    storagePath,
    mimeType,
    generatedAt,
  };
}

export function normalizeHtmlDeckMeta(raw: unknown): HtmlDeckMeta | null {
  const record = asRecord(raw);
  if (!record) return null;

  const rawSlides = Array.isArray(record.slides) ? record.slides : [];
  const slides = rawSlides.reduce<HtmlDeckSlideMeta[]>((acc, item, index) => {
      const slide = asRecord(item);
      if (!slide) return acc;
      const slideId =
        typeof slide.slideId === "string"
          ? slide.slideId.trim()
          : typeof slide.slide_id === "string"
            ? slide.slide_id.trim()
            : "";
      if (!slideId) return acc;
      const title =
        typeof slide.title === "string" && slide.title.trim()
          ? slide.title.trim()
          : `第 ${index + 1} 页`;
      const rawIndex =
        typeof slide.index === "number" && Number.isFinite(slide.index) ? slide.index : index;
      const speakerNotes =
        typeof slide.speakerNotes === "string"
          ? slide.speakerNotes
          : typeof slide.speaker_notes === "string"
            ? slide.speaker_notes
            : "";
      acc.push({
        index: Math.max(0, Math.trunc(rawIndex)),
        slideId,
        title,
        speakerNotes: speakerNotes || undefined,
        speakerAudio: normalizeSpeakerAudio(slide.speakerAudio ?? slide.speaker_audio),
      });
      return acc;
    }, []);

  const title =
    typeof record.title === "string" && record.title.trim() ? record.title.trim() : "新演示文稿";
  const slideCount =
    typeof record.slideCount === "number" && Number.isFinite(record.slideCount)
      ? Math.max(0, Math.trunc(record.slideCount))
      : typeof record.slide_count === "number" && Number.isFinite(record.slide_count)
        ? Math.max(0, Math.trunc(record.slide_count))
        : slides.length;

  return {
    title,
    slideCount: slideCount || slides.length,
    slides,
  };
}

export function extractHtmlDeckMetaFromPresentation(
  presentation: Presentation | null | undefined
): HtmlDeckMeta | null {
  return normalizeHtmlDeckMeta((presentation as { htmlDeckMeta?: unknown } | null)?.htmlDeckMeta);
}

export function buildHtmlMetaSlides(meta: HtmlDeckMeta | null | undefined): Slide[] {
  return (meta?.slides ?? []).map((slide) => ({
    slideId: slide.slideId,
    layoutType: "html-meta",
    layoutId: "html-meta",
    contentData: { title: slide.title },
    components: [],
    speakerNotes: slide.speakerNotes ?? "",
    speakerAudio: slide.speakerAudio,
  }));
}

export function buildHtmlPresentationShell(
  title: string,
  meta: HtmlDeckMeta | null | undefined,
  previous: Presentation | null | undefined
): Presentation {
  const presentationId =
    previous?.presentationId && previous.presentationId.trim()
      ? previous.presentationId
      : "pres-html";
  const normalizedMeta =
    meta ??
    normalizeHtmlDeckMeta({
      title,
      slideCount: previous?.slides.length ?? 0,
      slides: (previous?.slides ?? []).map((slide, index) => ({
        index,
        slideId: slide.slideId,
        title: String((slide.contentData as Record<string, unknown> | undefined)?.title || `第 ${index + 1} 页`),
        speakerNotes: slide.speakerNotes ?? "",
        speakerAudio: slide.speakerAudio,
      })),
    });

  return {
    presentationId,
    title: normalizedMeta?.title || title || previous?.title || "新演示文稿",
    slides: buildHtmlMetaSlides(normalizedMeta),
    htmlDeckMeta: normalizedMeta ?? undefined,
  };
}

export function updateHtmlDeckMetaSpeakerNotes(
  meta: HtmlDeckMeta | null | undefined,
  slideId: string,
  speakerNotes: string
): HtmlDeckMeta | null {
  if (!meta) return null;
  return {
    ...meta,
    slides: meta.slides.map((slide) =>
      slide.slideId === slideId ? { ...slide, speakerNotes } : slide
    ),
  };
}

export function applySpeakerAudioToHtmlDeckMeta(
  meta: HtmlDeckMeta | null | undefined,
  slideId: string,
  speakerAudio: SpeakerAudio
): HtmlDeckMeta | null {
  if (!meta) return null;
  return {
    ...meta,
    slides: meta.slides.map((slide) =>
      slide.slideId === slideId ? { ...slide, speakerAudio } : slide
    ),
  };
}

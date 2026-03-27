import type { Slide } from "@/types/slide";

export function applySpeakerNotesDraftToSlides(
  slides: Slide[],
  currentSlideIndex: number,
  draft: string
): Slide[] {
  return slides.map((slide, index) => {
    if (index !== currentSlideIndex) return slide;
    const nextNotes = draft.trim().length > 0 ? draft : undefined;
    const currentNotes = slide.speakerNotes ?? "";
    if ((nextNotes ?? "") === currentNotes) return slide;
    return {
      ...slide,
      speakerNotes: nextNotes,
      speakerAudio: undefined,
    };
  });
}

export function buildSpeakerNotesDraftMap(slides: Slide[]): Record<string, string> {
  return Object.fromEntries(slides.map((slide) => [slide.slideId, slide.speakerNotes ?? ""]));
}

export function applySpeakerAudioMetaToSlides(
  slides: Slide[],
  slideId: string,
  speakerAudio: NonNullable<Slide["speakerAudio"]>
): Slide[] {
  return slides.map((slide) =>
    slide.slideId === slideId
      ? {
          ...slide,
          speakerAudio,
        }
      : slide
  );
}

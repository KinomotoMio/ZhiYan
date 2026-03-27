interface SlideSpeakerNotesState {
  slideId: string;
  speakerNotes?: string;
}

interface MergeSpeakerNotesDraftsArgs {
  currentDrafts: Record<string, string>;
  previousSlides?: SlideSpeakerNotesState[] | null;
  currentSlides: SlideSpeakerNotesState[];
}

export function mergeSpeakerNotesDrafts({
  currentDrafts,
  previousSlides,
  currentSlides,
}: MergeSpeakerNotesDraftsArgs): Record<string, string> {
  const previousSlidesById = new Map(
    (previousSlides ?? []).map((slide) => [slide.slideId, slide.speakerNotes ?? ""])
  );

  return Object.fromEntries(
    currentSlides.map((slide) => {
      const currentDraft = currentDrafts[slide.slideId];
      const previousCanonicalNotes = previousSlidesById.get(slide.slideId) ?? "";
      const hasUserDraft =
        typeof currentDraft !== "undefined" && currentDraft !== previousCanonicalNotes;

      return [
        slide.slideId,
        hasUserDraft ? currentDraft : slide.speakerNotes ?? "",
      ];
    })
  );
}

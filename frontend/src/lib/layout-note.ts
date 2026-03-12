import layoutMetadataJson from "@/generated/layout-metadata.json";

type LayoutNoteMetadata = {
  noteTag?: string;
  noteText?: string;
};

const LAYOUT_NOTE_METADATA = Object.fromEntries(
  Object.entries(layoutMetadataJson.layouts).map(([layoutId, metadata]) => [
    layoutId,
    {
      noteTag: (metadata as LayoutNoteMetadata).noteTag ?? undefined,
      noteText: (metadata as LayoutNoteMetadata).noteText ?? undefined,
    },
  ]),
) as Record<string, LayoutNoteMetadata>;

export function getLayoutNoteTag(layoutId: string): string | null {
  return LAYOUT_NOTE_METADATA[layoutId]?.noteTag ?? null;
}

export function getLayoutNoteText(layoutId: string): string | null {
  return LAYOUT_NOTE_METADATA[layoutId]?.noteText ?? null;
}

export function formatLayoutNote(layoutId: string, fallback: string): string {
  const noteTag = getLayoutNoteTag(layoutId);
  const noteText = getLayoutNoteText(layoutId) ?? fallback;
  if (!noteTag) return noteText;
  return `【${noteTag}】${noteText}`;
}

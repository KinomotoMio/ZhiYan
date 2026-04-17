"use client";

// Placeholder: the legacy structured/html carousel was removed with the
// structured deck renderer. The centi-deck renderer (next task) will bring
// back a proper preview component; until then this stub keeps the module
// importable without pulling in deleted dependencies.

import type { Dispatch, SetStateAction } from "react";

interface RecentResultCarouselProps {
  title?: string | null;
  previewSlideIndex?: number;
  setPreviewSlideIndex?: Dispatch<SetStateAction<number>>;
  onOpenCurrentSlide?: () => void;
}

export default function RecentResultCarousel({
  title,
  onOpenCurrentSlide,
}: RecentResultCarouselProps) {
  return (
    <button
      type="button"
      onClick={onOpenCurrentSlide}
      className="flex h-full w-full items-center justify-center rounded-2xl border border-white/60 bg-white/75 px-4 text-center text-sm text-slate-500 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md"
    >
      {title ?? "预览即将上线"}
    </button>
  );
}

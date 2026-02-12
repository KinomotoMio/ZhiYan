"use client";

import type { Slide } from "@/types/slide";
import SlidePreview from "./SlidePreview";

interface SlideThumbnailProps {
  slide: Slide;
  index: number;
  isActive: boolean;
  onClick: () => void;
}

export default function SlideThumbnail({
  slide,
  index,
  isActive,
  onClick,
}: SlideThumbnailProps) {
  return (
    <div className="flex gap-2 items-start">
      <span className="text-xs text-muted-foreground mt-1 w-4 text-right shrink-0">
        {index + 1}
      </span>
      <SlidePreview
        slide={slide}
        onClick={onClick}
        isActive={isActive}
        className="w-full"
      />
    </div>
  );
}

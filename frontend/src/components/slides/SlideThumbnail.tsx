"use client";

import { useRef, useState, useEffect } from "react";
import type { Slide } from "@/types/slide";
import { Skeleton } from "@/components/ui/skeleton";
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
  const ref = useRef<HTMLDivElement>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "100px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="flex gap-2 items-start" ref={ref}>
      <span className="text-xs text-muted-foreground mt-1 w-4 text-right shrink-0">
        {index + 1}
      </span>
      {isVisible ? (
        <SlidePreview
          slide={slide}
          onClick={onClick}
          isActive={isActive}
          className="w-full"
        />
      ) : (
        <Skeleton className="w-full aspect-[16/9] rounded" />
      )}
    </div>
  );
}

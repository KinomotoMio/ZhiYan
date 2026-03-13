"use client";

import { useEffect, useState, type Dispatch, type FocusEvent, type SetStateAction } from "react";
import type { Presentation } from "@/types/slide";
import SlidePreview from "@/components/slides/SlidePreview";

interface RecentResultCarouselProps {
  presentation: Presentation;
  previewSlideIndex: number;
  setPreviewSlideIndex: Dispatch<SetStateAction<number>>;
  isPreviewHovered: boolean;
  setIsPreviewHovered: (value: boolean) => void;
  onOpenCurrentSlide: () => void;
}

export default function RecentResultCarousel({
  presentation,
  previewSlideIndex,
  setPreviewSlideIndex,
  isPreviewHovered,
  setIsPreviewHovered,
  onOpenCurrentSlide,
}: RecentResultCarouselProps) {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);
  const [isFocusWithin, setIsFocusWithin] = useState(false);
  const slides = presentation.slides ?? [];
  const slideCount = slides.length;
  const normalizedSlideIndex =
    slideCount > 0 ? Math.min(previewSlideIndex, slideCount - 1) : 0;
  const currentSlide = slides[normalizedSlideIndex];

  useEffect(() => {
    if (slideCount === 0) {
      setPreviewSlideIndex(0);
      return;
    }
    if (previewSlideIndex >= slideCount) {
      setPreviewSlideIndex(0);
    }
  }, [previewSlideIndex, setPreviewSlideIndex, slideCount]);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;

    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => {
      setPrefersReducedMotion(media.matches);
    };
    sync();

    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", sync);
      return () => media.removeEventListener("change", sync);
    }

    media.addListener(sync);
    return () => media.removeListener(sync);
  }, []);

  const shouldAutoPlay =
    slideCount > 1 && !prefersReducedMotion && !isPreviewHovered && !isFocusWithin;

  useEffect(() => {
    if (!shouldAutoPlay) return;
    const timer = window.setInterval(() => {
      setPreviewSlideIndex((prev) => (prev + 1) % slideCount);
    }, 3500);
    return () => window.clearInterval(timer);
  }, [setPreviewSlideIndex, shouldAutoPlay, slideCount, previewSlideIndex]);

  const handleBlurCapture = (event: FocusEvent<HTMLDivElement>) => {
    const nextTarget = event.relatedTarget;
    if (!nextTarget || !event.currentTarget.contains(nextTarget as Node)) {
      setIsFocusWithin(false);
    }
  };

  if (!currentSlide) {
    return (
      <div className="flex aspect-video items-center justify-center rounded-xl border border-blue-100/70 bg-white/80 text-sm text-slate-500">
        暂无可预览页面
      </div>
    );
  }

  return (
    <div
      onMouseEnter={() => setIsPreviewHovered(true)}
      onMouseLeave={() => setIsPreviewHovered(false)}
      onFocusCapture={() => setIsFocusWithin(true)}
      onBlurCapture={handleBlurCapture}
      className="flex h-full min-h-0 min-w-0 flex-col gap-3"
    >
      <button
        type="button"
        onClick={onOpenCurrentSlide}
        className="group relative block min-w-0 w-full overflow-hidden rounded-xl border border-blue-100/80 bg-white/75 text-left transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/70"
        aria-label={`打开编辑器并定位到第 ${normalizedSlideIndex + 1} 页`}
      >
        <SlidePreview slide={currentSlide} className="w-full border-0 shadow-none" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-slate-900/55 via-slate-900/10 to-transparent px-3 py-2">
          <p className="text-xs font-medium text-white/90">
            第 {normalizedSlideIndex + 1} / {slideCount} 页 · 点击进入编辑器
          </p>
        </div>
      </button>

      <div className="overflow-x-auto pb-1">
        <div className="flex min-w-max gap-2 pr-1">
          {slides.map((slide, index) => {
            const isActive = index === normalizedSlideIndex;
            return (
              <button
                key={slide.slideId}
                type="button"
                onClick={() => setPreviewSlideIndex(index)}
                aria-label={`跳转到第 ${index + 1} 页`}
                aria-current={isActive ? "true" : undefined}
                className={`group shrink-0 rounded-lg border bg-white/85 p-1 transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 ${
                  isActive
                    ? "border-rose-300 ring-2 ring-blue-200/80"
                    : "border-white/60 opacity-75 hover:opacity-100"
                }`}
              >
                <div className="w-32 overflow-hidden rounded-md">
                  <SlidePreview slide={slide} className="w-full border-0 shadow-none" />
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

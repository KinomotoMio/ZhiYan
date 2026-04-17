"use client";

import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type Dispatch,
  type FocusEvent,
  type SetStateAction,
} from "react";
import type { Presentation } from "@/types/slide";
import SlidePreview from "@/components/slides/SlidePreview";
import HtmlRuntimePreview from "@/components/slides/HtmlRuntimePreview";
import { resolveAspectContainSize } from "@/components/slides/HtmlPreviewSurface";
import type { PresentationOutputMode } from "@/lib/api";

interface RecentResultCarouselProps {
  presentation: Presentation;
  outputMode?: PresentationOutputMode;
  htmlContent?: string | null;
  previewSlideIndex: number;
  setPreviewSlideIndex: Dispatch<SetStateAction<number>>;
  isPreviewHovered: boolean;
  setIsPreviewHovered: (value: boolean) => void;
  onOpenCurrentSlide: () => void;
}

export default function RecentResultCarousel({
  presentation,
  outputMode = "structured",
  htmlContent = null,
  previewSlideIndex,
  setPreviewSlideIndex,
  isPreviewHovered,
  setIsPreviewHovered,
  onOpenCurrentSlide,
}: RecentResultCarouselProps) {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);
  const [isFocusWithin, setIsFocusWithin] = useState(false);
  const stageContainerRef = useRef<HTMLDivElement>(null);
  const [stageSize, setStageSize] = useState({ width: 0, height: 0 });
  const slides = presentation.slides ?? [];
  const slideCount = slides.length;
  const normalizedSlideIndex =
    slideCount > 0 ? Math.min(previewSlideIndex, slideCount - 1) : 0;
  const currentSlide = slides[normalizedSlideIndex];
  const isHtmlMode = outputMode === "html" && Boolean(htmlContent);

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

  useEffect(() => {
    const element = stageContainerRef.current;
    if (!element) return;

    const updateSize = (width: number, height: number) => {
      setStageSize(resolveAspectContainSize(width, height));
    };

    updateSize(element.clientWidth, element.clientHeight);

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        updateSize(entry.contentRect.width, entry.contentRect.height);
      }
    });

    observer.observe(element);
    return () => observer.disconnect();
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

  const stageStyle: CSSProperties =
    stageSize.width > 0 && stageSize.height > 0
      ? {
          width: `${stageSize.width}px`,
          height: `${stageSize.height}px`,
        }
      : {
          width: "100%",
          aspectRatio: "16 / 9",
          maxHeight: "100%",
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
      className="grid h-full min-h-0 min-w-0 grid-rows-[minmax(0,1fr)_auto] gap-3"
    >
      <div
        ref={stageContainerRef}
        className="flex min-h-0 min-w-0 items-center justify-center overflow-hidden rounded-2xl border border-white/60 bg-white/35 p-2 sm:p-3"
      >
        <button
          type="button"
          onClick={onOpenCurrentSlide}
          className="group relative block min-h-0 min-w-0 max-h-full max-w-full overflow-hidden rounded-xl border border-blue-100/80 bg-white/75 text-left transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/70"
          style={stageStyle}
          aria-label={`打开编辑器并定位到第 ${normalizedSlideIndex + 1} 页`}
        >
          {isHtmlMode ? (
            <div className="h-full w-full overflow-hidden">
              <HtmlRuntimePreview
                documentHtml={htmlContent}
                startSlide={normalizedSlideIndex}
                className="w-full border-0 shadow-none"
              />
            </div>
          ) : (
            <SlidePreview
              slide={currentSlide}
              className="h-full w-full border-0 shadow-none"
            />
          )}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-slate-900/55 via-slate-900/10 to-transparent px-3 py-2">
            <p className="text-xs font-medium text-white/90">
              第 {normalizedSlideIndex + 1} / {slideCount} 页 · 点击进入编辑器
            </p>
          </div>
        </button>
      </div>

      <div className="overflow-x-auto pb-1">
        <div className="flex min-w-full gap-2 pr-1">
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
                } basis-0 flex-1 min-w-[5.75rem] sm:min-w-[6.5rem] xl:min-w-[7.25rem] max-w-[8.5rem]`}
              >
                <div className="aspect-video w-full overflow-hidden rounded-md">
                  {isHtmlMode ? (
                    <div className="h-full w-full overflow-hidden">
                      <HtmlRuntimePreview
                        documentHtml={htmlContent}
                        startSlide={index}
                        thumbnailMode
                        className="w-full border-0 shadow-none pointer-events-none"
                      />
                    </div>
                  ) : (
                    <SlidePreview slide={slide} className="w-full border-0 shadow-none" />
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";

import type { Presentation } from "@/types/slide";
import RevealPreview from "@/components/slides/RevealPreview";

export function resolveAspectContainSize(
  containerWidth: number,
  containerHeight: number,
  aspectRatio = 16 / 9
): { width: number; height: number } {
  if (
    !Number.isFinite(containerWidth) ||
    !Number.isFinite(containerHeight) ||
    containerWidth <= 0 ||
    containerHeight <= 0
  ) {
    return { width: 0, height: 0 };
  }

  const containerRatio = containerWidth / containerHeight;
  if (containerRatio > aspectRatio) {
    const height = containerHeight;
    return {
      width: Math.floor(height * aspectRatio),
      height: Math.floor(height),
    };
  }

  const width = containerWidth;
  return {
    width: Math.floor(width),
    height: Math.floor(width / aspectRatio),
  };
}

interface HtmlPreviewSurfaceProps {
  presentation?: Presentation | null;
  htmlContent?: string | null;
  startSlide?: number;
  onSlideChange?: (slideIndex: number) => void;
  className?: string;
  frameClassName?: string;
}

export default function HtmlPreviewSurface({
  presentation,
  htmlContent,
  startSlide = 0,
  onSlideChange,
  className = "",
  frameClassName = "",
}: HtmlPreviewSurfaceProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [frameSize, setFrameSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const updateSize = (width: number, height: number) => {
      setFrameSize(resolveAspectContainSize(width, height));
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

  const frameStyle =
    frameSize.width > 0 && frameSize.height > 0
      ? {
          width: `${frameSize.width}px`,
          height: `${frameSize.height}px`,
        }
      : {
          width: "100%",
          aspectRatio: "16 / 9",
          maxHeight: "100%",
        };

  return (
    <div
      ref={containerRef}
      className={`flex h-full w-full items-center justify-center ${className}`}
    >
      <div
        className={`relative overflow-hidden rounded-[20px] ${frameClassName}`}
        style={frameStyle}
      >
        <RevealPreview
          presentation={presentation}
          htmlContent={htmlContent}
          startSlide={startSlide}
          onSlideChange={onSlideChange}
          className="rounded-[20px]"
        />
      </div>
    </div>
  );
}

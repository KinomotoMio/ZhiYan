"use client";

import { useEffect, useMemo, useRef } from "react";

interface SlidevPreviewProps {
  src?: string | null;
  startSlide?: number;
  className?: string;
  onSlideChange?: (slideIndex: number) => void;
}

function buildSlidevPreviewSrc(rawSrc: string, startSlide = 0): string {
  const url = new URL(rawSrc, window.location.origin);
  const safeSlide =
    typeof startSlide === "number" && Number.isFinite(startSlide)
      ? Math.max(0, Math.trunc(startSlide))
      : 0;
  url.hash = `#/${safeSlide + 1}`;
  return url.toString();
}

function getSlidevPreviewSlideIndex(data: unknown): number | null {
  if (!data || typeof data !== "object") return null;
  const payload = data as { type?: unknown; slideIndex?: unknown };
  if (payload.type !== "slidev-preview-slidechange") return null;
  if (typeof payload.slideIndex !== "number" || !Number.isFinite(payload.slideIndex)) {
    return null;
  }
  return Math.max(0, Math.trunc(payload.slideIndex));
}

export default function SlidevPreview({
  src,
  startSlide = 0,
  className = "",
  onSlideChange,
}: SlidevPreviewProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const expectedOrigin = useMemo(() => {
    if (!src) return null;
    try {
      return new URL(src, window.location.origin).origin;
    } catch {
      return null;
    }
  }, [src]);

  useEffect(() => {
    if (!iframeRef.current) return;
    if (!src) {
      iframeRef.current.removeAttribute("src");
      return;
    }
    iframeRef.current.src = buildSlidevPreviewSrc(src, startSlide);
  }, [src, startSlide]);

  useEffect(() => {
    if (!onSlideChange) return;
    const handleMessage = (event: MessageEvent) => {
      if (event.source !== iframeRef.current?.contentWindow) return;
      if (expectedOrigin && event.origin !== expectedOrigin) return;
      const slideIndex = getSlidevPreviewSlideIndex(event.data);
      if (slideIndex === null) return;
      onSlideChange(slideIndex);
    };
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [expectedOrigin, onSlideChange]);

  return (
    <iframe
      ref={iframeRef}
      className={`h-full w-full border-0 ${className}`}
      title="Slidev preview"
      tabIndex={-1}
    />
  );
}

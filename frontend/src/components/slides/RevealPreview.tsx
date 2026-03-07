"use client";

import { useEffect, useRef } from "react";
import type { Presentation } from "@/types/slide";
import { presentationToRevealHTML } from "@/lib/slide-to-reveal";

interface RevealPreviewProps {
  presentation: Presentation;
  startSlide?: number;
  className?: string;
  onSlideChange?: (slideIndex: number) => void;
}

export function buildRevealPreviewSrc(blobUrl: string, startSlide = 0): string {
  const safeStartSlide =
    typeof startSlide === "number" && Number.isFinite(startSlide)
      ? Math.max(0, Math.trunc(startSlide))
      : 0;

  return safeStartSlide > 0 ? `${blobUrl}#/${safeStartSlide}` : blobUrl;
}

export function getRevealPreviewSlideIndex(data: unknown): number | null {
  if (!data || typeof data !== "object") return null;

  const payload = data as { type?: unknown; slideIndex?: unknown };
  if (payload.type !== "reveal-preview-slidechange") return null;
  if (typeof payload.slideIndex !== "number" || !Number.isFinite(payload.slideIndex)) {
    return null;
  }

  return Math.max(0, Math.trunc(payload.slideIndex));
}

type FocusableRevealFrame = {
  focus?: (options?: FocusOptions) => void;
  contentWindow?: {
    focus?: () => void;
  } | null;
};

export function focusRevealPreviewFrame(frame: FocusableRevealFrame | null): void {
  if (!frame) return;

  try {
    frame.focus?.({ preventScroll: true });
  } catch {
    frame.focus?.();
  }

  try {
    frame.contentWindow?.focus?.();
  } catch {
    // Ignore focus failures for sandboxed or not-yet-ready frames.
  }
}

export default function RevealPreview({
  presentation,
  startSlide = 0,
  className = "",
  onSlideChange,
}: RevealPreviewProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    if (!iframeRef.current) return;
    const html = presentationToRevealHTML(presentation);
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    iframeRef.current.src = buildRevealPreviewSrc(url, startSlide);
    return () => URL.revokeObjectURL(url);
  }, [presentation, startSlide]);

  useEffect(() => {
    if (!onSlideChange) return;

    const handleMessage = (event: MessageEvent) => {
      if (event.source !== iframeRef.current?.contentWindow) return;
      if (event.origin !== window.location.origin) return;

      const slideIndex = getRevealPreviewSlideIndex(event.data);
      if (slideIndex === null) return;

      onSlideChange(slideIndex);
    };

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [onSlideChange]);

  return (
    <iframe
      ref={iframeRef}
      className={`w-full h-full border-0 ${className}`}
      title="Presentation preview"
      sandbox="allow-scripts allow-same-origin"
      tabIndex={-1}
      onLoad={() => focusRevealPreviewFrame(iframeRef.current)}
    />
  );
}

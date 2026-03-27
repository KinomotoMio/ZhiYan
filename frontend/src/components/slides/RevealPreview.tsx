"use client";

import { useEffect, useRef } from "react";
import type { Presentation } from "@/types/slide";
import { presentationToRevealHTML } from "@/lib/slide-to-reveal";

const THUMBNAIL_STYLE_MARKER = "data-reveal-preview-thumbnail";
const THUMBNAIL_STYLE_BLOCK = `<style ${THUMBNAIL_STYLE_MARKER}>
  html, body {
    background: transparent !important;
  }
  .reveal {
    background: transparent !important;
  }
  .reveal .controls,
  .reveal .progress,
  .reveal .slide-number {
    display: none !important;
  }
</style>`;

interface RevealPreviewProps {
  presentation?: Presentation | null;
  htmlContent?: string | null;
  startSlide?: number;
  className?: string;
  onSlideChange?: (slideIndex: number) => void;
  thumbnailMode?: boolean;
  autoFocusOnLoad?: boolean;
  listenForSlideChange?: boolean;
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

export function buildRevealPreviewHtml(
  htmlContent: string,
  options?: { thumbnailMode?: boolean }
): string {
  const html = String(htmlContent || "");
  if (!options?.thumbnailMode || !html) return html;
  if (html.includes(THUMBNAIL_STYLE_MARKER)) return html;
  if (/<\/head>/i.test(html)) {
    return html.replace(/<\/head>/i, `${THUMBNAIL_STYLE_BLOCK}\n</head>`);
  }
  return `${THUMBNAIL_STYLE_BLOCK}\n${html}`;
}

export function resolveRevealPreviewBehavior(options?: {
  thumbnailMode?: boolean;
  autoFocusOnLoad?: boolean;
  listenForSlideChange?: boolean;
  hasSlideChangeHandler?: boolean;
}): { autoFocusOnLoad: boolean; listenForSlideChange: boolean } {
  const thumbnailMode = options?.thumbnailMode ?? false;
  return {
    autoFocusOnLoad: (options?.autoFocusOnLoad ?? true) && !thumbnailMode,
    listenForSlideChange:
      (options?.listenForSlideChange ?? true) &&
      !thumbnailMode &&
      Boolean(options?.hasSlideChangeHandler),
  };
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
    try {
      frame.focus?.();
    } catch {
      // Ignore focus failures for sandboxed or not-yet-ready frames.
    }
  }

  try {
    frame.contentWindow?.focus?.();
  } catch {
    // Ignore focus failures for sandboxed or not-yet-ready frames.
  }
}

export default function RevealPreview({
  presentation,
  htmlContent,
  startSlide = 0,
  className = "",
  onSlideChange,
  thumbnailMode = false,
  autoFocusOnLoad = true,
  listenForSlideChange = true,
}: RevealPreviewProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const behavior = resolveRevealPreviewBehavior({
    thumbnailMode,
    autoFocusOnLoad,
    listenForSlideChange,
    hasSlideChangeHandler: Boolean(onSlideChange),
  });

  useEffect(() => {
    if (!iframeRef.current) return;
    const rawHtml = htmlContent ?? (presentation ? presentationToRevealHTML(presentation) : "");
    const html = buildRevealPreviewHtml(rawHtml, { thumbnailMode });
    if (!html) {
      iframeRef.current.removeAttribute("src");
      return;
    }
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    iframeRef.current.src = buildRevealPreviewSrc(url, startSlide);
    return () => URL.revokeObjectURL(url);
  }, [htmlContent, presentation, startSlide, thumbnailMode]);

  useEffect(() => {
    if (!behavior.listenForSlideChange || !onSlideChange) return;

    const handleMessage = (event: MessageEvent) => {
      if (event.source !== iframeRef.current?.contentWindow) return;
      if (event.origin !== window.location.origin) return;

      const slideIndex = getRevealPreviewSlideIndex(event.data);
      if (slideIndex === null) return;

      onSlideChange(slideIndex);
    };

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [behavior.listenForSlideChange, onSlideChange]);

  return (
    <iframe
      ref={iframeRef}
      className={`w-full h-full border-0 ${className}`}
      data-preview-mode={thumbnailMode ? "thumbnail" : "interactive"}
      title="Presentation preview"
      sandbox="allow-scripts allow-same-origin"
      loading={thumbnailMode ? "lazy" : undefined}
      tabIndex={-1}
      onLoad={() => {
        if (!behavior.autoFocusOnLoad) return;
        focusRevealPreviewFrame(iframeRef.current);
      }}
    />
  );
}

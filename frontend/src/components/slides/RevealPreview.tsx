"use client";

import { useEffect, useRef } from "react";
import type { Presentation } from "@/types/slide";
import { presentationToRevealHTML } from "@/lib/slide-to-reveal";

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

export type RevealPreviewMode = "interactive" | "thumbnail";

export interface RevealPreviewConfig {
  slide: number;
  mode: RevealPreviewMode;
}

const PREVIEW_CONFIG_MARKER = "data-zy-reveal-preview-config";

export function resolveRevealPreviewConfig(options?: {
  startSlide?: number;
  thumbnailMode?: boolean;
}): RevealPreviewConfig {
  const slide =
    typeof options?.startSlide === "number" && Number.isFinite(options.startSlide)
      ? Math.max(0, Math.trunc(options.startSlide))
      : 0;

  return {
    slide,
    mode: options?.thumbnailMode ? "thumbnail" : "interactive",
  };
}

export function buildRevealPreviewSrc(
  blobUrl: string,
  options?: { startSlide?: number; thumbnailMode?: boolean }
): string {
  void options;
  return String(blobUrl || "");
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
  options?: { startSlide?: number; thumbnailMode?: boolean }
): string {
  const html = String(htmlContent || "");
  if (!html) return html;

  const config = resolveRevealPreviewConfig(options);
  const serializedConfig = JSON.stringify(config)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026");
  const configScript = `<script ${PREVIEW_CONFIG_MARKER}>window.__ZY_REVEAL_PREVIEW__ = ${serializedConfig};</script>`;
  const configScriptPattern = new RegExp(
    `<script[^>]*${PREVIEW_CONFIG_MARKER}[^>]*>.*?<\\/script>\\s*`,
    "is"
  );

  if (configScriptPattern.test(html)) {
    return html.replace(configScriptPattern, `${configScript}\n`);
  }
  if (/<\/head>/i.test(html)) {
    return html.replace(/<\/head>/i, `${configScript}\n</head>`);
  }
  if (/<script\b/i.test(html)) {
    return html.replace(/<script\b/i, `${configScript}\n<script`);
  }
  if (/<body\b[^>]*>/i.test(html)) {
    return html.replace(/<body\b[^>]*>/i, (match) => `${match}\n${configScript}`);
  }
  return `${configScript}\n${html}`;
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

export function queueRevealPreviewUrlCleanup(
  queue: string[],
  activeUrl: string | null,
  nextActiveUrl: string | null
): string[] {
  if (!activeUrl || activeUrl === nextActiveUrl || queue.includes(activeUrl)) {
    return queue;
  }
  return [...queue, activeUrl];
}

export function flushRevealPreviewUrlCleanupQueue(
  queue: string[],
  activeUrl: string | null,
  revokeUrl: (url: string) => void
): string[] {
  const remaining: string[] = [];
  for (const url of queue) {
    if (!url || url === activeUrl) {
      if (url && !remaining.includes(url)) {
        remaining.push(url);
      }
      continue;
    }
    revokeUrl(url);
  }
  return remaining;
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
  const activeUrlRef = useRef<string | null>(null);
  const cleanupQueueRef = useRef<string[]>([]);
  const behavior = resolveRevealPreviewBehavior({
    thumbnailMode,
    autoFocusOnLoad,
    listenForSlideChange,
    hasSlideChangeHandler: Boolean(onSlideChange),
  });

  useEffect(() => {
    if (!iframeRef.current) return;
    const rawHtml =
      htmlContent ??
      (presentation && !presentation.htmlDeckMeta
        ? presentationToRevealHTML(presentation)
        : "");
    const html = buildRevealPreviewHtml(rawHtml, { startSlide, thumbnailMode });
    if (!html) {
      cleanupQueueRef.current = queueRevealPreviewUrlCleanup(
        cleanupQueueRef.current,
        activeUrlRef.current,
        null
      );
      activeUrlRef.current = null;
      iframeRef.current.removeAttribute("src");
      cleanupQueueRef.current = flushRevealPreviewUrlCleanupQueue(
        cleanupQueueRef.current,
        activeUrlRef.current,
        (url) => URL.revokeObjectURL(url)
      );
      return;
    }
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    cleanupQueueRef.current = queueRevealPreviewUrlCleanup(
      cleanupQueueRef.current,
      activeUrlRef.current,
      url
    );
    activeUrlRef.current = url;
    iframeRef.current.src = buildRevealPreviewSrc(url, { startSlide, thumbnailMode });
  }, [htmlContent, presentation, startSlide, thumbnailMode]);

  useEffect(
    () => () => {
      cleanupQueueRef.current = queueRevealPreviewUrlCleanup(
        cleanupQueueRef.current,
        activeUrlRef.current,
        null
      );
      activeUrlRef.current = null;
      cleanupQueueRef.current = flushRevealPreviewUrlCleanupQueue(
        cleanupQueueRef.current,
        activeUrlRef.current,
        (url) => URL.revokeObjectURL(url)
      );
    },
    []
  );

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
        cleanupQueueRef.current = flushRevealPreviewUrlCleanupQueue(
          cleanupQueueRef.current,
          activeUrlRef.current,
          (url) => URL.revokeObjectURL(url)
        );
        if (!behavior.autoFocusOnLoad) return;
        focusRevealPreviewFrame(iframeRef.current);
      }}
    />
  );
}

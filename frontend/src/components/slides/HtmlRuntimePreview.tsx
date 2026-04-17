"use client";

import { useEffect, useRef, useState } from "react";

import type { HtmlRuntimeRenderPayload } from "@/lib/api";

interface HtmlRuntimePreviewProps {
  renderPayload?: HtmlRuntimeRenderPayload | null;
  documentHtml?: string | null;
  startSlide?: number;
  className?: string;
  onSlideChange?: (slideIndex: number) => void;
  thumbnailMode?: boolean;
  printMode?: boolean;
  autoFocusOnLoad?: boolean;
  listenForSlideChange?: boolean;
}

export function buildHtmlRuntimePreviewSrc(
  blobUrl: string,
  options?: { startSlide?: number; thumbnailMode?: boolean; printMode?: boolean }
): string {
  void options;
  return blobUrl;
}

export function getHtmlRuntimeSlideIndex(data: unknown): number | null {
  if (!data || typeof data !== "object") return null;
  const payload = data as { type?: unknown; slideIndex?: unknown };
  if (payload.type !== "html-runtime-slidechange") return null;
  if (typeof payload.slideIndex !== "number" || !Number.isFinite(payload.slideIndex)) return null;
  return Math.max(0, Math.trunc(payload.slideIndex));
}

type FocusableFrame = {
  focus?: (options?: FocusOptions) => void;
  contentWindow?: {
    focus?: () => void;
  } | null;
};

function focusFrame(frame: FocusableFrame | null): void {
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

function injectHtmlRuntimePreviewConfig(
  html: string,
  options: { startSlide?: number; thumbnailMode?: boolean; printMode?: boolean }
): string {
  if (!html) return html;
  const safeStartSlide =
    typeof options.startSlide === "number" && Number.isFinite(options.startSlide)
      ? Math.max(0, Math.trunc(options.startSlide))
      : 0;
  const mode = options.printMode ? "print" : options.thumbnailMode ? "thumbnail" : "interactive";
  const configScript = `<script>window.__HTML_RUNTIME_PREVIEW_CONFIG=${JSON.stringify({
    slide: safeStartSlide,
    mode,
  })};</script>`;
  const paramsSnippet = `const previewConfig = window.__HTML_RUNTIME_PREVIEW_CONFIG || null;
      const searchParams = new URLSearchParams(window.location.search);
      const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ""));
      const params = {
        get(key) {
          const configuredValue = previewConfig && previewConfig[key];
          if (configuredValue !== undefined && configuredValue !== null) {
            return String(configuredValue);
          }
          return hashParams.get(key) ?? searchParams.get(key);
        },
      };`;

  const nextHeadHtml = html.includes("</head>")
    ? html.replace("</head>", `${configScript}</head>`)
    : `${configScript}${html}`;
  const nextHtml = nextHeadHtml.replace(
    "const params = new URLSearchParams(window.location.search);",
    paramsSnippet
  );
  return nextHtml;
}

export default function HtmlRuntimePreview({
  renderPayload = null,
  documentHtml,
  startSlide = 0,
  className = "",
  onSlideChange,
  thumbnailMode = false,
  printMode = false,
  autoFocusOnLoad = true,
  listenForSlideChange = true,
}: HtmlRuntimePreviewProps) {
  const THUMBNAIL_VIEWPORT_WIDTH = 1280;
  const THUMBNAIL_VIEWPORT_HEIGHT = 720;
  const wrapperRef = useRef<HTMLDivElement>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const blobUrlRef = useRef<string | null>(null);
  const [thumbnailScale, setThumbnailScale] = useState(1);
  const resolvedDocumentHtml = renderPayload?.documentHtml ?? documentHtml ?? null;

  useEffect(() => {
    if (!thumbnailMode || !wrapperRef.current) return;
    const element = wrapperRef.current;
    const updateScale = () => {
      const nextScale = Math.max(
        0.01,
        Math.min(
          element.clientWidth / THUMBNAIL_VIEWPORT_WIDTH,
          element.clientHeight / THUMBNAIL_VIEWPORT_HEIGHT
        )
      );
      setThumbnailScale(nextScale);
    };
    updateScale();
    const observer = new ResizeObserver(() => {
      updateScale();
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [thumbnailMode]);

  useEffect(() => {
    if (!iframeRef.current) return;
    const html = injectHtmlRuntimePreviewConfig(String(resolvedDocumentHtml || ""), {
      startSlide,
      thumbnailMode,
      printMode,
    });
    if (!html) {
      iframeRef.current.removeAttribute("src");
      return;
    }
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    blobUrlRef.current = url;
    iframeRef.current.src = buildHtmlRuntimePreviewSrc(url, {
      startSlide,
      thumbnailMode,
      printMode,
    });
    return () => {
      if (blobUrlRef.current === url) {
        blobUrlRef.current = null;
      }
      URL.revokeObjectURL(url);
    };
  }, [printMode, resolvedDocumentHtml, startSlide, thumbnailMode]);

  useEffect(() => {
    const frame = iframeRef.current;
    if (!frame || !frame.contentWindow || !resolvedDocumentHtml || thumbnailMode || printMode) return;
    frame.contentWindow.postMessage(
      {
        type: "html-runtime-go-to-slide",
        slideIndex: Math.max(0, Math.trunc(startSlide)),
      },
      window.location.origin
    );
  }, [printMode, resolvedDocumentHtml, startSlide, thumbnailMode]);

  useEffect(() => {
    if (!listenForSlideChange || thumbnailMode || !onSlideChange) return;

    const handleMessage = (event: MessageEvent) => {
      if (event.source !== iframeRef.current?.contentWindow) return;
      if (event.origin !== window.location.origin) return;
      const slideIndex = getHtmlRuntimeSlideIndex(event.data);
      if (slideIndex === null) return;
      onSlideChange(slideIndex);
    };

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [listenForSlideChange, thumbnailMode, onSlideChange]);

  return (
    <div ref={wrapperRef} className="relative h-full w-full overflow-hidden">
      <iframe
        ref={iframeRef}
        className={`border-0 ${thumbnailMode ? "absolute left-0 top-0" : "w-full h-full"} ${className}`}
        style={
          thumbnailMode
            ? {
                width: `${THUMBNAIL_VIEWPORT_WIDTH}px`,
                height: `${THUMBNAIL_VIEWPORT_HEIGHT}px`,
                transform: `scale(${thumbnailScale})`,
                transformOrigin: "top left",
              }
            : undefined
        }
        data-preview-mode={printMode ? "print" : thumbnailMode ? "thumbnail" : "interactive"}
        title="HTML runtime preview"
        sandbox="allow-scripts allow-same-origin"
        loading={thumbnailMode || printMode ? "lazy" : undefined}
        tabIndex={-1}
        onLoad={() => {
          if (!autoFocusOnLoad || thumbnailMode || printMode) return;
          focusFrame(iframeRef.current);
        }}
      />
    </div>
  );
}

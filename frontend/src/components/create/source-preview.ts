import type { SourceMeta } from "@/types/source";

export type SourcePreviewKind = "image" | "text";
export type HoverPreviewPlacement = "auto" | "right";

export interface HoverPreviewRect {
  top: number;
  left: number;
  right: number;
  bottom: number;
  width: number;
}

export interface HoverPreviewLayoutOptions {
  triggerRect: HoverPreviewRect;
  viewportWidth: number;
  viewportHeight: number;
  placement?: HoverPreviewPlacement;
  viewportMargin?: number;
  gap?: number;
  maxWidth?: number;
  minWidth?: number;
  widthPadding?: number;
  fallbackHeight?: number;
  minHeight?: number;
  minVisibleHeight?: number;
}

export interface HoverPreviewLayout {
  top: number;
  left: number;
  width: number;
  maxHeight: number;
}

export function canHoverPreviewSource(
  source: Pick<SourceMeta, "fileCategory" | "previewSnippet" | "status">
): boolean {
  if (source.status !== "ready") return false;
  if (source.fileCategory === "image") return true;
  return Boolean(source.previewSnippet);
}

export function getSourcePreviewKind(
  source: Pick<SourceMeta, "fileCategory" | "status">
): SourcePreviewKind {
  if (source.status === "ready" && source.fileCategory === "image") {
    return "image";
  }
  return "text";
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function resolveHoverPreviewLayout({
  triggerRect,
  viewportWidth,
  viewportHeight,
  placement = "auto",
  viewportMargin = 12,
  gap = 8,
  maxWidth = 420,
  minWidth = 300,
  widthPadding = 20,
  fallbackHeight = 240,
  minHeight = 180,
  minVisibleHeight = 96,
}: HoverPreviewLayoutOptions): HoverPreviewLayout {
  const resolvedMaxWidth = Math.min(maxWidth, viewportWidth - viewportMargin * 2);
  const width = Math.min(
    Math.max(triggerRect.width + widthPadding, minWidth),
    resolvedMaxWidth
  );

  if (placement === "right") {
    const maxHeight = Math.max(
      minVisibleHeight,
      viewportHeight - viewportMargin * 2
    );
    const left = clamp(
      triggerRect.right + gap,
      viewportMargin,
      viewportWidth - width - viewportMargin
    );
    const top = clamp(
      triggerRect.top,
      viewportMargin,
      viewportHeight - Math.min(fallbackHeight, maxHeight) - viewportMargin
    );

    return {
      top,
      left,
      width,
      maxHeight,
    };
  }

  const belowSpace = Math.max(
    0,
    viewportHeight - triggerRect.bottom - gap - viewportMargin
  );
  const aboveSpace = Math.max(0, triggerRect.top - gap - viewportMargin);
  const placeBelow = belowSpace >= minHeight || belowSpace >= aboveSpace;
  const availableHeight = placeBelow ? belowSpace : aboveSpace;
  const left = clamp(
    triggerRect.left,
    viewportMargin,
    viewportWidth - width - viewportMargin
  );
  const maxHeight = Math.max(
    Math.min(minVisibleHeight, Math.max(belowSpace, aboveSpace)),
    availableHeight
  );
  const top = placeBelow
    ? triggerRect.bottom + gap
    : Math.max(
        viewportMargin,
        triggerRect.top - gap - Math.min(fallbackHeight, maxHeight)
      );

  return {
    top,
    left,
    width,
    maxHeight,
  };
}

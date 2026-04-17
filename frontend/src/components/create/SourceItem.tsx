"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { createPortal } from "react-dom";
import {
  FileText,
  Globe,
  Type,
  FileImage,
  FileSpreadsheet,
  Presentation,
  X,
  Loader2,
  AlertCircle,
} from "lucide-react";
import type { SourceMeta } from "@/types/source";
import { fetchWorkspaceSourceFile } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  canHoverPreviewSource,
  getSourcePreviewKind,
  resolveHoverPreviewLayout,
  type HoverPreviewPlacement,
} from "@/components/create/source-preview";

const CATEGORY_ICON: Record<string, typeof FileText> = {
  pdf: FileText,
  docx: FileText,
  markdown: FileText,
  pptx: Presentation,
  image: FileImage,
  text: Type,
  unknown: FileSpreadsheet,
};

const HOVER_PREVIEW_VIEWPORT_MARGIN = 12;
const HOVER_PREVIEW_GAP = 8;
const HOVER_PREVIEW_MAX_WIDTH = 420;
const HOVER_PREVIEW_MIN_WIDTH = 300;
const HOVER_PREVIEW_WIDTH_PADDING = 20;
const HOVER_PREVIEW_FALLBACK_HEIGHT = 240;
const HOVER_PREVIEW_MIN_HEIGHT = 180;
const HOVER_PREVIEW_CLOSE_DELAY_MS = 80;
const HOVER_PREVIEW_MIN_VISIBLE_HEIGHT = 96;

function formatSize(bytes: number | undefined): string {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function renderSourceIcon(source: SourceMeta) {
  if (source.type === "url") return <Globe className="h-4 w-4" />;
  if (source.type === "text") return <Type className="h-4 w-4" />;
  const Icon = CATEGORY_ICON[source.fileCategory ?? "unknown"] ?? FileText;
  return <Icon className="h-4 w-4" />;
}

interface SourceItemProps {
  source: SourceMeta;
  isSelected: boolean;
  onToggleSelect: (id: string) => void;
  onRemove?: (id: string) => void;
  onPreview: (source: SourceMeta) => void;
  clickBehavior?: "preview" | "toggle-select";
  showSelectionCheckbox?: boolean;
  showRemove?: boolean;
  extraMeta?: string;
  statusDetail?: string;
  actionLabel?: string;
  onAction?: (source: SourceMeta) => void;
  actionDisabled?: boolean;
  hoverPreviewVariant?: "default" | "assets" | "create";
  hoverPreviewPlacement?: HoverPreviewPlacement;
  hoverPreviewOpenDelayMs?: number;
}

interface HoverPreviewPosition {
  top: number;
  left: number;
  width: number;
  maxHeight: number;
}

export default function SourceItem({
  source,
  isSelected,
  onToggleSelect,
  onRemove,
  onPreview,
  clickBehavior = "preview",
  showSelectionCheckbox = true,
  showRemove = false,
  extraMeta,
  statusDetail,
  actionLabel,
  onAction,
  actionDisabled = false,
  hoverPreviewVariant = "default",
  hoverPreviewPlacement = "auto",
  hoverPreviewOpenDelayMs = 0,
}: SourceItemProps) {
  const [showPopover, setShowPopover] = useState(false);
  const [hoverPreviewPosition, setHoverPreviewPosition] = useState<HoverPreviewPosition | null>(null);
  const [hoverImageUrl, setHoverImageUrl] = useState<string | null>(null);
  const [hoverImageError, setHoverImageError] = useState<string | null>(null);
  const [loadingHoverImage, setLoadingHoverImage] = useState(false);
  const triggerRef = useRef<HTMLDivElement>(null);
  const closeTimeoutRef = useRef<number | null>(null);
  const openTimeoutRef = useRef<number | null>(null);
  const hoverImageObjectUrlRef = useRef<string | null>(null);
  const hoverImageAbortRef = useRef<AbortController | null>(null);
  const isError = source.status === "error";
  const isParsing = source.status === "parsing";
  const isUploading = source.status === "uploading";
  const isReady = source.status === "ready";
  const previewKind = getSourcePreviewKind(source);
  const hasHoverPreview = canHoverPreviewSource(source);
  const isAssetsHoverPreview = hoverPreviewVariant === "assets";
  const isCreateHoverPreview = hoverPreviewVariant === "create";

  useEffect(() => {
    return () => {
      if (closeTimeoutRef.current !== null) {
        window.clearTimeout(closeTimeoutRef.current);
      }
      if (openTimeoutRef.current !== null) {
        window.clearTimeout(openTimeoutRef.current);
      }
      if (hoverImageAbortRef.current) {
        hoverImageAbortRef.current.abort();
      }
      if (hoverImageObjectUrlRef.current) {
        URL.revokeObjectURL(hoverImageObjectUrlRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!showPopover || !hasHoverPreview) return;

    const updateHoverPreviewPosition = () => {
      if (!triggerRef.current) return;

      const triggerRect = triggerRef.current.getBoundingClientRect();
      setHoverPreviewPosition(
        resolveHoverPreviewLayout({
          triggerRect,
          viewportWidth: window.innerWidth,
          viewportHeight: window.innerHeight,
          placement: hoverPreviewPlacement,
          viewportMargin: HOVER_PREVIEW_VIEWPORT_MARGIN,
          gap: HOVER_PREVIEW_GAP,
          maxWidth: HOVER_PREVIEW_MAX_WIDTH,
          minWidth: HOVER_PREVIEW_MIN_WIDTH,
          widthPadding: HOVER_PREVIEW_WIDTH_PADDING,
          fallbackHeight: HOVER_PREVIEW_FALLBACK_HEIGHT,
          minHeight: HOVER_PREVIEW_MIN_HEIGHT,
          minVisibleHeight: HOVER_PREVIEW_MIN_VISIBLE_HEIGHT,
        })
      );
    };

    updateHoverPreviewPosition();
    const frame = window.requestAnimationFrame(updateHoverPreviewPosition);
    window.addEventListener("resize", updateHoverPreviewPosition);
    window.addEventListener("scroll", updateHoverPreviewPosition, true);

    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", updateHoverPreviewPosition);
      window.removeEventListener("scroll", updateHoverPreviewPosition, true);
    };
  }, [
    hasHoverPreview,
    hoverPreviewPlacement,
    hoverPreviewVariant,
    showPopover,
  ]);

  const clearCloseTimeout = () => {
    if (closeTimeoutRef.current !== null) {
      window.clearTimeout(closeTimeoutRef.current);
      closeTimeoutRef.current = null;
    }
  };

  const clearOpenTimeout = () => {
    if (openTimeoutRef.current !== null) {
      window.clearTimeout(openTimeoutRef.current);
      openTimeoutRef.current = null;
    }
  };

  const ensureHoverImageLoaded = () => {
    if (previewKind !== "image" || hoverImageUrl || loadingHoverImage) return;
    if (hoverImageAbortRef.current) {
      hoverImageAbortRef.current.abort();
    }
    const controller = new AbortController();
    hoverImageAbortRef.current = controller;
    setLoadingHoverImage(true);
    setHoverImageError(null);
    fetchWorkspaceSourceFile(source.id, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        const objectUrl = URL.createObjectURL(blob);
        if (hoverImageObjectUrlRef.current) {
          URL.revokeObjectURL(hoverImageObjectUrlRef.current);
        }
        hoverImageObjectUrlRef.current = objectUrl;
        setHoverImageUrl(objectUrl);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setHoverImageError(err instanceof Error ? err.message : "图片加载失败");
      })
      .finally(() => {
        if (hoverImageAbortRef.current === controller) {
          hoverImageAbortRef.current = null;
        }
        if (!controller.signal.aborted) {
          setLoadingHoverImage(false);
        }
      });
  };

  const openHoverPreview = () => {
    if (!hasHoverPreview) return;
    clearCloseTimeout();
    clearOpenTimeout();
    const open = () => {
      if (previewKind === "image") {
        ensureHoverImageLoaded();
      }
      setShowPopover(true);
      openTimeoutRef.current = null;
    };
    if (hoverPreviewOpenDelayMs > 0) {
      openTimeoutRef.current = window.setTimeout(open, hoverPreviewOpenDelayMs);
      return;
    }
    open();
  };

  const scheduleHoverPreviewClose = () => {
    clearCloseTimeout();
    clearOpenTimeout();
    closeTimeoutRef.current = window.setTimeout(() => {
      setShowPopover(false);
      setHoverPreviewPosition(null);
      closeTimeoutRef.current = null;
    }, HOVER_PREVIEW_CLOSE_DELAY_MS);
  };

  const handleItemClick = () => {
    if (!isReady) return;
    if (clickBehavior === "toggle-select") {
      onToggleSelect(source.id);
      return;
    }
    onPreview(source);
  };

  const renderImagePreview = (maxHeightClass: string, loaderHeightClass: string, radiusClass: string) => (
    <div
      className={cn(
        "overflow-hidden border border-slate-200/80 bg-slate-50 dark:border-slate-700/80 dark:bg-slate-900/50",
        radiusClass
      )}
    >
      {hoverImageUrl ? (
        <Image
          src={hoverImageUrl}
          alt={source.name}
          width={1400}
          height={1050}
          unoptimized
          className={cn("h-auto w-full object-contain", maxHeightClass)}
        />
      ) : loadingHoverImage ? (
        <div className={cn("flex items-center justify-center", loaderHeightClass)}>
          <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
        </div>
      ) : hoverImageError ? (
        <p className="px-3 py-6 text-center text-xs text-red-500">{hoverImageError}</p>
      ) : null}
    </div>
  );

  const hoverPreview =
    showPopover &&
    hoverPreviewPosition &&
    typeof document !== "undefined"
      ? createPortal(
          <div className="pointer-events-none fixed inset-0 z-[70]">
            <div
              className={cn(
                "pointer-events-auto fixed overflow-hidden",
                isCreateHoverPreview
                  ? "rounded-[24px] border border-white/85 bg-white/96 p-4 shadow-[0_26px_60px_-36px_rgba(15,23,42,0.42)] backdrop-blur-xl dark:border-slate-700 dark:bg-slate-800/95"
                  : "rounded-lg border border-slate-200 bg-white/92 p-3 shadow-lg backdrop-blur-sm dark:border-slate-700 dark:bg-slate-800/92"
              )}
              style={hoverPreviewPosition}
              onMouseEnter={openHoverPreview}
              onMouseLeave={scheduleHoverPreviewClose}
              onClick={(event) => event.stopPropagation()}
            >
              {isCreateHoverPreview ? (
                <div className="flex max-h-full flex-col gap-2.5">
                  <div className="space-y-1">
                    <p className="break-words text-sm font-medium leading-5 text-slate-900 dark:text-slate-100">
                      {source.name}
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {formatSize(source.size)}
                    </p>
                  </div>
                  <div className="overflow-y-auto">
                    {previewKind === "image" ? (
                      renderImagePreview("max-h-[50vh]", "h-52", "rounded-[18px]")
                    ) : (
                      <p className="text-xs leading-5 text-slate-600 dark:text-slate-300">
                        {source.previewSnippet}
                      </p>
                    )}
                  </div>
                  {extraMeta ? (
                    <p className="border-t border-slate-200/80 pt-2 text-[11px] text-slate-500 dark:border-slate-700/80 dark:text-slate-400">
                      {extraMeta}
                    </p>
                  ) : null}
                </div>
              ) : isAssetsHoverPreview ? (
                <div className="flex max-h-full flex-col gap-2.5">
                  <div className="space-y-1">
                    <p className="break-words text-sm font-medium leading-5 text-slate-900 dark:text-slate-100">
                      {source.name}
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {formatSize(source.size)}
                    </p>
                  </div>
                  <div className="overflow-y-auto">
                    {previewKind === "image" ? (
                      renderImagePreview("max-h-64", "h-40", "rounded-xl")
                    ) : (
                      <p className="text-xs leading-5 text-slate-600 dark:text-slate-300">
                        {source.previewSnippet}
                      </p>
                    )}
                  </div>
                  {extraMeta ? (
                    <p className="border-t border-slate-200/80 pt-2 text-[11px] text-slate-500 dark:border-slate-700/80 dark:text-slate-400">
                      {extraMeta}
                    </p>
                  ) : null}
                </div>
              ) : (
                <div className="flex max-h-full flex-col gap-2">
                  <div className="overflow-y-auto">
                    {previewKind === "image" ? (
                      renderImagePreview("max-h-56", "h-36", "rounded-xl")
                    ) : (
                      <p className="text-xs leading-5 text-slate-500 dark:text-slate-400">
                        {source.previewSnippet}
                      </p>
                    )}
                  </div>
                  {extraMeta ? (
                    <p className="text-[11px] text-slate-500 dark:text-slate-400">{extraMeta}</p>
                  ) : null}
                </div>
              )}
            </div>
          </div>,
          document.body
        )
      : null;

  return (
    <div
      ref={triggerRef}
      className={cn(
        "group relative flex items-center gap-3 rounded-[22px] border px-3.5 py-3 transition-all duration-200",
        isError
          ? "border-red-200 bg-red-50/90 dark:border-red-800 dark:bg-red-950/30"
          : isReady
            ? isSelected
              ? "cursor-pointer border-[rgba(var(--zy-brand-blue),0.18)] bg-[linear-gradient(135deg,rgba(255,255,255,0.98),rgba(241,246,255,0.95))] shadow-[0_20px_42px_-34px_rgba(15,23,42,0.45)]"
              : "cursor-pointer border-white/85 bg-white/78 hover:-translate-y-0.5 hover:border-slate-200 hover:bg-white/92 hover:shadow-[0_18px_36px_-30px_rgba(15,23,42,0.4)] dark:border-slate-700 dark:bg-slate-800/80 dark:hover:border-slate-600 dark:hover:bg-slate-800"
            : "border-white/80 bg-white/70 dark:border-slate-700 dark:bg-slate-800/80"
      )}
      onClick={handleItemClick}
      onMouseEnter={openHoverPreview}
      onMouseLeave={scheduleHoverPreviewClose}
    >
      {isReady && showSelectionCheckbox && (
        <input
          type="checkbox"
          checked={isSelected}
          onChange={() => onToggleSelect(source.id)}
          onClick={(e) => e.stopPropagation()}
          className="h-4 w-4 shrink-0 cursor-pointer rounded border-gray-300 accent-[rgb(var(--zy-brand-blue))]"
        />
      )}

      <div
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl text-slate-500",
          isSelected ? "bg-[rgba(var(--zy-brand-blue),0.08)]" : "bg-slate-100/85"
        )}
      >
        {isParsing || isUploading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : isError ? (
          <AlertCircle className="h-4 w-4 text-red-500" />
        ) : (
          renderSourceIcon(source)
        )}
      </div>

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-800">{source.name}</p>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {statusDetail ? (
            isError ? <span className="text-red-500">{statusDetail}</span> : statusDetail
          ) : isError && source.error ? (
            <span className="text-red-500">{source.error}</span>
          ) : isParsing ? (
            "解析中..."
          ) : isUploading ? (
            "上传中..."
          ) : (
            [formatSize(source.size), extraMeta].filter(Boolean).join(" · ")
          )}
        </p>
      </div>

      {actionLabel && onAction ? (
        <button
          type="button"
          disabled={actionDisabled}
          onClick={(event) => {
            event.stopPropagation();
            onAction(source);
          }}
          className="shrink-0 rounded-full border border-slate-200 px-3 py-1.5 text-xs text-slate-600 transition hover:border-slate-300 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
        >
          {actionLabel}
        </button>
      ) : null}

      {showRemove && onRemove && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemove(source.id);
          }}
          className="shrink-0 rounded-full p-1.5 opacity-0 transition hover:bg-destructive/10 group-hover:opacity-100"
          aria-label="删除来源"
        >
          <X className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500 hover:text-destructive" />
        </button>
      )}

      {hoverPreview}
    </div>
  );
}

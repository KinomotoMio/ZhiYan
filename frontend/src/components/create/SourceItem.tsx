"use client";

import { useEffect, useRef, useState } from "react";
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
import { cn } from "@/lib/utils";

const CATEGORY_ICON: Record<string, typeof FileText> = {
  pdf: FileText,
  docx: FileText,
  markdown: FileText,
  pptx: Presentation,
  image: FileImage,
  text: Type,
  unknown: FileSpreadsheet,
};

const CREATE_HOVER_PREVIEW_VIEWPORT_MARGIN = 12;
const CREATE_HOVER_PREVIEW_GAP = 8;
const CREATE_HOVER_PREVIEW_MAX_WIDTH = 420;
const CREATE_HOVER_PREVIEW_MIN_WIDTH = 320;
const CREATE_HOVER_PREVIEW_WIDTH_PADDING = 20;
const CREATE_HOVER_PREVIEW_FALLBACK_HEIGHT = 240;
const CREATE_HOVER_PREVIEW_MIN_HEIGHT = 180;
const CREATE_HOVER_PREVIEW_CLOSE_DELAY_MS = 80;

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
  showSelectionCheckbox?: boolean;
  showRemove?: boolean;
  extraMeta?: string;
  hoverPreviewVariant?: "default" | "assets" | "create";
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
  showSelectionCheckbox = true,
  showRemove = false,
  extraMeta,
  hoverPreviewVariant = "default",
}: SourceItemProps) {
  const [showPopover, setShowPopover] = useState(false);
  const [hoverPreviewPosition, setHoverPreviewPosition] = useState<HoverPreviewPosition | null>(null);
  const triggerRef = useRef<HTMLDivElement>(null);
  const hoverCardRef = useRef<HTMLDivElement>(null);
  const closeTimeoutRef = useRef<number | null>(null);
  const isError = source.status === "error";
  const isParsing = source.status === "parsing";
  const isUploading = source.status === "uploading";
  const isReady = source.status === "ready";
  const hasHoverPreview = isReady && Boolean(source.previewSnippet);
  const isAssetsHoverPreview = hoverPreviewVariant === "assets";
  const isCreateHoverPreview = hoverPreviewVariant === "create";

  useEffect(() => {
    return () => {
      if (closeTimeoutRef.current !== null) {
        window.clearTimeout(closeTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!isCreateHoverPreview || !showPopover || !hasHoverPreview) return;

    const updateHoverPreviewPosition = () => {
      if (!triggerRef.current) return;

      const triggerRect = triggerRef.current.getBoundingClientRect();
      const viewportMargin = CREATE_HOVER_PREVIEW_VIEWPORT_MARGIN;
      const gap = CREATE_HOVER_PREVIEW_GAP;
      const maxWidth = Math.min(CREATE_HOVER_PREVIEW_MAX_WIDTH, window.innerWidth - viewportMargin * 2);
      const width = Math.min(
        Math.max(triggerRect.width + CREATE_HOVER_PREVIEW_WIDTH_PADDING, CREATE_HOVER_PREVIEW_MIN_WIDTH),
        maxWidth
      );
      const left = Math.max(
        viewportMargin,
        Math.min(triggerRect.left, window.innerWidth - width - viewportMargin)
      );
      const previewHeight = hoverCardRef.current?.offsetHeight ?? CREATE_HOVER_PREVIEW_FALLBACK_HEIGHT;
      const fitsBelow = triggerRect.bottom + gap + previewHeight <= window.innerHeight - viewportMargin;
      const top = fitsBelow
        ? triggerRect.bottom + gap
        : Math.max(viewportMargin, triggerRect.top - previewHeight - gap);
      const maxHeight = fitsBelow
        ? Math.max(CREATE_HOVER_PREVIEW_MIN_HEIGHT, window.innerHeight - top - viewportMargin)
        : Math.max(CREATE_HOVER_PREVIEW_MIN_HEIGHT, triggerRect.top - gap - viewportMargin);

      setHoverPreviewPosition({
        top,
        left,
        width,
        maxHeight,
      });
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
  }, [hasHoverPreview, isCreateHoverPreview, showPopover]);

  const clearCloseTimeout = () => {
    if (closeTimeoutRef.current !== null) {
      window.clearTimeout(closeTimeoutRef.current);
      closeTimeoutRef.current = null;
    }
  };

  const openHoverPreview = () => {
    if (!hasHoverPreview) return;
    clearCloseTimeout();
    setShowPopover(true);
  };

  const closeHoverPreview = () => {
    clearCloseTimeout();
    setShowPopover(false);
    setHoverPreviewPosition(null);
  };

  const scheduleHoverPreviewClose = () => {
    if (!isCreateHoverPreview) {
      closeHoverPreview();
      return;
    }

    clearCloseTimeout();
    closeTimeoutRef.current = window.setTimeout(() => {
      setShowPopover(false);
      setHoverPreviewPosition(null);
      closeTimeoutRef.current = null;
    }, CREATE_HOVER_PREVIEW_CLOSE_DELAY_MS);
  };

  const inlineHoverPreview =
    !isCreateHoverPreview && showPopover && source.previewSnippet ? (
      <div
        className={cn(
          "absolute left-0 top-full z-20 mt-1 rounded-lg border border-slate-200 bg-white/90 p-3 shadow-lg backdrop-blur-sm dark:border-slate-700 dark:bg-slate-800/90",
          "w-full",
          isAssetsHoverPreview && "space-y-2.5"
        )}
      >
        {isAssetsHoverPreview ? (
          <>
            <div className="space-y-1">
              <p className="break-words text-sm font-medium leading-5 text-slate-900 dark:text-slate-100">
                {source.name}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {formatSize(source.size)}
              </p>
            </div>
            <p className="line-clamp-6 text-xs leading-5 text-slate-600 dark:text-slate-300">
              {source.previewSnippet}
            </p>
            {extraMeta ? (
              <p className="border-t border-slate-200/80 pt-2 text-[11px] text-slate-500 dark:border-slate-700/80 dark:text-slate-400">
                {extraMeta}
              </p>
            ) : null}
          </>
        ) : (
          <>
            <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-4">
              {source.previewSnippet}
            </p>
            {extraMeta ? (
              <p className="mt-2 text-[11px] text-slate-500 dark:text-slate-400">{extraMeta}</p>
            ) : null}
          </>
        )}
      </div>
    ) : null;

  const createHoverPreview =
    isCreateHoverPreview &&
    showPopover &&
    source.previewSnippet &&
    hoverPreviewPosition &&
    typeof document !== "undefined"
      ? createPortal(
          <div className="pointer-events-none fixed inset-0 z-[70]">
            <div
              ref={hoverCardRef}
              className="pointer-events-auto fixed overflow-hidden rounded-[24px] border border-white/85 bg-white/96 p-4 shadow-[0_26px_60px_-36px_rgba(15,23,42,0.42)] backdrop-blur-xl dark:border-slate-700 dark:bg-slate-800/95"
              style={hoverPreviewPosition}
              onMouseEnter={openHoverPreview}
              onMouseLeave={scheduleHoverPreviewClose}
              onClick={(event) => event.stopPropagation()}
            >
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
                  <p className="text-xs leading-5 text-slate-600 dark:text-slate-300">
                    {source.previewSnippet}
                  </p>
                </div>
                {extraMeta ? (
                  <p className="border-t border-slate-200/80 pt-2 text-[11px] text-slate-500 dark:border-slate-700/80 dark:text-slate-400">
                    {extraMeta}
                  </p>
                ) : null}
              </div>
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
      onClick={() => isReady && onPreview(source)}
      onMouseEnter={openHoverPreview}
      onMouseLeave={scheduleHoverPreviewClose}
    >
      {/* Checkbox — 仅 ready 状态显示 */}
      {isReady && showSelectionCheckbox && (
        <input
          type="checkbox"
          checked={isSelected}
          onChange={() => onToggleSelect(source.id)}
          onClick={(e) => e.stopPropagation()}
          className="h-4 w-4 shrink-0 cursor-pointer rounded border-gray-300 accent-[rgb(var(--zy-brand-blue))]"
        />
      )}

      {/* 图标 */}
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

      {/* 名称和状态 */}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-800">{source.name}</p>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {isError && source.error ? (
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

      {/* 删除按钮 */}
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

      {inlineHoverPreview}
      {createHoverPreview}
    </div>
  );
}

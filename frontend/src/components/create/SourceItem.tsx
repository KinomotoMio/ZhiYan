"use client";

import { useState } from "react";
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
  hoverPreviewVariant?: "default" | "assets";
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
  const isError = source.status === "error";
  const isParsing = source.status === "parsing";
  const isUploading = source.status === "uploading";
  const isReady = source.status === "ready";
  const isAssetsHoverPreview = hoverPreviewVariant === "assets";

  return (
    <div
      className={cn(
        "group relative flex items-center gap-2 rounded-lg border px-3 py-2.5 transition-colors",
        isError
          ? "border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950/30"
          : isReady
            ? "border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-800/80 hover:-translate-y-0.5 hover:border-slate-300 dark:hover:border-slate-600 hover:bg-white dark:hover:bg-slate-800 hover:shadow-md cursor-pointer transition-all duration-200"
            : "border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-800/80"
      )}
      onClick={() => isReady && onPreview(source)}
      onMouseEnter={() => isReady && source.previewSnippet && setShowPopover(true)}
      onMouseLeave={() => setShowPopover(false)}
    >
      {/* Checkbox — 仅 ready 状态显示 */}
      {isReady && showSelectionCheckbox && (
        <input
          type="checkbox"
          checked={isSelected}
          onChange={() => onToggleSelect(source.id)}
          onClick={(e) => e.stopPropagation()}
          className="h-4 w-4 shrink-0 rounded border-gray-300 text-primary accent-primary cursor-pointer"
        />
      )}

      {/* 图标 */}
      <div className="shrink-0 text-slate-400 dark:text-slate-500">
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
        <p className="truncate text-sm font-medium">{source.name}</p>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {isError && source.error ? (
            <span className="text-red-500">{source.error}</span>
          ) : isParsing ? (
            "解析中..."
          ) : isUploading ? (
            "上传中..."
          ) : (
            formatSize(source.size)
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
          className="shrink-0 rounded-md p-1 opacity-0 transition-opacity hover:bg-destructive/10 group-hover:opacity-100"
          aria-label="删除来源"
        >
          <X className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500 hover:text-destructive" />
        </button>
      )}

      {/* Hover 预览浮层 */}
      {showPopover && source.previewSnippet && (
        <div
          className={cn(
            "absolute left-0 top-full z-20 mt-1 rounded-lg border border-slate-200 bg-white/90 p-3 shadow-lg backdrop-blur-sm dark:border-slate-700 dark:bg-slate-800/90",
            isAssetsHoverPreview ? "w-full space-y-2.5" : "w-full"
          )}
        >
          {isAssetsHoverPreview ? (
            <>
              <div className="space-y-1">
                <p className="text-sm font-medium leading-5 text-slate-900 dark:text-slate-100 break-words">
                  {source.name}
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {formatSize(source.size)}
                </p>
              </div>
              <p className="text-xs leading-5 text-slate-600 dark:text-slate-300 line-clamp-6">
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
      )}
    </div>
  );
}

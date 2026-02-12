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
import type { SourceMeta, FileCategory } from "@/types/source";
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

function getIcon(source: SourceMeta) {
  if (source.type === "url") return Globe;
  if (source.type === "text") return Type;
  return CATEGORY_ICON[source.fileCategory ?? "unknown"] ?? FileText;
}

interface SourceItemProps {
  source: SourceMeta;
  isSelected: boolean;
  onToggleSelect: (id: string) => void;
  onRemove: (id: string) => void;
  onPreview: (source: SourceMeta) => void;
}

export default function SourceItem({
  source,
  isSelected,
  onToggleSelect,
  onRemove,
  onPreview,
}: SourceItemProps) {
  const [showPopover, setShowPopover] = useState(false);
  const Icon = getIcon(source);
  const isError = source.status === "error";
  const isParsing = source.status === "parsing";
  const isUploading = source.status === "uploading";
  const isReady = source.status === "ready";

  return (
    <div
      className={cn(
        "group relative flex items-center gap-2 rounded-lg border px-3 py-2.5 transition-colors",
        isError
          ? "border-red-300 bg-red-50"
          : isReady
            ? "border-border bg-card hover:bg-accent/50 cursor-pointer"
            : "border-border bg-card"
      )}
      onClick={() => isReady && onPreview(source)}
      onMouseEnter={() => isReady && source.previewSnippet && setShowPopover(true)}
      onMouseLeave={() => setShowPopover(false)}
    >
      {/* Checkbox — 仅 ready 状态显示 */}
      {isReady && (
        <input
          type="checkbox"
          checked={isSelected}
          onChange={() => onToggleSelect(source.id)}
          onClick={(e) => e.stopPropagation()}
          className="h-4 w-4 shrink-0 rounded border-gray-300 text-primary accent-primary cursor-pointer"
        />
      )}

      {/* 图标 */}
      <div className="shrink-0 text-muted-foreground">
        {isParsing || isUploading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : isError ? (
          <AlertCircle className="h-4 w-4 text-red-500" />
        ) : (
          <Icon className="h-4 w-4" />
        )}
      </div>

      {/* 名称和状态 */}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{source.name}</p>
        <p className="text-xs text-muted-foreground">
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
      <button
        onClick={(e) => {
          e.stopPropagation();
          onRemove(source.id);
        }}
        className="shrink-0 rounded-md p-1 opacity-0 transition-opacity hover:bg-destructive/10 group-hover:opacity-100"
        aria-label="删除来源"
      >
        <X className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
      </button>

      {/* Hover 预览浮层 */}
      {showPopover && source.previewSnippet && (
        <div className="absolute left-0 top-full z-20 mt-1 w-full rounded-lg border border-border bg-popover p-3 shadow-lg">
          <p className="text-xs text-muted-foreground line-clamp-4">
            {source.previewSnippet}
          </p>
        </div>
      )}
    </div>
  );
}

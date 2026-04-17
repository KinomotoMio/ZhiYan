"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check, FileText, Link, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  canSubmitTextSource,
  canSubmitUrlSource,
  getAvailableAddSourceModes,
  resetAddSourceAreaDrafts,
  type AddSourceMode,
} from "@/components/create/add-source-area-logic";

const ACCEPTED_TYPES = ".pdf,.doc,.docx,.pptx,.ppt,.md,.markdown,.txt,.csv,.json,.png,.jpg,.jpeg,.gif,.webp";

interface AddSourceAreaProps {
  onFilesSelected: (files: File[]) => void;
  onUrlSubmit: (url: string) => void;
  onTextSubmit?: (name: string, content: string) => void;
  variant?: "default" | "assets";
  defaultMode?: AddSourceMode;
}

export default function AddSourceArea({
  onFilesSelected,
  onUrlSubmit,
  onTextSubmit,
  variant = "default",
  defaultMode = "file",
}: AddSourceAreaProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const availableModes = getAvailableAddSourceModes(Boolean(onTextSubmit));
  const resolvedDefaultMode =
    availableModes.includes(defaultMode) ? defaultMode : availableModes[0] ?? "file";
  const [mode, setMode] = useState<AddSourceMode>(resolvedDefaultMode);
  const [urlValue, setUrlValue] = useState("");
  const [textName, setTextName] = useState("");
  const [textContent, setTextContent] = useState("");
  const [isFileDragOver, setIsFileDragOver] = useState(false);

  const resetDrafts = useCallback(() => {
    const next = resetAddSourceAreaDrafts();
    setMode(next.mode);
    setUrlValue(next.urlValue);
    setTextName(next.textName);
    setTextContent(next.textContent);
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) onFilesSelected(files);
    e.target.value = "";
  };

  const handleUrlSubmit = () => {
    const trimmed = urlValue.trim();
    if (!trimmed) return;
    onUrlSubmit(trimmed);
    setUrlValue("");
    if (!isAssetsVariant) {
      resetDrafts();
    }
  };

  const handleUrlKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleUrlSubmit();
    if (e.key === "Escape") {
      resetDrafts();
    }
  };

  const handleTextSubmit = () => {
    if (!onTextSubmit) return;
    const normalizedName = textName.trim();
    const normalizedContent = textContent.trim();
    if (!canSubmitTextSource(normalizedName, normalizedContent)) return;
    onTextSubmit(normalizedName, normalizedContent);
    resetDrafts();
  };

  const handleTextKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      handleTextSubmit();
      return;
    }
    if (e.key === "Escape") {
      resetDrafts();
    }
  };

  useEffect(() => {
    if (mode === "file") return;

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (!target) return;
      if (containerRef.current?.contains(target)) return;
      resetDrafts();
    };

    document.addEventListener("pointerdown", handlePointerDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [mode, resetDrafts]);

  const isAssetsVariant = variant === "assets";
  const showUrlInput = isAssetsVariant || mode === "url";
  const showTextInput = mode === "text" && Boolean(onTextSubmit);

  const handleFileDragOver = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (!event.dataTransfer.types.includes("Files")) return;
    setIsFileDragOver(true);
  };

  const handleFileDragLeave = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    const nextTarget = event.relatedTarget;
    if (nextTarget instanceof Node && event.currentTarget.contains(nextTarget)) {
      return;
    }
    setIsFileDragOver(false);
  };

  const handleFileDrop = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsFileDragOver(false);
    const files = Array.from(event.dataTransfer.files ?? []);
    if (files.length > 0) {
      onFilesSelected(files);
    }
  };

  return (
    <div
      ref={containerRef}
      className={cn(
        "rounded-[24px] border border-white/85 bg-[linear-gradient(180deg,rgba(255,255,255,0.88),rgba(247,249,252,0.82))] p-3 shadow-[0_20px_44px_-36px_rgba(15,23,42,0.42)]",
        isAssetsVariant && "mx-auto max-w-4xl space-y-4 rounded-[28px] p-5 md:p-6"
      )}
    >
      {isAssetsVariant ? (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              onDragOver={handleFileDragOver}
              onDragLeave={handleFileDragLeave}
              onDrop={handleFileDrop}
              className={cn(
                "flex min-h-[164px] flex-col items-center justify-center rounded-[24px] border-2 border-dashed p-6 text-center transition-all duration-200",
                isFileDragOver
                  ? "border-[rgba(var(--zy-brand-blue),0.55)] bg-[linear-gradient(180deg,rgba(239,246,255,0.96),rgba(230,241,255,0.92))] shadow-[0_22px_42px_-30px_rgba(15,23,42,0.42)]"
                  : "border-slate-300/90 bg-[linear-gradient(180deg,rgba(255,255,255,0.94),rgba(243,247,255,0.92))] hover:border-[rgba(var(--zy-brand-blue),0.36)] hover:bg-white hover:shadow-[0_18px_36px_-30px_rgba(15,23,42,0.35)]"
              )}
            >
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[rgba(var(--zy-brand-blue),0.1)] text-[rgb(var(--zy-brand-blue))]">
                <Plus className="h-5 w-5" />
              </span>
              <span className="mt-4 min-w-0">
                <span className="block text-base font-semibold text-slate-900">上传文件</span>
                <span className="mt-2 block text-sm leading-6 text-slate-500">
                  直接把文件拖拽到这里，或点击唤起文件浏览器。
                </span>
              </span>
            </button>

            {onTextSubmit ? (
              <button
                type="button"
                onClick={() => setMode(showTextInput ? "file" : "text")}
                className={cn(
                  "flex min-h-[164px] flex-col items-center justify-center rounded-[24px] border p-6 text-center transition-all duration-200",
                  showTextInput
                    ? "border-[rgba(var(--zy-brand-blue),0.42)] bg-[linear-gradient(180deg,rgba(248,251,255,0.98),rgba(239,246,255,0.94))] ring-2 ring-[rgba(var(--zy-brand-blue),0.14)] shadow-[0_22px_42px_-30px_rgba(15,23,42,0.36)]"
                    : "border-white/85 bg-white/82 text-slate-700 hover:-translate-y-0.5 hover:bg-white hover:shadow-[0_18px_32px_-28px_rgba(15,23,42,0.4)]"
                )}
              >
                <span
                  className={cn(
                    "flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl",
                    showTextInput
                      ? "bg-[rgba(var(--zy-brand-blue),0.12)] text-[rgb(var(--zy-brand-blue))]"
                      : "bg-slate-100 text-slate-600"
                  )}
                >
                  <FileText className="h-5 w-5" />
                </span>
                <span className="mt-4 min-w-0">
                  <span className="block text-base font-semibold text-slate-900">
                    新建文本素材
                  </span>
                  <span className="mt-2 block text-sm leading-6 text-slate-500">
                    手动输入一段内容，保存成可检索的独立素材。
                  </span>
                </span>
              </button>
            ) : null}
          </div>
        </div>
      ) : (
        <>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex w-full items-center justify-center gap-2 rounded-[18px] border border-dashed border-slate-300/90 bg-white/80 px-4 py-3 text-sm font-medium text-slate-600 transition-all duration-200 hover:border-slate-400 hover:bg-white hover:text-slate-900 hover:shadow-[0_16px_32px_-28px_rgba(15,23,42,0.45)]"
          >
            <Plus className="h-4 w-4" />
            添加素材
          </button>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setMode("url")}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs transition-colors",
                showUrlInput
                  ? "bg-slate-900 text-white"
                  : "text-slate-500 hover:bg-white/80 hover:text-slate-700"
              )}
            >
              <Link className="h-3 w-3" />
              粘贴网页链接
            </button>
            {onTextSubmit ? (
              <button
                type="button"
                onClick={() => setMode("text")}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs transition-colors",
                  showTextInput
                    ? "bg-slate-900 text-white"
                    : "text-slate-500 hover:bg-white/80 hover:text-slate-700"
                )}
              >
                <FileText className="h-3 w-3" />
                新建文本素材
              </button>
            ) : null}
          </div>
        </>
      )}
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_TYPES}
        multiple
        className="hidden"
        onChange={handleFileChange}
      />

      {showUrlInput ? (
        <div
          className={cn(
            "mt-3 flex gap-2",
            isAssetsVariant &&
              "items-center rounded-[22px] border border-white/85 bg-white/82 p-3.5 shadow-[0_16px_30px_-28px_rgba(15,23,42,0.28)]"
          )}
        >
          {isAssetsVariant ? (
            <div className="shrink-0 px-1 text-sm font-semibold text-slate-900">
              粘贴网页链接
            </div>
          ) : null}
          <input
            type="url"
            value={urlValue}
            onChange={(e) => setUrlValue(e.target.value)}
            onKeyDown={handleUrlKeyDown}
            placeholder="https://..."
            className={cn(
              "flex-1 rounded-2xl border border-white/90 bg-white/92 px-3 py-2 text-sm text-slate-700 outline-none transition focus:border-cyan-200 focus:ring-2 focus:ring-cyan-500/15",
              isAssetsVariant && "min-w-0 border-slate-200 bg-white px-4 py-3"
            )}
            autoFocus={!isAssetsVariant}
          />
          <button
            onClick={handleUrlSubmit}
            disabled={!canSubmitUrlSource(urlValue)}
            className={cn(
              "rounded-2xl bg-slate-900 px-4 py-2 text-sm text-white transition-colors hover:bg-slate-800 disabled:opacity-50",
              isAssetsVariant && "flex h-12 w-12 items-center justify-center rounded-full p-0"
            )}
            aria-label="提交网页链接"
          >
            {isAssetsVariant ? <Check className="h-4 w-4" /> : "添加"}
          </button>
        </div>
      ) : null}

      {showTextInput ? (
        <div className={cn("mt-3 space-y-2 rounded-[20px] border border-white/85 bg-white/78 p-3", isAssetsVariant && "rounded-[22px] bg-white/82 p-4")}>
          <input
            type="text"
            value={textName}
            onChange={(e) => setTextName(e.target.value)}
            placeholder="素材名称"
            className="w-full rounded-2xl border border-white/90 bg-white/92 px-3 py-2 text-sm text-slate-700 outline-none transition focus:border-cyan-200 focus:ring-2 focus:ring-cyan-500/15"
          />
          <textarea
            value={textContent}
            onChange={(e) => setTextContent(e.target.value)}
            onKeyDown={handleTextKeyDown}
            placeholder="粘贴要保存的正文内容，支持 Ctrl/Cmd + Enter 快速提交"
            className="min-h-28 w-full rounded-2xl border border-white/90 bg-white/92 px-3 py-2 text-sm text-slate-700 outline-none transition focus:border-cyan-200 focus:ring-2 focus:ring-cyan-500/15"
          />
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] text-slate-500">保存后会作为可检索的文本素材进入工作区。</p>
            <button
              onClick={handleTextSubmit}
              disabled={!canSubmitTextSource(textName, textContent)}
              className="rounded-2xl bg-slate-900 px-4 py-2 text-sm text-white transition-colors hover:bg-slate-800 disabled:opacity-50"
            >
              保存文本
            </button>
          </div>
        </div>
      ) : (
        <p className="text-xs text-slate-500">
          {isAssetsVariant
            ? "上传文件支持拖拽或点击，文本素材会在右上区域展开编辑。"
            : "也可以粘贴网页链接补充来源。"}
        </p>
      )}
    </div>
  );
}

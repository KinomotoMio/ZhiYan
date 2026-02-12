"use client";

import { useState, useCallback } from "react";
import { useAppStore } from "@/lib/store";
import { uploadSource, fetchUrlSource, deleteSource } from "@/lib/api";
import SourceItem from "./SourceItem";
import SourcePreviewModal from "./SourcePreviewModal";
import AddSourceArea from "./AddSourceArea";
import { cn } from "@/lib/utils";
import type { SourceMeta } from "@/types/source";

function isUrl(text: string): boolean {
  try {
    const url = new URL(text);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export default function SourcePanel() {
  const {
    sources,
    selectedSourceIds,
    addSource,
    updateSource,
    removeSource,
    toggleSourceSelection,
    selectAllSources,
    deselectAllSources,
  } = useAppStore();
  const [isDragOver, setIsDragOver] = useState(false);
  const [previewSource, setPreviewSource] = useState<SourceMeta | null>(null);

  const readySources = sources.filter((s) => s.status === "ready");
  const selectedCount = readySources.filter((s) =>
    selectedSourceIds.includes(s.id)
  ).length;
  const allSelected =
    readySources.length > 0 && selectedCount === readySources.length;

  const handleUploadFiles = useCallback(
    async (files: File[]) => {
      for (const file of files) {
        const tempId = `temp-${Date.now()}-${file.name}`;
        addSource({
          id: tempId,
          name: file.name,
          type: "file",
          size: file.size,
          status: "uploading",
        });

        try {
          const meta = await uploadSource(file, (pct) => {
            if (pct < 100) {
              updateSource(tempId, { status: "uploading" });
            }
          });
          removeSource(tempId);
          addSource(meta);
        } catch {
          updateSource(tempId, {
            status: "error",
            error: "上传失败",
          });
        }
      }
    },
    [addSource, updateSource, removeSource]
  );

  const handleUrlSubmit = useCallback(
    async (url: string) => {
      const tempId = `temp-url-${Date.now()}`;
      addSource({
        id: tempId,
        name: url,
        type: "url",
        status: "parsing",
      });

      try {
        const meta = await fetchUrlSource(url);
        removeSource(tempId);
        addSource(meta);
      } catch {
        updateSource(tempId, { status: "error", error: "抓取失败" });
      }
    },
    [addSource, removeSource, updateSource]
  );

  const handleRemove = useCallback(
    async (id: string) => {
      removeSource(id);
      deleteSource(id).catch(() => {});
    },
    [removeSource]
  );

  const handleToggleAll = useCallback(() => {
    if (allSelected) {
      deselectAllSources();
    } else {
      selectAllSources();
    }
  }, [allSelected, deselectAllSources, selectAllSources]);

  // 拖拽处理
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);

      const files = Array.from(e.dataTransfer.files);
      if (files.length > 0) {
        handleUploadFiles(files);
        return;
      }

      const text = e.dataTransfer.getData("text/plain");
      if (text && isUrl(text)) {
        handleUrlSubmit(text);
      }
    },
    [handleUploadFiles, handleUrlSubmit]
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent) => {
      const files = Array.from(e.clipboardData.files);
      if (files.length > 0) {
        handleUploadFiles(files);
        return;
      }

      const text = e.clipboardData.getData("text/plain");
      if (text && isUrl(text)) {
        e.preventDefault();
        handleUrlSubmit(text);
      }
    },
    [handleUploadFiles, handleUrlSubmit]
  );

  return (
    <>
      <div
        className={cn(
          "relative flex w-80 shrink-0 flex-col border-r border-border bg-muted/30",
          isDragOver && "ring-2 ring-inset ring-primary/50"
        )}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onPaste={handlePaste}
        tabIndex={0}
      >
        {/* 拖拽高亮遮罩 */}
        {isDragOver && (
          <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-primary/5">
            <p className="text-sm font-medium text-primary">松开以添加来源</p>
          </div>
        )}

        {/* 标题栏 */}
        <div className="border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            {readySources.length > 0 && (
              <input
                type="checkbox"
                checked={allSelected}
                onChange={handleToggleAll}
                className="h-4 w-4 rounded border-gray-300 text-primary accent-primary cursor-pointer"
              />
            )}
            <h2 className="text-sm font-semibold">素材来源</h2>
          </div>
          {sources.length > 0 && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              {readySources.length > 0
                ? `已选择 ${selectedCount}/${readySources.length} 个来源`
                : `已添加 ${sources.length} 个来源`}
            </p>
          )}
        </div>

        {/* 来源列表 */}
        <div className="flex-1 overflow-y-auto px-3 py-2">
          {sources.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center text-sm text-muted-foreground">
              <p>还没有添加来源</p>
              <p className="mt-1 text-xs">
                上传文档、粘贴网址，或直接描述主题
              </p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {sources.map((source) => (
                <SourceItem
                  key={source.id}
                  source={source}
                  isSelected={selectedSourceIds.includes(source.id)}
                  onToggleSelect={toggleSourceSelection}
                  onRemove={handleRemove}
                  onPreview={setPreviewSource}
                />
              ))}
            </div>
          )}
        </div>

        {/* 底部添加区域 */}
        <div className="border-t border-border px-3 py-3">
          <AddSourceArea
            onFilesSelected={handleUploadFiles}
            onUrlSubmit={handleUrlSubmit}
          />
        </div>
      </div>

      {/* 预览弹窗 */}
      {previewSource && (
        <SourcePreviewModal
          source={previewSource}
          onClose={() => setPreviewSource(null)}
        />
      )}
    </>
  );
}

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useAppStore } from "@/lib/store";
import {
  addWorkspaceTextSource,
  bulkDeleteWorkspaceSources,
  fetchWorkspaceUrlSource,
  getCurrentWorkspace,
  listWorkspaceSources,
  uploadWorkspaceSource,
} from "@/lib/api";
import type { SourceMeta } from "@/types/source";
import AddSourceArea from "@/components/create/AddSourceArea";
import SourcePreviewModal from "@/components/create/SourcePreviewModal";
import SourceItem from "@/components/create/SourceItem";
import CircleCheckbox from "@/components/ui/CircleCheckbox";
import {
  createTempFileEntry,
  createTempTextEntry,
  createTempUrlEntry,
  describeAssetEntryStatus,
  getDeletableIds,
  markTempEntryError,
  mergeAssetEntries,
  removeAssetEntry,
  type AssetListEntry,
  type AssetRetryPayload,
  updateTempEntryProgress,
  upsertPersistedSource,
} from "@/components/assets/assets-view-model";

function isUrl(text: string): boolean {
  try {
    const parsed = new URL(text);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || target.isContentEditable;
}

export default function AssetsView() {
  const router = useRouter();
  const setWorkspaceId = useAppStore((store) => store.setWorkspaceId);

  const [items, setItems] = useState<SourceMeta[]>([]);
  const [tempEntries, setTempEntries] = useState<AssetListEntry[]>([]);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<"all" | "file" | "url" | "text">("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "ready" | "error" | "parsing" | "uploading">("all");
  const [sort, setSort] = useState<"created_desc" | "name_asc" | "linked_desc">("created_desc");
  const [loading, setLoading] = useState(false);
  const [selectedForDelete, setSelectedForDelete] = useState<string[]>([]);
  const [previewSource, setPreviewSource] = useState<SourceMeta | null>(null);
  const [deleting, setDeleting] = useState(false);

  const refreshWorkspaceSources = useCallback(async () => {
    setLoading(true);
    try {
      const sources = await listWorkspaceSources({
        q: query,
        type: typeFilter === "all" ? undefined : typeFilter,
        status: statusFilter === "all" ? undefined : statusFilter,
        sort,
        limit: 500,
        offset: 0,
      });
      setItems(sources);
    } finally {
      setLoading(false);
    }
  }, [query, sort, statusFilter, typeFilter]);

  useEffect(() => {
    const run = async () => {
      const workspace = await getCurrentWorkspace();
      setWorkspaceId(workspace.id);
      await refreshWorkspaceSources();
    };
    run().catch((err) => {
      console.error("assets bootstrap failed", err);
    });
  }, [refreshWorkspaceSources, setWorkspaceId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      refreshWorkspaceSources().catch((err) => {
        console.error("refresh workspace sources failed", err);
      });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query, typeFilter, statusFilter, sort, refreshWorkspaceSources]);

  const displayedEntries = useMemo(
    () =>
      mergeAssetEntries({
        persistedItems: items,
        tempEntries,
        query,
        typeFilter,
        statusFilter,
        sort,
      }),
    [items, query, sort, statusFilter, tempEntries, typeFilter]
  );

  const displayedDeletableIds = useMemo(
    () => getDeletableIds(displayedEntries),
    [displayedEntries]
  );

  useEffect(() => {
    setSelectedForDelete((prev) =>
      prev.filter((id) => items.some((item) => item.id === id))
    );
  }, [items]);

  const allDeleteSelected =
    displayedDeletableIds.length > 0 &&
    displayedDeletableIds.every((id) => selectedForDelete.includes(id));

  const toggleDeleteSelection = (id: string) => {
    setSelectedForDelete((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const toggleAllDeleteSelection = () => {
    if (allDeleteSelected) {
      setSelectedForDelete((prev) =>
        prev.filter((id) => !displayedDeletableIds.includes(id))
      );
      return;
    }
    setSelectedForDelete((prev) =>
      Array.from(new Set([...prev, ...displayedDeletableIds]))
    );
  };

  const upsertRealSource = useCallback((source: SourceMeta) => {
    setItems((prev) => upsertPersistedSource(prev, source));
  }, []);

  const finishTempEntry = useCallback((key: string, source: SourceMeta) => {
    setTempEntries((prev) => removeAssetEntry(prev, key));
    upsertRealSource(source);
  }, [upsertRealSource]);

  const failTempEntry = useCallback((key: string, error: string) => {
    setTempEntries((prev) => markTempEntryError(prev, key, error));
  }, []);

  const runFileUpload = useCallback(async (file: File) => {
    const tempEntry = createTempFileEntry(file);
    setTempEntries((prev) => [tempEntry, ...prev]);
    try {
      const meta = await uploadWorkspaceSource(file, (progress) => {
        setTempEntries((prev) => updateTempEntryProgress(prev, tempEntry.key, progress));
      });
      finishTempEntry(tempEntry.key, meta);
      if (meta.deduped) {
        toast.info("检测到重复素材，已复用已有内容");
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : `上传失败: ${file.name}`;
      failTempEntry(tempEntry.key, message);
      toast.error(message);
    }
  }, [failTempEntry, finishTempEntry]);

  const handleUploadFiles = useCallback(async (files: File[]) => {
    await Promise.allSettled(files.map((file) => runFileUpload(file)));
  }, [runFileUpload]);

  const runUrlImport = useCallback(async (url: string) => {
    const tempEntry = createTempUrlEntry(url);
    setTempEntries((prev) => [tempEntry, ...prev]);
    try {
      const meta = await fetchWorkspaceUrlSource(url);
      finishTempEntry(tempEntry.key, meta);
      if (meta.deduped) {
        toast.info("检测到重复素材，已复用已有内容");
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "URL 抓取失败";
      failTempEntry(tempEntry.key, message);
      toast.error(message);
    }
  }, [failTempEntry, finishTempEntry]);

  const handleUrlSubmit = useCallback(async (url: string) => {
    await runUrlImport(url);
  }, [runUrlImport]);

  const runTextImport = useCallback(async (name: string, content: string) => {
    const tempEntry = createTempTextEntry(name, content);
    setTempEntries((prev) => [tempEntry, ...prev]);
    try {
      const meta = await addWorkspaceTextSource(name, content);
      finishTempEntry(tempEntry.key, meta);
      if (meta.deduped) {
        toast.info("检测到重复素材，已复用已有内容");
      } else {
        toast.success("文本素材已保存");
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "文本素材保存失败";
      failTempEntry(tempEntry.key, message);
      toast.error(message);
    }
  }, [failTempEntry, finishTempEntry]);

  const handleTextSubmit = useCallback(async (name: string, content: string) => {
    await runTextImport(name, content);
  }, [runTextImport]);

  const handleRetry = useCallback(async (payload: AssetRetryPayload) => {
    if (payload.kind === "file") {
      await runFileUpload(payload.file);
      return;
    }
    if (payload.kind === "url") {
      await runUrlImport(payload.url);
      return;
    }
    await runTextImport(payload.name, payload.content);
  }, [runFileUpload, runTextImport, runUrlImport]);

  const handleBulkDelete = async () => {
    if (selectedForDelete.length === 0 || deleting) return;
    const selectedItems = items.filter((item) => selectedForDelete.includes(item.id));
    const linkedCount = selectedItems.reduce(
      (sum, item) => sum + (item.linked_session_count ?? 0),
      0
    );
    const confirmMessage = linkedCount > 0
      ? `确认永久删除 ${selectedForDelete.length} 条素材吗？这些素材当前共影响 ${linkedCount} 个会话引用，此操作不可恢复。`
      : `确认永久删除 ${selectedForDelete.length} 条素材吗？此操作不可恢复。`;
    if (!window.confirm(confirmMessage)) {
      return;
    }
    setDeleting(true);
    try {
      const result = await bulkDeleteWorkspaceSources(selectedForDelete);
      setSelectedForDelete([]);
      setItems((prev) => prev.filter((item) => !result.deleted_ids.includes(item.id)));
      toast.success(`已删除 ${result.deleted_ids.length} 条素材`);
      if (result.not_found_ids.length > 0) {
        void refreshWorkspaceSources();
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "批量删除失败");
    } finally {
      setDeleting(false);
    }
  };

  const handlePaste = useCallback((event: React.ClipboardEvent<HTMLDivElement>) => {
    if (isEditableTarget(event.target)) return;
    const files = Array.from(event.clipboardData.files ?? []);
    if (files.length > 0) {
      event.preventDefault();
      void handleUploadFiles(files);
      return;
    }
    const text = event.clipboardData.getData("text/plain");
    if (text && isUrl(text.trim())) {
      event.preventDefault();
      void handleUrlSubmit(text.trim());
    }
  }, [handleUploadFiles, handleUrlSubmit]);

  const emptyStateMessage = loading
    ? "素材加载中..."
    : "拖拽文件、粘贴网页链接，或直接新建文本素材。";

  return (
    <>
      <div className="min-h-screen zy-bg-page">
        <div
          className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-6 py-6"
          onPaste={handlePaste}
          tabIndex={0}
        >
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => router.push("/create")}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white/70 dark:bg-slate-800/70 px-3 py-2 text-sm hover:shadow-md hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-cyan-500/60 transition-all duration-200"
            >
              <ArrowLeft className="h-4 w-4" />
              返回创建页
            </button>
            <h1 className="text-lg font-semibold">Workspace 素材库</h1>
          </div>

          <div className="grid gap-3 rounded-2xl border border-white/80 dark:border-slate-700 bg-white/75 dark:bg-slate-800/75 p-4 md:grid-cols-[2fr_1fr_1fr_1fr_auto]">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索素材名称..."
              className="h-10 rounded-md border border-slate-300 dark:border-slate-600 bg-white/80 dark:bg-slate-800/80 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500/60"
            />
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as typeof typeFilter)}
              className="h-10 rounded-md border border-slate-300 dark:border-slate-600 bg-white/80 dark:bg-slate-800/80 px-2 text-sm"
            >
              <option value="all">全部类型</option>
              <option value="file">文件</option>
              <option value="url">网址</option>
              <option value="text">文本</option>
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
              className="h-10 rounded-md border border-slate-300 dark:border-slate-600 bg-white/80 dark:bg-slate-800/80 px-2 text-sm"
            >
              <option value="all">全部状态</option>
              <option value="ready">可用</option>
              <option value="error">失败</option>
              <option value="parsing">解析中</option>
              <option value="uploading">上传中</option>
            </select>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as typeof sort)}
              className="h-10 rounded-md border border-slate-300 dark:border-slate-600 bg-white/80 dark:bg-slate-800/80 px-2 text-sm"
            >
              <option value="created_desc">最近创建</option>
              <option value="name_asc">名称 A-Z</option>
              <option value="linked_desc">引用最多</option>
            </select>
            <button
              onClick={() => {
                void refreshWorkspaceSources();
              }}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-slate-300 dark:border-slate-600 bg-white/80 dark:bg-slate-800/80 px-3 text-sm hover:shadow-sm transition-all duration-200"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              刷新
            </button>
          </div>

          <div className="relative rounded-2xl border border-white/80 dark:border-slate-700 bg-white/75 dark:bg-slate-800/75 p-4 pb-10">
            <AddSourceArea
              variant="assets"
              onFilesSelected={(files) => {
                void handleUploadFiles(files);
              }}
              onUrlSubmit={(url) => {
                void handleUrlSubmit(url);
              }}
              onTextSubmit={(name, content) => {
                void handleTextSubmit(name, content);
              }}
            />
            <p className="pointer-events-none absolute bottom-4 left-4 text-xs text-slate-500 dark:text-slate-400">
              上传文件支持拖拽或点击，文本素材会在右上区域展开编辑。
            </p>
          </div>

          <div className="flex items-center gap-3">
            <CircleCheckbox
              checked={allDeleteSelected}
              onChange={toggleAllDeleteSelection}
              aria-label="全选删除"
            />
            <span className="text-sm text-slate-500 dark:text-slate-400">
              已选 {selectedForDelete.length} 条
            </span>
            <button
              onClick={() => {
                void handleBulkDelete();
              }}
              disabled={selectedForDelete.length === 0 || deleting}
              className="ml-auto inline-flex items-center gap-2 rounded-md border border-destructive/30 px-3 py-2 text-sm text-destructive disabled:opacity-50"
            >
              {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              批量永久删除
            </button>
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {loading && displayedEntries.length === 0 ? (
              <p className="col-span-full py-10 text-center text-sm text-slate-500 dark:text-slate-400">{emptyStateMessage}</p>
            ) : displayedEntries.length === 0 ? (
              <div className="col-span-full rounded-2xl border border-dashed border-slate-200 bg-white/60 px-6 py-12 text-center dark:border-slate-700 dark:bg-slate-800/40">
                <p className="text-sm font-medium text-slate-700 dark:text-slate-200">素材库还是空的</p>
                <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{emptyStateMessage}</p>
              </div>
            ) : (
              displayedEntries.map((entry) => {
                const source = entry.source;
                const canDelete = !entry.isTemp;
                const statusDetail =
                  source.status === "error"
                    ? source.error || "导入失败，请重试"
                    : describeAssetEntryStatus(entry);
                const retryPayload = entry.retryPayload;
                return (
                  <div
                    key={entry.key}
                    className="relative z-0 flex h-full min-h-[96px] items-center gap-3 rounded-2xl border border-slate-200 bg-white/85 p-3 transition-all duration-200 hover:z-30 hover:-translate-y-0.5 hover:shadow-[0_18px_36px_-28px_rgba(15,23,42,0.35)] focus-within:z-30 dark:border-slate-700 dark:bg-slate-800/85"
                  >
                    {canDelete ? (
                      <CircleCheckbox
                        checked={selectedForDelete.includes(source.id)}
                        onChange={() => toggleDeleteSelection(source.id)}
                        aria-label="选择用于删除"
                      />
                    ) : (
                      <div className="h-5 w-5 shrink-0 rounded-full border border-dashed border-slate-300/80 bg-white/60" />
                    )}
                    <div className="min-w-0 flex-1">
                      <SourceItem
                        source={source}
                        isSelected={false}
                        onToggleSelect={() => {}}
                        onPreview={setPreviewSource}
                        showSelectionCheckbox={false}
                        showRemove={false}
                        hoverPreviewVariant="assets"
                        statusDetail={statusDetail}
                        actionLabel={entry.isTemp && source.status === "error" ? "重试" : undefined}
                        onAction={
                          retryPayload
                            ? () => {
                                setTempEntries((prev) => removeAssetEntry(prev, entry.key));
                                void handleRetry(retryPayload);
                              }
                            : undefined
                        }
                        extraMeta={
                          typeof source.linked_session_count === "number"
                            ? `已关联 ${source.linked_session_count} 个会话`
                            : undefined
                        }
                      />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {previewSource ? (
        <SourcePreviewModal
          key={previewSource.id}
          source={previewSource}
          onClose={() => setPreviewSource(null)}
        />
      ) : null}
    </>
  );
}

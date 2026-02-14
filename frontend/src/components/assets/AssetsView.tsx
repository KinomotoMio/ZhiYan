"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useAppStore } from "@/lib/store";
import {
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

export default function AssetsView() {
  const router = useRouter();
  const setWorkspaceId = useAppStore((store) => store.setWorkspaceId);

  const [items, setItems] = useState<SourceMeta[]>([]);
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

  const allDeleteSelected =
    items.length > 0 && selectedForDelete.length > 0 && selectedForDelete.length === items.length;

  const toggleDeleteSelection = (id: string) => {
    setSelectedForDelete((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const toggleAllDeleteSelection = () => {
    if (allDeleteSelected) {
      setSelectedForDelete([]);
      return;
    }
    setSelectedForDelete(items.map((item) => item.id));
  };

  const handleBulkDelete = async () => {
    if (selectedForDelete.length === 0 || deleting) return;
    if (!window.confirm(`确认永久删除 ${selectedForDelete.length} 条素材吗？此操作不可恢复。`)) {
      return;
    }
    setDeleting(true);
    try {
      const result = await bulkDeleteWorkspaceSources(selectedForDelete);
      setSelectedForDelete([]);
      await refreshWorkspaceSources();
      toast.success(`已删除 ${result.deleted_ids.length} 条素材`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "批量删除失败");
    } finally {
      setDeleting(false);
    }
  };

  const handleUploadFiles = async (files: File[]) => {
    for (const file of files) {
      try {
        const meta = await uploadWorkspaceSource(file);
        if (meta.deduped) {
          toast.info("检测到重复素材，已复用已有内容");
        }
      } catch {
        toast.error(`上传失败: ${file.name}`);
      }
    }
    await refreshWorkspaceSources();
  };

  const handleUrlSubmit = async (url: string) => {
    try {
      const meta = await fetchWorkspaceUrlSource(url);
      if (meta.deduped) {
        toast.info("检测到重复素材，已复用已有内容");
      }
      await refreshWorkspaceSources();
    } catch {
      toast.error("URL 抓取失败");
    }
  };

  return (
    <>
      <div className="min-h-screen zy-bg-page">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-6 py-6">
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => router.push("/create")}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white/70 dark:bg-slate-800/70 px-3 py-2 text-sm hover:shadow-md hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-cyan-500/60 transition-all duration-200"
            >
              <ArrowLeft className="h-4 w-4" />
              返回创建页
            </button>
            <h1 className="text-lg font-semibold">Workspace 素材库</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">Workspace 级素材管理</p>
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
              className="h-10 rounded-md border border-slate-300 dark:border-slate-600 bg-white/80 dark:bg-slate-800/80 px-3 text-sm hover:shadow-sm transition-all duration-200"
            >
              刷新
            </button>
          </div>

          <div className="rounded-2xl border border-white/80 dark:border-slate-700 bg-white/75 dark:bg-slate-800/75 p-4">
            <AddSourceArea
              onFilesSelected={(files) => {
                void handleUploadFiles(files);
              }}
              onUrlSubmit={(url) => {
                void handleUrlSubmit(url);
              }}
            />
          </div>

          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={allDeleteSelected}
              onChange={toggleAllDeleteSelection}
              className="h-4 w-4 rounded border-gray-300 accent-primary"
              aria-label="全选删除"
            />
            <span className="text-sm text-slate-500 dark:text-slate-400">
              已选 {selectedForDelete.length} 条用于批量删除
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

          <div className="space-y-2">
            {loading ? (
              <p className="py-10 text-center text-sm text-slate-500 dark:text-slate-400">素材加载中...</p>
            ) : items.length === 0 ? (
              <p className="py-10 text-center text-sm text-slate-500 dark:text-slate-400">暂无素材</p>
            ) : (
              items.map((source) => (
                <div key={source.id} className="flex items-start gap-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-800/80 p-2 hover:shadow-sm transition-all duration-200">
                  <input
                    type="checkbox"
                    checked={selectedForDelete.includes(source.id)}
                    onChange={() => toggleDeleteSelection(source.id)}
                    className="mt-3 h-4 w-4 rounded border-gray-300 accent-primary"
                    aria-label="选择用于删除"
                  />
                  <div className="min-w-0 flex-1">
                    <SourceItem
                      source={source}
                      isSelected={false}
                      onToggleSelect={() => {}}
                      onPreview={setPreviewSource}
                      showSelectionCheckbox={false}
                      showRemove={false}
                      extraMeta={
                        typeof source.linked_session_count === "number"
                          ? `已关联 ${source.linked_session_count} 个会话`
                          : undefined
                      }
                    />
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {previewSource ? (
        <SourcePreviewModal source={previewSource} onClose={() => setPreviewSource(null)} />
      ) : null}
    </>
  );
}

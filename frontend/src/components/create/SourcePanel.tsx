"use client";

import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { FolderOpen } from "lucide-react";
import { toast } from "sonner";
import { useAppStore, type ChatMessage } from "@/lib/store";
import {
  appendSessionChat,
  createSession,
  createSessionSnapshot,
  fetchWorkspaceUrlSource,
  getJob,
  getCurrentWorkspace,
  getSessionDetail,
  linkSourcesToSession,
  listSessions,
  listWorkspaceSources,
  unlinkSourceFromSession,
  uploadWorkspaceSource,
} from "@/lib/api";
import SourceItem from "./SourceItem";
import SourcePreviewModal from "./SourcePreviewModal";
import AddSourceArea from "./AddSourceArea";
import { cn } from "@/lib/utils";
import {
  getSessionEditorPath,
  shouldAutoRedirectToEditor,
} from "@/lib/routes";
import type { SourceMeta } from "@/types/source";
import type { Presentation, Slide } from "@/types/slide";

const MIGRATION_FLAG_KEY = "zhiyan-session-migrated-v1";

function isUrl(text: string): boolean {
  try {
    const url = new URL(text);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function readLegacyStore() {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem("zhiyan-store");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { state?: Record<string, unknown> };
    return parsed.state || null;
  } catch {
    return null;
  }
}

function toStoreChatMessages(records: Array<Record<string, unknown>>): ChatMessage[] {
  return records
    .map((item) => {
      const role = item.role === "assistant" ? "assistant" : "user";
      const content = typeof item.content === "string" ? item.content : "";
      const createdAt = typeof item.created_at === "string" ? item.created_at : "";
      return {
        id: typeof item.id === "string" ? item.id : `msg-${Math.random().toString(36).slice(2)}`,
        role,
        content,
        timestamp: Date.parse(createdAt) || Date.now(),
      } as ChatMessage;
    })
    .filter((item) => item.content.trim().length > 0);
}

type SourceFilterMode = "all" | "selected" | "unselected";

type HydratedGenerationJob = {
  slides?: Slide[];
  request?: { title?: string };
  issues?: Array<Record<string, unknown>>;
  failed_slide_indices?: number[];
  hard_issue_slide_ids?: string[];
  advisory_issue_count?: number;
  fix_preview_slides?: Slide[];
  fix_preview_source_ids?: string[];
};

function toTimestamp(source: SourceMeta): number {
  const raw = source.created_at;
  if (!raw) return 0;
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : 0;
}

export default function SourcePanel() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preferredSessionId = searchParams.get("session");
  const {
    setWorkspaceId,
    setSessions,
    upsertSession,
    currentSessionId,
    setCurrentSessionId,
    setSessionData,
    updateJobState,
    setIsGenerating,
    workspaceSources,
    setWorkspaceSources,
    addWorkspaceSource,
    updateWorkspaceSource,
    removeWorkspaceSource,
    selectedSourceIds,
    addSelectedSource,
    removeSelectedSource,
    selectAllSources,
    deselectAllSources,
  } = useAppStore();

  const [workspaceQuery, setWorkspaceQuery] = useState("");
  const [loadingWorkspaceSources, setLoadingWorkspaceSources] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [previewSource, setPreviewSource] = useState<SourceMeta | null>(null);
  const [sourceFilterMode, setSourceFilterMode] = useState<SourceFilterMode>("all");
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const bootstrappedRef = useRef(false);
  const effectiveSelectedSourceIds = useMemo(
    () => (isBootstrapping ? [] : selectedSourceIds),
    [isBootstrapping, selectedSourceIds]
  );

  const readySources = workspaceSources.filter((s) => s.status === "ready");
  const selectedCount = readySources.filter((s) =>
    effectiveSelectedSourceIds.includes(s.id)
  ).length;
  const allSelected = readySources.length > 0 && selectedCount === readySources.length;

  const visibleSources = useMemo(() => {
    const selectedSet = new Set(effectiveSelectedSourceIds);
    const filtered = workspaceSources.filter((source) => {
      if (workspaceQuery.trim()) {
        const normalized = workspaceQuery.trim().toLowerCase();
        if (!source.name.toLowerCase().includes(normalized)) {
          return false;
        }
      }
      if (sourceFilterMode === "selected") return selectedSet.has(source.id);
      if (sourceFilterMode === "unselected") return !selectedSet.has(source.id);
      return true;
    });
    return filtered.sort((a, b) => {
      const selectedA = selectedSet.has(a.id) ? 1 : 0;
      const selectedB = selectedSet.has(b.id) ? 1 : 0;
      if (selectedA !== selectedB) return selectedB - selectedA;
      return toTimestamp(b) - toTimestamp(a);
    });
  }, [effectiveSelectedSourceIds, sourceFilterMode, workspaceQuery, workspaceSources]);

  const refreshSessions = useCallback(
    async (q = "") => {
      const result = await listSessions({ q, limit: 100, offset: 0 });
      setSessions(result);
      return result;
    },
    [setSessions]
  );

  const refreshWorkspaceSources = useCallback(
    async () => {
      setLoadingWorkspaceSources(true);
      try {
        const result = await listWorkspaceSources({
          sort: "created_desc",
          limit: 300,
          offset: 0,
        });
        setWorkspaceSources(result);
        return result;
      } finally {
        setLoadingWorkspaceSources(false);
      }
    },
    [setWorkspaceSources]
  );

  const loadSession = useCallback(
    async (
      sessionId: string,
      options?: {
        fromExplicitSessionParam?: boolean;
      }
    ) => {
      const detail = await getSessionDetail(sessionId);
      const chatMessages = toStoreChatMessages(
        detail.chat_messages as unknown as Array<Record<string, unknown>>
      );
      const currentStore = useAppStore.getState();
      const resolvedJobStatus =
        detail.latest_generation_job?.status === "pending" &&
        currentStore.jobId === detail.latest_generation_job.job_id &&
        currentStore.jobStatus === "running"
          ? "running"
          : detail.latest_generation_job?.status ?? null;
      let hydratedJob: HydratedGenerationJob | null = null;
      let hydratedPresentation = detail.latest_presentation?.presentation ?? null;
      const shouldHydrateJob =
        Boolean(detail.latest_generation_job?.job_id) &&
        (resolvedJobStatus === "running" ||
          resolvedJobStatus === "waiting_fix_review" ||
          resolvedJobStatus === "completed");
      if (shouldHydrateJob && detail.latest_generation_job?.job_id) {
        try {
          const job = await getJob(detail.latest_generation_job.job_id);
          hydratedJob = job as unknown as HydratedGenerationJob;
          if (!hydratedPresentation && Array.isArray(job.slides) && job.slides.length > 0) {
            hydratedPresentation = {
              presentationId:
                (typeof job.presentation?.presentationId === "string" &&
                job.presentation.presentationId.trim()
                  ? job.presentation.presentationId
                  : "pres-skeleton"),
              title:
                (typeof job.request?.title === "string" && job.request.title.trim()) ||
                "生成中...",
              slides: job.slides,
            };
          }
        } catch {
          hydratedJob = null;
        }
      }
      setCurrentSessionId(sessionId);
      upsertSession(detail.session);
      setSessionData({
        sources: detail.sources,
        chatMessages,
        presentation: hydratedPresentation,
      });
      if (detail.latest_generation_job?.job_id) {
        updateJobState({
          jobId: detail.latest_generation_job.job_id,
          jobStatus: resolvedJobStatus,
          currentStage: null,
          lastJobEventSeq: 0,
          issues:
            hydratedJob && Array.isArray(hydratedJob.issues)
              ? hydratedJob.issues
              : [],
          failedSlideIndices:
            hydratedJob && Array.isArray(hydratedJob.failed_slide_indices)
              ? hydratedJob.failed_slide_indices
              : [],
          hardIssueSlideIds:
            hydratedJob && Array.isArray(hydratedJob.hard_issue_slide_ids)
              ? hydratedJob.hard_issue_slide_ids
              : [],
          advisoryIssueCount:
            hydratedJob && typeof hydratedJob.advisory_issue_count === "number"
              ? hydratedJob.advisory_issue_count
              : 0,
          fixPreviewSlides:
            hydratedJob && Array.isArray(hydratedJob.fix_preview_slides)
              ? hydratedJob.fix_preview_slides
              : [],
          fixPreviewSourceIds:
            hydratedJob && Array.isArray(hydratedJob.fix_preview_source_ids)
              ? hydratedJob.fix_preview_source_ids
              : [],
          selectedFixPreviewSlideIds:
            hydratedJob && Array.isArray(hydratedJob.fix_preview_source_ids)
              ? hydratedJob.fix_preview_source_ids
              : [],
        });
        setIsGenerating(resolvedJobStatus === "running");
      } else {
        updateJobState({
          jobId: null,
          jobStatus: null,
          currentStage: null,
          lastJobEventSeq: 0,
          issues: [],
          failedSlideIndices: [],
          hardIssueSlideIds: [],
          advisoryIssueCount: 0,
          fixPreviewSlides: [],
          fixPreviewSourceIds: [],
          selectedFixPreviewSlideIds: [],
        });
        setIsGenerating(false);
      }

      if (
        shouldAutoRedirectToEditor(
          Boolean(detail.latest_presentation),
          Boolean(options?.fromExplicitSessionParam)
        )
      ) {
        router.push(getSessionEditorPath(sessionId));
      }
    },
    [router, setCurrentSessionId, setIsGenerating, setSessionData, updateJobState, upsertSession]
  );

  const createAndOpenSession = useCallback(
    async (title: string) => {
      const created = await createSession(title);
      upsertSession(created);
      await loadSession(created.id, { fromExplicitSessionParam: false });
      return created.id;
    },
    [loadSession, upsertSession]
  );

  useEffect(() => {
    if (bootstrappedRef.current) return;
    bootstrappedRef.current = true;

    let cancelled = false;
    let finished = false;
    const run = async () => {
      setIsBootstrapping(true);
      const workspace = await getCurrentWorkspace();
      setWorkspaceId(workspace.id);

      let items = await refreshSessions();
      await refreshWorkspaceSources();
      if (cancelled) return;

      if (items.length === 0) {
        const legacy = readLegacyStore();
        const migrated = typeof window !== "undefined" && window.localStorage.getItem(MIGRATION_FLAG_KEY) === "1";
        const legacyPresentation = legacy?.presentation as Record<string, unknown> | undefined;
        const legacyChats = Array.isArray(legacy?.chatMessages)
          ? (legacy?.chatMessages as Array<Record<string, unknown>>)
          : [];
        const legacyTopic = typeof legacy?.topic === "string" ? legacy.topic.trim() : "";
        const hasLegacyData =
          Boolean(legacyPresentation) || legacyChats.length > 0 || legacyTopic.length > 0;

        if (hasLegacyData && !migrated) {
          const migratedSessionId = await createAndOpenSession("本地迁移会话");
          if (legacyPresentation) {
            await createSessionSnapshot(
              migratedSessionId,
              "本地迁移快照",
              legacyPresentation as unknown as Presentation
            ).catch(() => {});
          }
          for (const msg of legacyChats) {
            const role = msg.role === "assistant" ? "assistant" : "user";
            const content = typeof msg.content === "string" ? msg.content : "";
            if (!content.trim()) continue;
            await appendSessionChat(migratedSessionId, { role, content }).catch(() => {});
          }
          if (typeof window !== "undefined") {
            window.localStorage.setItem(MIGRATION_FLAG_KEY, "1");
          }
          items = await refreshSessions();
          if (cancelled) return;
          await loadSession(migratedSessionId, { fromExplicitSessionParam: false });
          await refreshWorkspaceSources();
          return;
        }

        const sid = await createAndOpenSession("未命名会话");
        items = await refreshSessions();
        if (cancelled) return;
        await loadSession(sid, { fromExplicitSessionParam: false });
        await refreshWorkspaceSources();
        return;
      }

      if (preferredSessionId && items.some((item) => item.id === preferredSessionId)) {
        await loadSession(preferredSessionId, { fromExplicitSessionParam: true });
        return;
      }

      if (currentSessionId && items.some((item) => item.id === currentSessionId)) {
        await loadSession(currentSessionId, { fromExplicitSessionParam: false });
        return;
      }

      await createAndOpenSession("未命名会话");
    };

    run().catch((err) => {
      console.error("session bootstrap failed", err);
    }).finally(() => {
      finished = true;
      if (!cancelled) {
        setIsBootstrapping(false);
      }
    });

    return () => {
      cancelled = true;
      // React Strict Mode will teardown immediately once in dev.
      // If bootstrap has not finished yet, allow a second setup run.
      if (!finished) {
        bootstrappedRef.current = false;
      }
    };
  }, [
    createAndOpenSession,
    currentSessionId,
    loadSession,
    preferredSessionId,
    refreshSessions,
    refreshWorkspaceSources,
    setWorkspaceId,
  ]);

  const ensureSession = useCallback(async () => {
    if (currentSessionId) return currentSessionId;
    return createAndOpenSession("未命名会话");
  }, [createAndOpenSession, currentSessionId]);

  const handleUploadFiles = useCallback(
    async (files: File[]) => {
      const sessionId = await ensureSession();
      for (const file of files) {
        const tempId = `temp-${Date.now()}-${file.name}`;
        addWorkspaceSource({
          id: tempId,
          name: file.name,
          type: "file",
          size: file.size,
          status: "uploading",
        });

        try {
          const meta = await uploadWorkspaceSource(file, (pct) => {
            if (pct < 100) {
              updateWorkspaceSource(tempId, { status: "uploading" });
            }
          });
          await linkSourcesToSession(sessionId, [meta.id]);
          removeWorkspaceSource(tempId);
          addSelectedSource(meta.id);
          await refreshWorkspaceSources();
          refreshSessions().catch(() => {});
          if (meta.deduped) {
            toast.info("检测到重复素材，已复用已有内容");
          }
        } catch {
          updateWorkspaceSource(tempId, {
            status: "error",
            error: "上传失败",
          });
        }
      }
    },
    [
      addSelectedSource,
      addWorkspaceSource,
      ensureSession,
      refreshSessions,
      refreshWorkspaceSources,
      removeWorkspaceSource,
      updateWorkspaceSource,
    ]
  );

  const handleUrlSubmit = useCallback(
    async (url: string) => {
      const sessionId = await ensureSession();
      const tempId = `temp-url-${Date.now()}`;
      addWorkspaceSource({
        id: tempId,
        name: url,
        type: "url",
        status: "parsing",
      });

      try {
        const meta = await fetchWorkspaceUrlSource(url);
        await linkSourcesToSession(sessionId, [meta.id]);
        removeWorkspaceSource(tempId);
        addSelectedSource(meta.id);
        await refreshWorkspaceSources();
        refreshSessions().catch(() => {});
        if (meta.deduped) {
          toast.info("检测到重复素材，已复用已有内容");
        }
      } catch {
        updateWorkspaceSource(tempId, { status: "error", error: "抓取失败" });
      }
    },
    [
      addSelectedSource,
      addWorkspaceSource,
      ensureSession,
      refreshSessions,
      refreshWorkspaceSources,
      removeWorkspaceSource,
      updateWorkspaceSource,
    ]
  );

  const handleToggleSessionSource = useCallback(
    async (sourceId: string) => {
      if (isBootstrapping) return;
      const sessionId = await ensureSession();
      const selected = effectiveSelectedSourceIds.includes(sourceId);
      if (selected) {
        removeSelectedSource(sourceId);
        try {
          await unlinkSourceFromSession(sessionId, sourceId);
        } catch {
          addSelectedSource(sourceId);
          toast.error("取消关联失败，请稍后重试");
        }
      } else {
        addSelectedSource(sourceId);
        try {
          await linkSourcesToSession(sessionId, [sourceId]);
        } catch {
          removeSelectedSource(sourceId);
          toast.error("关联素材失败，请稍后重试");
        }
      }
      refreshSessions().catch(() => {});
    },
    [
      addSelectedSource,
      ensureSession,
      effectiveSelectedSourceIds,
      isBootstrapping,
      refreshSessions,
      removeSelectedSource,
    ]
  );

  const handleToggleAll = useCallback(async () => {
    if (isBootstrapping) return;
    const sessionId = await ensureSession();
    if (allSelected) {
      const toUnlink = readySources
        .map((source) => source.id)
        .filter((id) => effectiveSelectedSourceIds.includes(id));
      deselectAllSources();
      await Promise.all(
        toUnlink.map((id) =>
          unlinkSourceFromSession(sessionId, id).catch(() => {
            addSelectedSource(id);
          })
        )
      );
      refreshSessions().catch(() => {});
      return;
    }

    const toLink = readySources
      .map((source) => source.id)
      .filter((id) => !effectiveSelectedSourceIds.includes(id));
    if (toLink.length === 0) return;
    selectAllSources();
    try {
      await linkSourcesToSession(sessionId, toLink);
    } catch {
      toLink.forEach((id) => removeSelectedSource(id));
      toast.error("批量关联失败，请稍后重试");
    }
    refreshSessions().catch(() => {});
  }, [
    addSelectedSource,
    allSelected,
    deselectAllSources,
    ensureSession,
    effectiveSelectedSourceIds,
    isBootstrapping,
    readySources,
    refreshSessions,
    removeSelectedSource,
    selectAllSources,
  ]);

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
        void handleUploadFiles(files);
        return;
      }

      const text = e.dataTransfer.getData("text/plain");
      if (text && isUrl(text)) {
        void handleUrlSubmit(text);
      }
    },
    [handleUploadFiles, handleUrlSubmit]
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent) => {
      const files = Array.from(e.clipboardData.files);
      if (files.length > 0) {
        void handleUploadFiles(files);
        return;
      }

      const text = e.clipboardData.getData("text/plain");
      if (text && isUrl(text)) {
        e.preventDefault();
        void handleUrlSubmit(text);
      }
    },
    [handleUploadFiles, handleUrlSubmit]
  );

  return (
    <>
      <div
        className={cn(
          "relative flex w-[340px] shrink-0 flex-col border-r border-white/60 bg-card/60 backdrop-blur-md",
          isDragOver && "ring-2 ring-inset ring-cyan-500/50"
        )}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onPaste={handlePaste}
        tabIndex={0}
      >
        {isDragOver && (
          <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-primary/5">
            <p className="text-sm font-medium text-primary">松开以上传素材</p>
          </div>
        )}

        <div className="border-b border-slate-200 dark:border-slate-700 px-4 py-3">
          <div className="flex items-center gap-2">
            {readySources.length > 0 && (
              <input
                type="checkbox"
                checked={allSelected}
                disabled={isBootstrapping}
                onChange={() => {
                  void handleToggleAll();
                }}
                className="h-4 w-4 cursor-pointer rounded border-gray-300 accent-primary"
                aria-label="全选来源"
              />
            )}
            <h2 className="text-sm font-semibold">素材库</h2>
          </div>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            {loadingWorkspaceSources
              ? "加载素材中..."
              : readySources.length > 0
                ? `当前会话已勾选 ${selectedCount}/${readySources.length} 个可用素材`
                : `共 ${workspaceSources.length} 条素材`}
          </p>
        </div>

        <div className="border-b border-slate-200 dark:border-slate-700 px-3 py-2">
          <input
            value={workspaceQuery}
            onChange={(e) => setWorkspaceQuery(e.target.value)}
            placeholder="检索素材..."
            className="mb-2 h-8 w-full rounded-md border border-slate-300 dark:border-slate-600 bg-white/80 dark:bg-slate-800/80 px-2 text-xs focus:outline-none focus:ring-2 focus:ring-cyan-500/60"
          />
          <div className="flex gap-1">
            <button
              onClick={() => setSourceFilterMode("all")}
              className={cn(
                "rounded-md px-2 py-1 text-xs transition-colors",
                sourceFilterMode === "all" ? "bg-slate-900 text-white shadow-sm dark:bg-slate-100 dark:text-slate-900" : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
              )}
            >
              全部
            </button>
            <button
              onClick={() => setSourceFilterMode("selected")}
              className={cn(
                "rounded-md px-2 py-1 text-xs transition-colors",
                sourceFilterMode === "selected" ? "bg-slate-900 text-white shadow-sm dark:bg-slate-100 dark:text-slate-900" : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
              )}
            >
              已勾选
            </button>
            <button
              onClick={() => setSourceFilterMode("unselected")}
              className={cn(
                "rounded-md px-2 py-1 text-xs transition-colors",
                sourceFilterMode === "unselected" ? "bg-slate-900 text-white shadow-sm dark:bg-slate-100 dark:text-slate-900" : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
              )}
            >
              未勾选
            </button>
            <button
              onClick={() => router.push("/assets")}
              className="ml-auto inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-foreground"
            >
              <FolderOpen className="h-3.5 w-3.5" />
              管理素材库
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-2">
          {visibleSources.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center text-sm text-slate-500 dark:text-slate-400">
              <p>当前没有可显示素材</p>
              <p className="mt-1 text-xs">上传文档、粘贴网址，即可开始生成</p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {visibleSources.map((source) => (
                <SourceItem
                  key={source.id}
                  source={source}
                  isSelected={effectiveSelectedSourceIds.includes(source.id)}
                  onToggleSelect={(id) => {
                    void handleToggleSessionSource(id);
                  }}
                  onPreview={setPreviewSource}
                  showRemove={false}
                  hoverPreviewVariant="create"
                  extraMeta={
                    typeof source.linked_session_count === "number"
                      ? `已关联 ${source.linked_session_count} 个会话`
                      : undefined
                  }
                />
              ))}
            </div>
          )}
        </div>

        <div className="border-t border-slate-200 dark:border-slate-700 px-3 py-3">
          <AddSourceArea
            onFilesSelected={(files) => {
              void handleUploadFiles(files);
            }}
            onUrlSubmit={(url) => {
              void handleUrlSubmit(url);
            }}
          />
        </div>

      </div>

      {previewSource && (
        <SourcePreviewModal
          source={previewSource}
          onClose={() => setPreviewSource(null)}
        />
      )}
    </>
  );
}

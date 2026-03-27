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
import { resolveGenerationRequestTitle } from "@/lib/loading-title";
import SourceItem from "./SourceItem";
import SourcePreviewModal from "./SourcePreviewModal";
import AddSourceArea from "./AddSourceArea";
import { cn } from "@/lib/utils";
import {
  getSessionEditorPath,
  pickCreateLandingSessionId,
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
      const modelMeta =
        item.model_meta && typeof item.model_meta === "object"
          ? (item.model_meta as Record<string, unknown>)
          : {};
      return {
        id: typeof item.id === "string" ? item.id : `msg-${Math.random().toString(36).slice(2)}`,
        role,
        content,
        timestamp: Date.parse(createdAt) || Date.now(),
        phase: typeof modelMeta.phase === "string" ? modelMeta.phase : undefined,
        messageKind:
          typeof modelMeta.message_kind === "string"
            ? modelMeta.message_kind
            : undefined,
        outlineVersion:
          typeof modelMeta.outline_version === "number"
            ? modelMeta.outline_version
            : null,
        jobId: typeof modelMeta.job_id === "string" ? modelMeta.job_id : null,
      } as ChatMessage;
    })
    .filter((item) => item.content.trim().length > 0);
}

type SourceFilterMode = "all" | "selected" | "unselected";

type HydratedGenerationJob = {
  slides?: Slide[];
  request?: { title?: string; topic?: string };
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
    planningState,
    setOutlineStale,
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
              title: resolveGenerationRequestTitle(job.request),
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
        planningState: detail.planning_state ?? null,
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
            ).catch((err) => {
              console.error(
                `Failed to create session snapshot for session ${migratedSessionId}:`,
                err
              );
            });
          }
          for (const msg of legacyChats) {
            const role = msg.role === "assistant" ? "assistant" : "user";
            const content = typeof msg.content === "string" ? msg.content : "";
            if (!content.trim()) continue;
            await appendSessionChat(migratedSessionId, { role, content }).catch((err) => {
              console.error(
                `Failed to append session chat for session ${migratedSessionId}:`,
                err
              );
            });
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

      const landingSessionId = pickCreateLandingSessionId(items, currentSessionId);
      if (landingSessionId) {
        await loadSession(landingSessionId, { fromExplicitSessionParam: false });
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
          refreshSessions().catch((err) => { console.error("Failed to refresh sessions:", err); });
          if (planningState?.outline?.items && planningState.outline.items.length > 0) {
            setOutlineStale(true);
          }
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
      planningState?.outline?.items,
      refreshSessions,
      refreshWorkspaceSources,
      removeWorkspaceSource,
      setOutlineStale,
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
        refreshSessions().catch((err) => { console.error("Failed to refresh sessions:", err); });
        if (planningState?.outline?.items && planningState.outline.items.length > 0) {
          setOutlineStale(true);
        }
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
      planningState?.outline?.items,
      refreshSessions,
      refreshWorkspaceSources,
      removeWorkspaceSource,
      setOutlineStale,
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
          if (planningState?.outline?.items && planningState.outline.items.length > 0) {
            setOutlineStale(true);
          }
        } catch {
          addSelectedSource(sourceId);
          toast.error("取消关联失败，请稍后重试");
        }
      } else {
        addSelectedSource(sourceId);
        try {
          await linkSourcesToSession(sessionId, [sourceId]);
          if (planningState?.outline?.items && planningState.outline.items.length > 0) {
            setOutlineStale(true);
          }
        } catch {
          removeSelectedSource(sourceId);
          toast.error("关联素材失败，请稍后重试");
        }
      }
      refreshSessions().catch((err) => { console.error("Failed to refresh sessions:", err); });
    },
    [
      addSelectedSource,
      ensureSession,
      effectiveSelectedSourceIds,
      isBootstrapping,
      planningState?.outline?.items,
      refreshSessions,
      removeSelectedSource,
      setOutlineStale,
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
          unlinkSourceFromSession(sessionId, id).catch((err) => {
            console.error(
              `Failed to unlink source ${id} from session ${sessionId}:`,
              err
            );
            addSelectedSource(id);
          })
        )
      );
      if (planningState?.outline?.items && planningState.outline.items.length > 0) {
        setOutlineStale(true);
      }
      refreshSessions().catch((err) => { console.error("Failed to refresh sessions:", err); });
      return;
    }

    const toLink = readySources
      .map((source) => source.id)
      .filter((id) => !effectiveSelectedSourceIds.includes(id));
    if (toLink.length === 0) return;
    selectAllSources();
    try {
      await linkSourcesToSession(sessionId, toLink);
      if (planningState?.outline?.items && planningState.outline.items.length > 0) {
        setOutlineStale(true);
      }
    } catch {
      toLink.forEach((id) => removeSelectedSource(id));
      toast.error("批量关联失败，请稍后重试");
    }
    refreshSessions().catch((err) => { console.error("Failed to refresh sessions:", err); });
  }, [
    addSelectedSource,
    allSelected,
    deselectAllSources,
    ensureSession,
    effectiveSelectedSourceIds,
    isBootstrapping,
    planningState?.outline?.items,
    readySources,
    refreshSessions,
    removeSelectedSource,
    setOutlineStale,
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
          "relative flex w-[332px] shrink-0 flex-col border-r border-white/55 bg-white/34 backdrop-blur-xl",
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

        <div className="border-b border-white/55 px-4 pb-4 pt-5">
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
            <h2 className="text-sm font-semibold text-slate-900">素材库</h2>
          </div>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            {loadingWorkspaceSources
              ? "加载素材中..."
              : readySources.length > 0
                ? `当前会话已选中 ${selectedCount}/${readySources.length} 份可用素材`
                : `共 ${workspaceSources.length} 份素材`}
          </p>
        </div>

        <div className="border-b border-white/55 px-4 py-4">
          <input
            value={workspaceQuery}
            onChange={(e) => setWorkspaceQuery(e.target.value)}
            placeholder="检索素材..."
            className="h-10 w-full rounded-2xl border border-white/90 bg-white/88 px-3 text-sm text-slate-700 shadow-[0_12px_24px_-24px_rgba(15,23,42,0.5)] outline-none transition placeholder:text-slate-400 focus:border-cyan-200 focus:ring-2 focus:ring-cyan-500/15"
          />
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              onClick={() => setSourceFilterMode("all")}
              className={cn(
                "rounded-full border px-3 py-1.5 text-xs font-medium transition",
                sourceFilterMode === "all"
                  ? "border-slate-200 bg-white text-slate-900 shadow-[0_10px_22px_-20px_rgba(15,23,42,0.45)]"
                  : "border-transparent bg-white/55 text-slate-500 hover:border-white/90 hover:bg-white/80 hover:text-slate-700"
              )}
            >
              全部
            </button>
            <button
              onClick={() => setSourceFilterMode("selected")}
              className={cn(
                "rounded-full border px-3 py-1.5 text-xs font-medium transition",
                sourceFilterMode === "selected"
                  ? "border-slate-200 bg-white text-slate-900 shadow-[0_10px_22px_-20px_rgba(15,23,42,0.45)]"
                  : "border-transparent bg-white/55 text-slate-500 hover:border-white/90 hover:bg-white/80 hover:text-slate-700"
              )}
            >
              已选择
            </button>
            <button
              onClick={() => setSourceFilterMode("unselected")}
              className={cn(
                "rounded-full border px-3 py-1.5 text-xs font-medium transition",
                sourceFilterMode === "unselected"
                  ? "border-slate-200 bg-white text-slate-900 shadow-[0_10px_22px_-20px_rgba(15,23,42,0.45)]"
                  : "border-transparent bg-white/55 text-slate-500 hover:border-white/90 hover:bg-white/80 hover:text-slate-700"
              )}
            >
              未选择
            </button>
            <button
              onClick={() => router.push("/assets")}
              className="ml-auto inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs text-slate-500 transition hover:bg-white/70 hover:text-slate-700"
            >
              <FolderOpen className="h-3.5 w-3.5" />
              管理素材库
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4">
          {visibleSources.length === 0 ? (
            <div className="flex flex-col items-center justify-center px-5 py-12 text-center text-sm text-slate-500">
              <p className="font-medium text-slate-700">这里还没有可用素材</p>
              <p className="mt-2 text-xs leading-6">
                上传文件或贴上链接后，就可以让知演围绕这些内容帮你整理演示结构。
              </p>
            </div>
          ) : (
            <div className="space-y-2.5">
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

        <div className="border-t border-white/55 px-4 py-4">
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

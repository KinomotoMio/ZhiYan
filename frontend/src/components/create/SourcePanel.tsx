"use client";

import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { FolderOpen, Grid2x2, List, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { useAppStore, type ChatMessage } from "@/lib/store";
import {
  addWorkspaceTextSource,
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
import CircleCheckbox from "@/components/ui/CircleCheckbox";
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

type HydratedGenerationJob = {
  slides?: Slide[];
  request?: { title?: string; topic?: string };
  issues?: Array<Record<string, unknown>>;
  failed_slide_indices?: number[];
  hard_issue_slide_ids?: string[];
  advisory_issue_count?: number;
  fix_preview_slides?: Slide[];
  fix_preview_source_ids?: string[];
  fix_preview_slidev?: { markdown: string; meta: Record<string, unknown>; preview_url: string; selected_style_id?: string | null } | null;
};

function toTimestamp(source: SourceMeta): number {
  const raw = source.created_at;
  if (!raw) return 0;
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : 0;
}

function matchesSourceQuery(source: SourceMeta, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  return (
    source.name.toLowerCase().includes(normalized) ||
    (source.previewSnippet || "").toLowerCase().includes(normalized)
  );
}

function compareSourceOrder(a: SourceMeta, b: SourceMeta): number {
  return toTimestamp(b) - toTimestamp(a);
}

export default function SourcePanel() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preferredSessionId = searchParams.get("session");
  const suppressEditorRedirect = searchParams.get("from") === "editor";
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
  } = useAppStore();

  const [workspaceQuery, setWorkspaceQuery] = useState("");
  const [loadingWorkspaceSources, setLoadingWorkspaceSources] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [previewSource, setPreviewSource] = useState<SourceMeta | null>(null);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [sourceViewMode, setSourceViewMode] = useState<"single" | "double">("double");
  const bootstrappedRef = useRef(false);
  const effectiveSelectedSourceIds = useMemo(
    () => (isBootstrapping ? [] : selectedSourceIds),
    [isBootstrapping, selectedSourceIds]
  );

  const visibleSources = useMemo(() => {
    return [...workspaceSources]
      .filter((source) => matchesSourceQuery(source, workspaceQuery))
      .sort(compareSourceOrder);
  }, [workspaceQuery, workspaceSources]);

  const visibleReadySourceIds = useMemo(
    () =>
      visibleSources
        .filter((source) => source.status === "ready")
        .map((source) => source.id),
    [visibleSources]
  );

  const allSelected =
    visibleReadySourceIds.length > 0 &&
    visibleReadySourceIds.every((id) => effectiveSelectedSourceIds.includes(id));

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
        suppressEditorRedirect?: boolean;
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
      const latestOutputMode = detail.latest_presentation?.output_mode ?? "structured";
      const shouldHydrateJob =
        Boolean(detail.latest_generation_job?.job_id) &&
        (resolvedJobStatus === "running" ||
          resolvedJobStatus === "artifact_ready" ||
          resolvedJobStatus === "waiting_fix_review" ||
          resolvedJobStatus === "render_failed" ||
          resolvedJobStatus === "completed");
      if (shouldHydrateJob && detail.latest_generation_job?.job_id) {
        try {
          const job = await getJob(sessionId, detail.latest_generation_job.job_id);
          hydratedJob = job as unknown as HydratedGenerationJob;
          if (
            !hydratedPresentation &&
            latestOutputMode !== "slidev" &&
            Array.isArray(job.slides) &&
            job.slides.length > 0
          ) {
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
        presentationArtifactStatus: detail.latest_presentation?.artifact_status ?? null,
        presentationRenderStatus: detail.latest_presentation?.render_status ?? null,
        presentationRenderError: detail.latest_presentation?.render_error ?? null,
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
          fixPreviewSlidev:
            hydratedJob && hydratedJob.fix_preview_slidev
              ? hydratedJob.fix_preview_slidev
              : null,
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
          fixPreviewSlidev: null,
          selectedFixPreviewSlideIds: [],
        });
        setIsGenerating(false);
      }

      if (
        shouldAutoRedirectToEditor(
          Boolean(detail.latest_presentation),
          Boolean(options?.fromExplicitSessionParam)
        ) &&
        !options?.suppressEditorRedirect
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
        await loadSession(preferredSessionId, {
          fromExplicitSessionParam: true,
          suppressEditorRedirect,
        });
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
    suppressEditorRedirect,
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

  const handleTextSubmit = useCallback(
    async (name: string, content: string) => {
      const sessionId = await ensureSession();
      const tempId = `temp-text-${Date.now()}`;
      addWorkspaceSource({
        id: tempId,
        name,
        type: "text",
        fileCategory: "text",
        size: new TextEncoder().encode(content).length,
        status: "parsing",
        previewSnippet: content.trim().slice(0, 200) || undefined,
      });

      try {
        const meta = await addWorkspaceTextSource(name, content);
        await linkSourcesToSession(sessionId, [meta.id]);
        removeWorkspaceSource(tempId);
        addSelectedSource(meta.id);
        await refreshWorkspaceSources();
        refreshSessions().catch((err) => {
          console.error("Failed to refresh sessions:", err);
        });
        if (planningState?.outline?.items && planningState.outline.items.length > 0) {
          setOutlineStale(true);
        }
        if (meta.deduped) {
          toast.info("检测到重复素材，已复用已有内容");
        } else {
          toast.success("文本素材已保存并选中");
        }
      } catch (err) {
        updateWorkspaceSource(tempId, {
          status: "error",
          error: err instanceof Error ? err.message : "文本保存失败",
        });
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
      const toUnlink = visibleReadySourceIds.filter((id) =>
        effectiveSelectedSourceIds.includes(id)
      );
      toUnlink.forEach((id) => removeSelectedSource(id));
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

    const toLink = visibleReadySourceIds.filter(
      (id) => !effectiveSelectedSourceIds.includes(id)
    );
    if (toLink.length === 0) return;
    toLink.forEach((id) => addSelectedSource(id));
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
    ensureSession,
    effectiveSelectedSourceIds,
    isBootstrapping,
    planningState?.outline?.items,
    refreshSessions,
    removeSelectedSource,
    setOutlineStale,
    visibleReadySourceIds,
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

  const filteredSelectedCount = visibleReadySourceIds.filter((id) =>
    effectiveSelectedSourceIds.includes(id)
  ).length;
  const hasSearchQuery = workspaceQuery.trim().length > 0;
  const emptyStateTitle = hasSearchQuery ? "没有找到匹配素材" : "素材库还是空的";
  const emptyStateMessage = loadingWorkspaceSources
    ? "素材加载中..."
    : hasSearchQuery
      ? "可以换个关键词，或直接上传新的素材。"
      : "拖拽文件、粘贴网页链接，或新建文本素材后再开始选择。";

  return (
    <>
      <div
        className={cn(
          "relative flex w-[440px] shrink-0 flex-col border-r border-white/80 bg-white/46 backdrop-blur-xl",
          isDragOver && "ring-2 ring-inset ring-cyan-500/50"
        )}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onPaste={handlePaste}
        tabIndex={0}
      >
        {isDragOver && (
          <div className="absolute inset-0 z-10 flex items-center justify-center rounded-[28px] bg-[rgba(var(--zy-brand-blue),0.08)] backdrop-blur-sm">
            <p className="text-sm font-medium text-[rgb(var(--zy-brand-blue))]">松开以上传素材</p>
          </div>
        )}

        <div className="border-b border-white/75 bg-white/66 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="min-w-0 flex-1">
              <h2 className="text-base font-semibold leading-none text-slate-900">素材库</h2>
            </div>
            <button
              type="button"
              onClick={() => {
                void refreshWorkspaceSources();
              }}
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-slate-300 bg-white/80 text-slate-600 transition-all duration-200 hover:shadow-sm"
              aria-label="刷新素材"
            >
              <RefreshCw className={cn("h-4 w-4", loadingWorkspaceSources && "animate-spin")} />
            </button>
            <button
              onClick={() => router.push("/assets")}
              className="inline-flex h-10 items-center gap-1.5 rounded-xl border border-slate-300 bg-white/80 px-3 text-sm text-slate-600 transition-all duration-200 hover:shadow-sm"
            >
              <FolderOpen className="h-4 w-4" />
              管理
            </button>
          </div>
        </div>

        <div className="flex items-center gap-3 border-b border-white/75 px-5 py-3">
          <CircleCheckbox
            checked={allSelected}
            disabled={visibleReadySourceIds.length === 0 || isBootstrapping}
            onChange={() => {
              void handleToggleAll();
            }}
            aria-label="全选当前筛选素材"
          />
          <span className="text-sm text-slate-500">
            当前筛选已选 {filteredSelectedCount}/{visibleReadySourceIds.length || 0}
          </span>
          <div className="ml-auto flex items-center gap-2">
            <input
              value={workspaceQuery}
              onChange={(e) => setWorkspaceQuery(e.target.value)}
              placeholder="搜索素材名称..."
              className="h-9 w-[176px] rounded-lg border border-slate-300 bg-white/80 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500/60"
            />
            <div className="inline-flex items-center rounded-xl border border-slate-300 bg-white/80 p-1">
              <button
                type="button"
                onClick={() => setSourceViewMode("single")}
                className={cn(
                  "inline-flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 transition-colors",
                  sourceViewMode === "single"
                    ? "bg-slate-900 text-white"
                    : "hover:bg-slate-100 hover:text-slate-700"
                )}
                aria-label="单列显示素材"
              >
                <List className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setSourceViewMode("double")}
                className={cn(
                  "inline-flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 transition-colors",
                  sourceViewMode === "double"
                    ? "bg-slate-900 text-white"
                    : "hover:bg-slate-100 hover:text-slate-700"
                )}
                aria-label="双列显示素材"
              >
                <Grid2x2 className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loadingWorkspaceSources && visibleSources.length === 0 ? (
            <p className="py-10 text-center text-sm text-slate-500">{emptyStateMessage}</p>
          ) : visibleSources.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-white/60 px-6 py-12 text-center">
              <p className="text-sm font-medium text-slate-700">{emptyStateTitle}</p>
              <p className="mt-2 text-sm text-slate-500">{emptyStateMessage}</p>
            </div>
          ) : (
            <div
              className={cn(
                "grid gap-3",
                sourceViewMode === "double" ? "grid-cols-2" : "grid-cols-1"
              )}
            >
              {visibleSources.map((source) => {
                const isSelected = effectiveSelectedSourceIds.includes(source.id);
                const statusDetail =
                  source.status === "error" ? source.error || "导入失败，请稍后重试" : undefined;

                return (
                  <SourceItem
                    key={source.id}
                    source={source}
                    isSelected={isSelected}
                    onToggleSelect={() => {
                      void handleToggleSessionSource(source.id);
                    }}
                    onPreview={setPreviewSource}
                    clickBehavior="toggle-select"
                    showSelectionCheckbox={false}
                    showRemove={false}
                    hoverPreviewVariant="assets"
                    hoverPreviewPlacement="right"
                    statusDetail={statusDetail}
                    extraMeta={
                      typeof source.linked_session_count === "number"
                        ? `已关联 ${source.linked_session_count} 个会话`
                        : undefined
                    }
                  />
                );
              })}
            </div>
          )}
        </div>

        <div className="border-t border-white/75 px-5 py-3">
          <AddSourceArea
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

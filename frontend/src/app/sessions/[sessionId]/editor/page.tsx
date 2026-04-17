"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import EditorWorkspace from "@/components/editor/EditorWorkspace";
import {
  getLatestSessionPresentationCentiDeck,
  getLatestSessionPresentationCentiDeckArtifact,
  getLatestSessionPresentationSlidev,
  getLatestSessionPresentationSlidevSidecar,
  getSessionDetail,
  updateSession,
} from "@/lib/api";
import { getCreateSessionPath } from "@/lib/routes";
import { resolveSlidevPreviewState } from "@/lib/slidev-preview-state";
import { useAppStore, type ChatMessage } from "@/lib/store";

type LoadState = "loading" | "ready" | "empty" | "error";

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
        id:
          typeof item.id === "string"
            ? item.id
            : `msg-${Math.random().toString(36).slice(2)}`,
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

function parseSlideQueryToIndex(rawSlide: string | null, totalSlides: number): number {
  if (totalSlides <= 0 || !rawSlide) return 0;
  if (!/^\d+$/.test(rawSlide)) return 0;

  const requested = Number.parseInt(rawSlide, 10);
  if (!Number.isFinite(requested)) return 0;

  const oneBased = Math.max(1, requested);
  const clamped = Math.min(oneBased, totalSlides);
  return clamped - 1;
}

export default function SessionEditorPage() {
  const params = useParams<{ sessionId: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = useMemo(() => {
    const value = params?.sessionId;
    return typeof value === "string" ? value : "";
  }, [params]);
  const requestedSlide = searchParams.get("slide");
  const createSessionPath = useMemo(
    () => getCreateSessionPath(sessionId || null, { fromEditor: true }),
    [sessionId]
  );

  const [state, setState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState("会话不存在或无权限访问。");
  const [sessionTitle, setSessionTitle] = useState("\u672a\u547d\u540d\u4f1a\u8bdd");
  const setCurrentSessionId = useAppStore((store) => store.setCurrentSessionId);
  const syncedSessionTitle = useAppStore(
    (store) => store.sessions.find((session) => session.id === sessionId)?.title ?? ""
  );
  const displaySessionTitle = syncedSessionTitle || sessionTitle;
  const upsertSession = useAppStore((store) => store.upsertSession);
  const setSessionData = useAppStore((store) => store.setSessionData);
  const setPresentationSlidevState = useAppStore((store) => store.setPresentationSlidevState);
  const setCurrentSlideIndex = useAppStore((store) => store.setCurrentSlideIndex);
  const updateJobState = useAppStore((store) => store.updateJobState);
  const setIsGenerating = useAppStore((store) => store.setIsGenerating);

  useEffect(() => {
    if (!sessionId) return;

    let cancelled = false;
    const run = async () => {
      try {
        const detail = await getSessionDetail(sessionId);
        if (cancelled) return;
        setSessionTitle(detail.session.title || "未命名会话");
        upsertSession(detail.session);
        const chatMessages = toStoreChatMessages(
          detail.chat_messages as unknown as Array<Record<string, unknown>>
        );
        const latestOutputMode =
          detail.latest_presentation?.output_mode ??
          detail.planning_state?.output_mode ??
          "slidev";
        let presentationSlidevMarkdown: string | null = null;
        let presentationSlidevMeta: Record<string, unknown> | null = null;
        let presentationSlidevBuildUrl: string | null = null;
        let presentationSlidevNotesState: Record<string, string> = {};
        let presentationSlidevAudioState: Record<string, unknown> = {};
        const presentationArtifactStatus =
          detail.latest_presentation?.artifact_status ?? null;
        let presentationRenderStatus =
          detail.latest_presentation?.render_status ?? null;
        let presentationRenderError =
          detail.latest_presentation?.render_error ?? null;
        const latestJob = detail.latest_generation_job;
        const currentStore = useAppStore.getState();
        const resolvedJobStatus =
          latestJob?.status === "pending" &&
          currentStore.jobId === latestJob.job_id &&
          currentStore.jobStatus === "running"
            ? "running"
            : latestJob?.status ?? null;

        if (latestOutputMode === "slidev") {
          try {
            const [slidev, slidevSidecar] = await Promise.all([
              getLatestSessionPresentationSlidev(sessionId),
              getLatestSessionPresentationSlidevSidecar(sessionId),
            ]);
            const resolvedPreviewState = resolveSlidevPreviewState({
              buildUrl: slidev?.build_url ?? null,
              renderStatus: slidev?.render_status ?? presentationRenderStatus,
              renderError: slidev?.render_error ?? presentationRenderError,
            });
            presentationSlidevMarkdown = slidev?.markdown ?? null;
            presentationSlidevMeta = slidev?.meta ?? null;
            presentationSlidevBuildUrl = resolvedPreviewState.buildUrl;
            presentationSlidevNotesState = slidevSidecar?.speaker_notes ?? {};
            presentationSlidevAudioState = slidevSidecar?.speaker_audio ?? {};
            presentationRenderStatus = resolvedPreviewState.renderStatus;
            presentationRenderError = resolvedPreviewState.renderError;
          } catch {
            presentationSlidevMarkdown = null;
            presentationSlidevMeta = null;
            presentationSlidevBuildUrl = null;
            presentationSlidevNotesState = {};
            presentationSlidevAudioState = {};
          }
        }

        let centiDeckArtifact: Record<string, unknown> | null = null;
        let centiDeckRender: Record<string, unknown> | null = null;
        if (latestOutputMode === "html") {
          try {
            const [summary, artifact] = await Promise.all([
              getLatestSessionPresentationCentiDeck(sessionId),
              getLatestSessionPresentationCentiDeckArtifact(sessionId),
            ]);
            centiDeckArtifact = (artifact ?? null) as Record<string, unknown> | null;
            centiDeckRender = (summary?.render ?? null) as Record<string, unknown> | null;
          } catch {
            centiDeckArtifact = null;
            centiDeckRender = null;
          }
        }

        const initialSlideIndex = parseSlideQueryToIndex(
          requestedSlide,
          latestOutputMode === "slidev"
            ? Array.isArray(presentationSlidevMeta?.slides)
              ? presentationSlidevMeta.slides.length
              : 0
            : Array.isArray(centiDeckArtifact?.slides)
              ? centiDeckArtifact.slides.length
              : 0
        );

        setCurrentSessionId(sessionId);
        setSessionData({
          sources: detail.sources,
          chatMessages,
          presentationOutputMode: latestOutputMode,
          presentationSlidevMarkdown,
          presentationSlidevMeta,
          presentationSlidevDeckArtifact: detail.latest_presentation?.artifacts?.slidev_deck ?? null,
          presentationSlidevBuildArtifact: detail.latest_presentation?.artifacts?.slidev_build ?? null,
          presentationSlidevBuildUrl,
          presentationSlidevNotesState,
          presentationSlidevAudioState: presentationSlidevAudioState as Record<
            string,
            undefined
          >,
          presentationArtifactStatus,
          presentationRenderStatus,
          presentationRenderError,
          planningState: detail.planning_state ?? null,
        });
        setPresentationSlidevState({
          outputMode: latestOutputMode,
          markdown: presentationSlidevMarkdown,
          meta: presentationSlidevMeta,
          deckArtifact: detail.latest_presentation?.artifacts?.slidev_deck ?? null,
          buildArtifact: detail.latest_presentation?.artifacts?.slidev_build ?? null,
          buildUrl: presentationSlidevBuildUrl,
          notesState: presentationSlidevNotesState,
          audioState: presentationSlidevAudioState as Record<string, undefined>,
        });
        useAppStore.getState().setPresentationCentiDeckArtifact(centiDeckArtifact);
        useAppStore.getState().setPresentationCentiDeckRender(centiDeckRender);
        if (latestJob?.job_id) {
          updateJobState({
            jobId: latestJob.job_id,
            jobStatus: resolvedJobStatus,
            currentStage: null,
            lastJobEventSeq: 0,
            issues: [],
            failedSlideIndices: [],
            hardIssueSlideIds: [],
            advisoryIssueCount: 0,
            fixPreviewSourceIds: [],
            fixPreviewSlidev: null,
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
            fixPreviewSourceIds: [],
            fixPreviewSlidev: null,
          });
          setIsGenerating(false);
        }
        setCurrentSlideIndex(initialSlideIndex);

        if (presentationSlidevMarkdown || centiDeckArtifact || latestJob?.job_id) {
          setState("ready");
        } else {
          setState("empty");
        }
      } catch (err) {
        if (cancelled) return;
        setState("error");
        setErrorMessage(
          err instanceof Error && err.message
            ? `会话加载失败：${err.message}`
            : "会话不存在或无权限访问。"
        );
      }
    };
    void run();

    return () => {
      cancelled = true;
    };
  }, [
    requestedSlide,
    sessionId,
    setCurrentSessionId,
    setCurrentSlideIndex,
    setIsGenerating,
    setPresentationSlidevState,
    setSessionData,
    updateJobState,
    upsertSession,
  ]);

  if (!sessionId) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-muted-foreground">会话参数缺失。</p>
          <button
            onClick={() => router.push(createSessionPath)}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md"
          >
            返回创建页
          </button>
        </div>
      </div>
    );
  }

  if (state === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在加载会话内容...
        </div>
      </div>
    );
  }

  if (state === "error") {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-muted-foreground">{errorMessage}</p>
          <button
            onClick={() => router.push(createSessionPath)}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md"
          >
            返回创建页
          </button>
        </div>
      </div>
    );
  }

  if (state === "empty") {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-muted-foreground">该会话暂无生成结果</p>
          <button
            onClick={() => router.push(createSessionPath)}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md"
          >
            返回创建页
          </button>
        </div>
      </div>
    );
  }

  const handleRenameSessionTitle = async (nextTitle: string) => {
    if (!sessionId) return;
    const updated = await updateSession(sessionId, { title: nextTitle });
    upsertSession(updated);
    setSessionTitle(updated.title || "未命名会话");
  };

  return (
    <EditorWorkspace
      returnHref={createSessionPath}
      returnLabel="返回创建页"
      sessionTitle={displaySessionTitle}
      onRenameSessionTitle={handleRenameSessionTitle}
    />
  );
}

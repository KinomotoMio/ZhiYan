"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import EditorWorkspace from "@/components/editor/EditorWorkspace";
import {
  getJob,
  getLatestSessionPresentationHtml,
  getLatestSessionPresentationHtmlMeta,
  getSessionDetail,
  updateSession,
} from "@/lib/api";
import { extractHtmlDeckMetaFromPresentation } from "@/lib/html-deck";
import { DEFAULT_LOADING_TITLE, resolveGenerationRequestTitle } from "@/lib/loading-title";
import { getCreateSessionPath } from "@/lib/routes";
import {
  buildShellSlides,
  mergeGeneratedSlide,
} from "@/components/generation/presentation-shell";
import { useAppStore, type ChatMessage } from "@/lib/store";
import type { Presentation, Slide } from "@/types/slide";

type LoadState = "loading" | "ready" | "empty" | "error";

type HydratedGenerationJob = {
  slides?: Slide[];
  request?: { num_pages?: number; title?: string; topic?: string };
  presentation?: Presentation | null;
  issues?: Array<Record<string, unknown>>;
  failed_slide_indices?: number[];
  hard_issue_slide_ids?: string[];
  advisory_issue_count?: number;
  fix_preview_slides?: Slide[];
  fix_preview_source_ids?: string[];
};

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
  const setPresentationHtmlState = useAppStore((store) => store.setPresentationHtmlState);
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
        const currentStore = useAppStore.getState();
        const localPresentation =
          currentStore.currentSessionId === sessionId
            ? currentStore.presentation
            : null;
        let presentation =
          detail.latest_presentation?.presentation ?? localPresentation ?? null;
        const latestOutputMode = detail.latest_presentation?.output_mode ?? "structured";
        let htmlDeckMeta =
          latestOutputMode === "html"
            ? extractHtmlDeckMetaFromPresentation(presentation)
            : null;
        let presentationHtml =
          currentStore.currentSessionId === sessionId
            ? currentStore.presentationHtml
            : null;
        const latestJob = detail.latest_generation_job;
        const resolvedJobStatus =
          latestJob?.status === "pending" &&
          currentStore.jobId === latestJob.job_id &&
          currentStore.jobStatus === "running"
            ? "running"
            : latestJob?.status ?? null;

        let hydratedJob: HydratedGenerationJob | null = null;

        const shouldHydrateJob =
          Boolean(latestJob?.job_id) &&
          (resolvedJobStatus === "running" ||
            resolvedJobStatus === "waiting_outline_review" ||
            resolvedJobStatus === "waiting_fix_review" ||
            resolvedJobStatus === "completed");

        if (shouldHydrateJob && latestJob?.job_id) {
          try {
            const job = await getJob(sessionId, latestJob.job_id);
            hydratedJob = job as unknown as HydratedGenerationJob;
            if (!presentation) {
              const rawNumPages =
                typeof job.request?.num_pages === "number"
                  ? job.request.num_pages
                  : 5;
              const pageCount = Math.max(1, Math.trunc(rawNumPages));
              const jobTitle = resolveGenerationRequestTitle(job.request);

              let mergedSlides = buildShellSlides(pageCount, jobTitle);
              if (Array.isArray(job.slides) && job.slides.length > 0) {
                for (let idx = 0; idx < Math.min(job.slides.length, mergedSlides.length); idx += 1) {
                  const slide = job.slides[idx] as Slide | undefined;
                  if (slide) {
                    mergedSlides = mergeGeneratedSlide(mergedSlides, idx, slide);
                  }
                }
              }

              const presentationId =
                typeof job.presentation?.presentationId === "string" &&
                job.presentation.presentationId.trim()
                  ? job.presentation.presentationId
                  : "pres-skeleton";

              presentation = {
                presentationId,
                title: jobTitle,
                slides: mergedSlides,
              } as Presentation;
            }
          } catch {
            if (
              !presentation &&
              (resolvedJobStatus === "running" || resolvedJobStatus === "waiting_outline_review")
            ) {
              presentation = {
                presentationId: "pres-skeleton",
                title: DEFAULT_LOADING_TITLE,
                slides: buildShellSlides(5, DEFAULT_LOADING_TITLE),
              };
            }
          }
        }

        if (latestOutputMode === "html") {
          try {
            const [latestHtml, latestHtmlMeta] = await Promise.all([
              getLatestSessionPresentationHtml(sessionId),
              getLatestSessionPresentationHtmlMeta(sessionId),
            ]);
            presentationHtml = latestHtml;
            htmlDeckMeta = latestHtmlMeta ?? htmlDeckMeta;
          } catch {
            presentationHtml = null;
          }
        }

        const initialSlideIndex = parseSlideQueryToIndex(
          requestedSlide,
          latestOutputMode === "html"
            ? htmlDeckMeta?.slides.length ?? 0
            : presentation?.slides.length ?? 0
        );

        setCurrentSessionId(sessionId);
        setSessionData({
          sources: detail.sources,
          chatMessages,
          presentation,
          presentationOutputMode: latestOutputMode,
          presentationHtml,
          presentationHtmlArtifact: detail.latest_presentation?.artifacts?.html_deck ?? null,
          htmlDeckMeta,
          planningState: detail.planning_state ?? null,
        });
        setPresentationHtmlState(
          latestOutputMode,
          presentationHtml,
          detail.latest_presentation?.artifacts?.html_deck ?? null,
          htmlDeckMeta
        );
        if (latestJob?.job_id) {
          updateJobState({
            jobId: latestJob.job_id,
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
        setCurrentSlideIndex(initialSlideIndex);

        if (presentation || latestJob?.job_id) {
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
    setPresentationHtmlState,
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

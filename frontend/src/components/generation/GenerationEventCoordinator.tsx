"use client";

import { useEffect } from "react";
import { toast } from "sonner";
import {
  acceptOutline,
  runJob,
  subscribeJobEvents,
  type GenerationErrorCode,
  type GenerationEvent,
} from "@/lib/api";
import { collectIssueSlideIds } from "@/lib/verification-issues";
import { useAppStore } from "@/lib/store";
import type { Presentation, Slide } from "@/types/slide";

function stageRank(stage: string | null): number {
  if (!stage) return 0;
  switch (stage) {
    case "parse":
      return 1;
    case "outline":
      return 2;
    case "layout":
      return 3;
    case "slides":
      return 4;
    case "assets":
      return 5;
    case "verify":
      return 6;
    case "fix":
      return 7;
    case "complete":
      return 8;
    default:
      return 0;
  }
}

function asNumber(value: unknown, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function asErrorCode(value: unknown): GenerationErrorCode | null {
  if (
    value === "STAGE_TIMEOUT" ||
    value === "PROVIDER_TIMEOUT" ||
    value === "PROVIDER_NETWORK" ||
    value === "PROVIDER_RATE_LIMIT" ||
    value === "CANCELLED" ||
    value === "UNKNOWN"
  ) {
    return value;
  }
  return null;
}

function toErrorMessage(evt: GenerationEvent): string {
  const payload = evt.payload as Record<string, unknown>;
  const message =
    typeof payload.error_message === "string"
      ? payload.error_message
      : typeof payload.error === "string"
        ? payload.error
        : evt.message || "任务失败";
  const code = asErrorCode(payload.error_code);
  if (code === "STAGE_TIMEOUT") {
    const timeout =
      typeof payload.timeout_seconds === "number" ? payload.timeout_seconds : 90;
    return `${message}（${Math.round(timeout)}秒）`;
  }
  return message;
}

export default function GenerationEventCoordinator() {
  const {
    jobId,
    jobStatus,
    updateJobState,
    setFixPreviewSelection,
    clearFixReviewState,
    setIssueDecision,
    resetIssueReviewState,
    patchSlideTitlesFromOutline,
    setPresentationTitle,
    updateSlideAtIndex,
    setPresentation,
    setIsGenerating,
    finishGeneration,
  } = useAppStore();

  useEffect(() => {
    if (!jobId || jobStatus !== "running") {
      return;
    }
    setIsGenerating(true);
    const afterSeq = useAppStore.getState().lastJobEventSeq;

    const controller = new AbortController();
    void subscribeJobEvents(
      jobId,
      {
        onEvent: (evt) => {
          const payload = evt.payload as Record<string, unknown>;
          const engineId =
            typeof payload.engine_id === "string" && payload.engine_id.trim()
              ? payload.engine_id.trim()
              : null;

          updateJobState({ lastJobEventSeq: evt.seq });
          if (evt.type === "job_started") {
            const primaryEngine =
              typeof payload.engine === "string" && payload.engine.trim()
                ? payload.engine.trim()
                : engineId;
            updateJobState({ primaryEngineId: primaryEngine ?? null });
          }

          if (evt.stage) {
            const primary = useAppStore.getState().primaryEngineId;
            const prevStage = useAppStore.getState().currentStage;
            const shouldUpdateStage =
              !(primary && engineId && engineId !== primary) &&
              stageRank(evt.stage) >= stageRank(prevStage);

            if (shouldUpdateStage) {
              updateJobState({
                jobId,
                jobStatus: "running",
                currentStage: evt.stage,
              });
            }
          }

          if (evt.type === "outline_ready") {
            const rawItems = Array.isArray(payload.items) ? payload.items : [];
            const items = rawItems
              .map((item) => {
                const obj = item as Record<string, unknown>;
                return {
                  slide_number: Number(obj.slide_number ?? 0),
                  title: String(obj.title ?? "未命名页面"),
                };
              })
              .filter((item) => item.slide_number > 0);
            const title =
              typeof payload.topic === "string" && payload.topic.trim()
                ? payload.topic
                : useAppStore.getState().presentation?.title || "新演示文稿";
            setPresentationTitle(title);
            if (items.length > 0) {
              patchSlideTitlesFromOutline(items);
            }

            if (payload.requires_accept === true) {
              void (async () => {
                try {
                  await acceptOutline(jobId);
                  await runJob(jobId);
                  updateJobState({ jobStatus: "running" });
                } catch (err) {
                  toast.error(err instanceof Error ? err.message : "确认大纲失败");
                }
              })();
            }
            return;
          }

          if (evt.type === "slide_ready") {
            const index = Number(payload.slide_index ?? -1);
            const slide = payload.slide as Slide | undefined;
            const currentSlides =
              useAppStore.getState().presentation?.slides.length ?? 0;
            if (index >= 0 && index < currentSlides && slide) {
              const tier =
                typeof payload.layer === "string" && payload.layer.trim()
                  ? payload.layer.trim()
                  : "content";
              const tierRank = asNumber(payload.layer_rank, 20);
              const nextSlide: Slide = {
                ...slide,
                contentData: {
                  ...(slide.contentData ?? {}),
                  _generation: {
                    seq: evt.seq,
                    engine_id: engineId ?? undefined,
                    tier,
                    tier_rank: tierRank,
                  },
                },
              };
              updateSlideAtIndex(index, nextSlide);
            } else if (index >= 0) {
              console.warn(
                "[generation] slide_ready index out of range",
                { index, currentSlides, jobId }
              );
            }
            return;
          }

          if (evt.type === "job_waiting_fix_review") {
            const payload = evt.payload as Record<string, unknown>;
            const normalizedIssues = Array.isArray(payload.issues)
              ? (payload.issues as Array<Record<string, unknown>>)
              : [];
            updateJobState({
              jobId,
              jobStatus: "waiting_fix_review",
              currentStage: "verify",
              issues: normalizedIssues,
              failedSlideIndices: Array.isArray(payload.failed_slide_indices)
                ? (payload.failed_slide_indices as number[])
                : [],
              hardIssueSlideIds: Array.isArray(payload.hard_issue_slide_ids)
                ? (payload.hard_issue_slide_ids as string[])
                : [],
              advisoryIssueCount:
                typeof payload.advisory_issue_count === "number"
                  ? payload.advisory_issue_count
                  : 0,
              fixPreviewSlides: [],
              fixPreviewSourceIds: [],
              selectedFixPreviewSlideIds: [],
            });
            for (const slideId of collectIssueSlideIds(normalizedIssues)) {
              setIssueDecision(slideId, "pending");
            }
            finishGeneration();
            toast.warning("检测到需要人工决策的问题，请确认是否应用修复建议");
            return;
          }

          if (evt.type === "fix_preview_ready") {
            const payload = evt.payload as Record<string, unknown>;
            const previewSlides = Array.isArray(payload.fix_preview_slides)
              ? (payload.fix_preview_slides as Slide[])
              : [];
            const sourceIds = Array.isArray(payload.fix_preview_source_ids)
              ? (payload.fix_preview_source_ids as string[])
              : [];
            updateJobState({
              fixPreviewSlides: previewSlides,
              fixPreviewSourceIds: sourceIds,
              selectedFixPreviewSlideIds: sourceIds,
            });
            setFixPreviewSelection(sourceIds);
            toast.success(`已生成 ${sourceIds.length} 页修复建议`);
            return;
          }

          if (evt.type === "job_completed") {
            const payload = evt.payload as Record<string, unknown>;
            const presentation = payload.presentation as Presentation | undefined;
            if (presentation) {
              setPresentation(presentation);
            }
            const normalizedIssues = Array.isArray(payload.issues)
              ? (payload.issues as Array<Record<string, unknown>>)
              : [];
            updateJobState({
              jobId,
              jobStatus: "completed",
              currentStage: "complete",
              issues: normalizedIssues,
              failedSlideIndices: Array.isArray(payload.failed_slide_indices)
                ? (payload.failed_slide_indices as number[])
                : [],
              hardIssueSlideIds: Array.isArray(payload.hard_issue_slide_ids)
                ? (payload.hard_issue_slide_ids as string[])
                : [],
              advisoryIssueCount:
                typeof payload.advisory_issue_count === "number"
                  ? payload.advisory_issue_count
                  : 0,
              fixPreviewSlides: [],
              fixPreviewSourceIds: [],
              selectedFixPreviewSlideIds: [],
            });
            clearFixReviewState();
            for (const slideId of collectIssueSlideIds(normalizedIssues)) {
              const currentDecision = useAppStore.getState().issueDecisionBySlideId[slideId];
              if (!currentDecision) {
                setIssueDecision(slideId, "pending");
              }
            }
            finishGeneration();
            return;
          }

          if (evt.type === "job_failed") {
            const payload = evt.payload as Record<string, unknown>;
            const presentation = payload.presentation as Presentation | undefined;
            if (presentation) {
              setPresentation(presentation);
            }
            updateJobState({
              jobId,
              jobStatus: "failed",
              currentStage: null,
              hardIssueSlideIds: [],
              advisoryIssueCount: 0,
              fixPreviewSlides: [],
              fixPreviewSourceIds: [],
              selectedFixPreviewSlideIds: [],
            });
            clearFixReviewState();
            resetIssueReviewState();
            finishGeneration();
            toast.error(toErrorMessage(evt));
            return;
          }

          if (evt.type === "job_cancelled") {
            updateJobState({
              jobId,
              jobStatus: "cancelled",
              currentStage: null,
              hardIssueSlideIds: [],
              advisoryIssueCount: 0,
              fixPreviewSlides: [],
              fixPreviewSourceIds: [],
              selectedFixPreviewSlideIds: [],
            });
            clearFixReviewState();
            resetIssueReviewState();
            finishGeneration();
            toast.info("任务已取消");
          }
        },
        onError: (err) => {
          updateJobState({
            jobId,
            jobStatus: "failed",
            currentStage: null,
            hardIssueSlideIds: [],
            advisoryIssueCount: 0,
            fixPreviewSlides: [],
            fixPreviewSourceIds: [],
            selectedFixPreviewSlideIds: [],
          });
          clearFixReviewState();
          resetIssueReviewState();
          finishGeneration();
          toast.error(err.message || "事件流连接失败");
        },
      },
      {
        signal: controller.signal,
        afterSeq,
      }
    );

    return () => {
      controller.abort();
    };
  }, [
    finishGeneration,
    jobId,
    jobStatus,
    patchSlideTitlesFromOutline,
    clearFixReviewState,
    resetIssueReviewState,
    setIsGenerating,
    setIssueDecision,
    setFixPreviewSelection,
    setPresentation,
    setPresentationTitle,
    updateJobState,
    updateSlideAtIndex,
  ]);

  return null;
}

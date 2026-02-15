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
import { useAppStore } from "@/lib/store";
import type { Presentation, Slide } from "@/types/slide";

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
          updateJobState({ lastJobEventSeq: evt.seq });
          if (evt.stage) {
            updateJobState({
              jobId,
              jobStatus: "running",
              currentStage: evt.stage,
            });
          }

          if (evt.type === "outline_ready") {
            const payload = evt.payload as Record<string, unknown>;
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
            const payload = evt.payload as Record<string, unknown>;
            const index = Number(payload.slide_index ?? -1);
            const slide = payload.slide as Slide | undefined;
            const currentSlides =
              useAppStore.getState().presentation?.slides.length ?? 0;
            if (index >= 0 && index < currentSlides && slide) {
              updateSlideAtIndex(index, slide);
            } else if (index >= 0) {
              console.warn(
                "[generation] slide_ready index out of range",
                { index, currentSlides, jobId }
              );
            }
            return;
          }

          if (evt.type === "job_completed") {
            const payload = evt.payload as Record<string, unknown>;
            const presentation = payload.presentation as Presentation | undefined;
            if (presentation) {
              setPresentation(presentation);
            }
            updateJobState({
              jobId,
              jobStatus: "completed",
              currentStage: "complete",
              issues: Array.isArray(payload.issues)
                ? (payload.issues as Array<Record<string, unknown>>)
                : [],
              failedSlideIndices: Array.isArray(payload.failed_slide_indices)
                ? (payload.failed_slide_indices as number[])
                : [],
            });
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
            });
            finishGeneration();
            toast.error(toErrorMessage(evt));
            return;
          }

          if (evt.type === "job_cancelled") {
            updateJobState({
              jobId,
              jobStatus: "cancelled",
              currentStage: null,
            });
            finishGeneration();
            toast.info("任务已取消");
          }
        },
        onError: (err) => {
          updateJobState({
            jobId,
            jobStatus: "failed",
            currentStage: null,
          });
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
    setIsGenerating,
    setPresentation,
    setPresentationTitle,
    updateJobState,
    updateSlideAtIndex,
  ]);

  return null;
}

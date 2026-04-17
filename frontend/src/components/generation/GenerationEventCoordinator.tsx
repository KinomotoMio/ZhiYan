"use client";

import { useEffect } from "react";
import { toast } from "sonner";
import {
  getLatestSessionPresentationHtmlManifest,
  getLatestSessionPresentationHtmlRender,
  getLatestSessionPresentationSlidev,
  subscribeJobEvents,
  type GenerationErrorCode,
  type GenerationEvent,
  type HtmlDeckArtifactMeta,
  type SlidevBuildArtifactMeta,
  type SlidevDeckArtifactMeta,
} from "@/lib/api";
import { collectIssueSlideIds } from "@/lib/verification-issues";
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
    currentSessionId,
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
    setPresentationHtmlState,
    setPresentationSlidevState,
    setPresentationRenderState,
    setIsGenerating,
    finishGeneration,
  } = useAppStore();

  useEffect(() => {
    if (!currentSessionId || !jobId || (jobStatus !== "running" && jobStatus !== "artifact_ready")) {
      return;
    }
    setIsGenerating(jobStatus === "running");
    const afterSeq = useAppStore.getState().lastJobEventSeq;

    const controller = new AbortController();
    void subscribeJobEvents(
      currentSessionId,
      jobId,
      {
        onEvent: (evt) => {
          updateJobState({ lastJobEventSeq: evt.seq });
          if (evt.stage) {
            const currentJobStatus = useAppStore.getState().jobStatus;
            updateJobState({
              jobId,
              jobStatus:
                currentJobStatus === "artifact_ready" &&
                (evt.stage === "artifact_render" || evt.stage === "artifact_publish")
                  ? "artifact_ready"
                  : "running",
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
              updateJobState({
                jobId,
                jobStatus: "waiting_outline_review",
                currentStage: "outline",
              });
              setIsGenerating(false);
              toast.info("大纲已生成，请确认后继续生成");
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

          if (evt.type === "artifact_ready") {
            const payload = evt.payload as Record<string, unknown>;
            const presentation = payload.presentation as Presentation | undefined;
            if (presentation) {
              setPresentation(presentation);
            }
            setPresentationRenderState({
              artifactStatus:
                typeof payload.artifact_status === "string" ? payload.artifact_status : "ready",
              renderStatus:
                typeof payload.render_status === "string" ? payload.render_status : "pending",
              renderError:
                typeof payload.render_error === "string" ? payload.render_error : null,
            });
            if (payload.output_mode === "html" && currentSessionId) {
              void Promise.all([
                getLatestSessionPresentationHtmlManifest(currentSessionId),
                getLatestSessionPresentationHtmlRender(currentSessionId),
              ])
                .then(([manifest, render]) => {
                  const artifacts =
                    payload.artifacts && typeof payload.artifacts === "object"
                      ? (payload.artifacts as { html_deck?: HtmlDeckArtifactMeta })
                      : undefined;
                  setPresentationHtmlState(
                    "html",
                    render?.documentHtml ?? null,
                    manifest ?? null,
                    render ?? null,
                    artifacts?.html_deck ?? null
                  );
                })
                .catch(() => {
                  setPresentationHtmlState("html", null, null, null, null);
                });
            } else if (payload.output_mode === "slidev" && currentSessionId) {
              void getLatestSessionPresentationSlidev(currentSessionId)
                .then((slidev) => {
                  const artifacts =
                    payload.artifacts && typeof payload.artifacts === "object"
                      ? (payload.artifacts as {
                          slidev_deck?: SlidevDeckArtifactMeta;
                          slidev_build?: SlidevBuildArtifactMeta;
                        })
                      : undefined;
                  setPresentationSlidevState({
                    outputMode: "slidev",
                    markdown: slidev?.markdown ?? null,
                    meta: slidev?.meta ?? null,
                    deckArtifact: artifacts?.slidev_deck ?? null,
                    buildArtifact: artifacts?.slidev_build ?? null,
                    buildUrl: slidev?.build_url ?? null,
                  });
                })
                .catch(() => {
                  setPresentationSlidevState({
                    outputMode: "slidev",
                    markdown: null,
                    meta: null,
                    buildUrl: null,
                  });
                });
            }
            updateJobState({
              jobId,
              jobStatus: "artifact_ready",
              currentStage: evt.stage ?? "artifact_publish",
            });
            finishGeneration();
            return;
          }

          if (evt.type === "job_completed") {
            const payload = evt.payload as Record<string, unknown>;
            const presentation = payload.presentation as Presentation | undefined;
            if (presentation) {
              setPresentation(presentation);
            }
            setPresentationRenderState({
              artifactStatus:
                typeof payload.artifact_status === "string" ? payload.artifact_status : "ready",
              renderStatus:
                typeof payload.render_status === "string" ? payload.render_status : "ready",
              renderError:
                typeof payload.render_error === "string" ? payload.render_error : null,
            });
            if (payload.output_mode === "html" && currentSessionId) {
              void Promise.all([
                getLatestSessionPresentationHtmlManifest(currentSessionId),
                getLatestSessionPresentationHtmlRender(currentSessionId),
              ])
                .then(([manifest, render]) => {
                  const artifacts =
                    payload.artifacts && typeof payload.artifacts === "object"
                      ? (payload.artifacts as {
                          html_deck?: HtmlDeckArtifactMeta;
                        })
                      : undefined;
                  setPresentationHtmlState(
                    "html",
                    render?.documentHtml ?? null,
                    manifest ?? null,
                    render ?? null,
                    artifacts?.html_deck ?? null
                  );
                })
                .catch(() => {
                  setPresentationHtmlState("html", null, null, null, null);
                });
            } else if (payload.output_mode === "slidev" && currentSessionId) {
              void getLatestSessionPresentationSlidev(currentSessionId)
                .then((slidev) => {
                  const artifacts =
                    payload.artifacts && typeof payload.artifacts === "object"
                      ? (payload.artifacts as {
                          slidev_deck?: SlidevDeckArtifactMeta;
                          slidev_build?: SlidevBuildArtifactMeta;
                        })
                      : undefined;
                  setPresentationSlidevState({
                    outputMode: "slidev",
                    markdown: slidev?.markdown ?? null,
                    meta: slidev?.meta ?? null,
                    deckArtifact: artifacts?.slidev_deck ?? null,
                    buildArtifact: artifacts?.slidev_build ?? null,
                    buildUrl: slidev?.build_url ?? null,
                  });
                })
                .catch(() => {
                  setPresentationSlidevState({
                    outputMode: "slidev",
                    markdown: null,
                    meta: null,
                    buildUrl: null,
                  });
                });
            } else {
              setPresentationHtmlState("structured", null, null, null, null);
              setPresentationSlidevState({
                outputMode: "structured",
                markdown: null,
                meta: null,
                buildUrl: null,
              });
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
            const nextJobStatus =
              payload.job_status === "render_failed" ? "render_failed" : "failed";
            setPresentationRenderState({
              artifactStatus:
                typeof payload.artifact_status === "string" ? payload.artifact_status : null,
              renderStatus:
                typeof payload.render_status === "string" ? payload.render_status : null,
              renderError:
                typeof payload.render_error === "string"
                  ? payload.render_error
                  : typeof payload.error_message === "string"
                    ? payload.error_message
                    : null,
            });
            if (payload.output_mode === "slidev" && currentSessionId) {
              void getLatestSessionPresentationSlidev(currentSessionId)
                .then((slidev) => {
                  const artifacts =
                    payload.artifacts && typeof payload.artifacts === "object"
                      ? (payload.artifacts as {
                          slidev_deck?: SlidevDeckArtifactMeta;
                          slidev_build?: SlidevBuildArtifactMeta;
                        })
                      : undefined;
                  setPresentationSlidevState({
                    outputMode: "slidev",
                    markdown: slidev?.markdown ?? null,
                    meta: slidev?.meta ?? null,
                    deckArtifact: artifacts?.slidev_deck ?? null,
                    buildArtifact: artifacts?.slidev_build ?? null,
                    buildUrl: slidev?.build_url ?? null,
                  });
                })
                .catch(() => {
                  setPresentationSlidevState({
                    outputMode: "slidev",
                    markdown: null,
                    meta: null,
                    buildUrl: null,
                  });
                });
            }
            updateJobState({
              jobId,
              jobStatus: nextJobStatus,
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
            if (nextJobStatus === "render_failed") {
              toast.warning(toErrorMessage(evt));
            } else {
              toast.error(toErrorMessage(evt));
            }
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
    currentSessionId,
    jobId,
    jobStatus,
    patchSlideTitlesFromOutline,
    clearFixReviewState,
    resetIssueReviewState,
    setIsGenerating,
    setIssueDecision,
    setFixPreviewSelection,
    setPresentation,
    setPresentationHtmlState,
    setPresentationRenderState,
    setPresentationSlidevState,
    setPresentationTitle,
    updateJobState,
    updateSlideAtIndex,
  ]);

  return null;
}

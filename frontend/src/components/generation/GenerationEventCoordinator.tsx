"use client";

import { useEffect } from "react";
import { toast } from "sonner";
import {
  getLatestSessionPresentationCentiDeck,
  getLatestSessionPresentationCentiDeckArtifact,
  getLatestSessionPresentationSlidev,
  getLatestSessionPresentationSlidevSidecar,
  subscribeJobEvents,
  type GenerationErrorCode,
  type GenerationEvent,
  type SlidevBuildArtifactMeta,
  type SlidevDeckArtifactMeta,
  type SlidevFixPreviewState,
} from "@/lib/api";
import { collectIssueSlideIds } from "@/lib/verification-issues";
import { useAppStore } from "@/lib/store";

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
    clearFixReviewState,
    setIssueDecision,
    resetIssueReviewState,
    setPresentationSlidevState,
    setPresentationRenderState,
    setPresentationCentiDeckArtifact,
    setPresentationCentiDeckRender,
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
              fixPreviewSourceIds: [],
              fixPreviewSlidev: null,
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
            const sourceIds = Array.isArray(payload.fix_preview_source_ids)
              ? (payload.fix_preview_source_ids as string[])
              : [];
            const slidevPreview =
              payload.fix_preview_slidev && typeof payload.fix_preview_slidev === "object"
                ? (payload.fix_preview_slidev as SlidevFixPreviewState)
                : null;
            updateJobState({
              fixPreviewSourceIds: sourceIds,
              fixPreviewSlidev: slidevPreview,
            });
            toast.success(`已生成 ${sourceIds.length} 页修复建议`);
            return;
          }

          if (evt.type === "artifact_ready") {
            const payload = evt.payload as Record<string, unknown>;
            setPresentationRenderState({
              artifactStatus:
                typeof payload.artifact_status === "string" ? payload.artifact_status : "ready",
              renderStatus:
                typeof payload.render_status === "string" ? payload.render_status : "pending",
              renderError:
                typeof payload.render_error === "string" ? payload.render_error : null,
            });
            if (payload.output_mode === "slidev" && currentSessionId) {
              void Promise.all([
                getLatestSessionPresentationSlidev(currentSessionId),
                getLatestSessionPresentationSlidevSidecar(currentSessionId),
              ])
                .then(([slidev, slidevSidecar]) => {
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
                    notesState: slidevSidecar?.speaker_notes ?? {},
                    audioState: slidevSidecar?.speaker_audio ?? {},
                  });
                })
                .catch(() => {
                  setPresentationSlidevState({
                    outputMode: "slidev",
                    markdown: null,
                    meta: null,
                    buildUrl: null,
                    notesState: {},
                    audioState: {},
                  });
                });
            } else if (payload.output_mode === "html" && currentSessionId) {
              void Promise.all([
                getLatestSessionPresentationCentiDeck(currentSessionId),
                getLatestSessionPresentationCentiDeckArtifact(currentSessionId),
              ])
                .then(([summary, artifact]) => {
                  setPresentationCentiDeckRender(summary?.render ?? null);
                  setPresentationCentiDeckArtifact(artifact ?? null);
                })
                .catch(() => {
                  setPresentationCentiDeckRender(null);
                  setPresentationCentiDeckArtifact(null);
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
            setPresentationRenderState({
              artifactStatus:
                typeof payload.artifact_status === "string" ? payload.artifact_status : "ready",
              renderStatus:
                typeof payload.render_status === "string" ? payload.render_status : "ready",
              renderError:
                typeof payload.render_error === "string" ? payload.render_error : null,
            });
            if (payload.output_mode === "slidev" && currentSessionId) {
              const sid = currentSessionId;
              const expectBuildReady = payload.render_status === "ready";
              void Promise.all([
                getLatestSessionPresentationSlidev(sid),
                getLatestSessionPresentationSlidevSidecar(sid),
              ])
                .then(([slidev, slidevSidecar]) => {
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
                    notesState: slidevSidecar?.speaker_notes ?? {},
                    audioState: slidevSidecar?.speaker_audio ?? {},
                  });
                  if (expectBuildReady && !slidev?.build_url) {
                    setTimeout(() => {
                      void getLatestSessionPresentationSlidev(sid)
                        .then((retry) => {
                          if (retry?.build_url) {
                            setPresentationSlidevState({
                              outputMode: "slidev",
                              markdown: retry.markdown ?? slidev?.markdown ?? null,
                              meta: retry.meta ?? slidev?.meta ?? null,
                              deckArtifact: artifacts?.slidev_deck ?? null,
                              buildArtifact: artifacts?.slidev_build ?? null,
                              buildUrl: retry.build_url,
                              notesState: slidevSidecar?.speaker_notes ?? {},
                              audioState: slidevSidecar?.speaker_audio ?? {},
                            });
                          }
                        })
                        .catch(() => {});
                    }, 1000);
                  }
                })
                .catch(() => {
                  setPresentationSlidevState({
                    outputMode: "slidev",
                    markdown: null,
                    meta: null,
                    buildUrl: null,
                    notesState: {},
                    audioState: {},
                  });
                });
            } else if (payload.output_mode === "html" && currentSessionId) {
              void Promise.all([
                getLatestSessionPresentationCentiDeck(currentSessionId),
                getLatestSessionPresentationCentiDeckArtifact(currentSessionId),
              ])
                .then(([summary, artifact]) => {
                  setPresentationCentiDeckRender(summary?.render ?? null);
                  setPresentationCentiDeckArtifact(artifact ?? null);
                })
                .catch(() => {
                  setPresentationCentiDeckRender(null);
                  setPresentationCentiDeckArtifact(null);
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
              fixPreviewSourceIds: [],
              fixPreviewSlidev: null,
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
              void Promise.all([
                getLatestSessionPresentationSlidev(currentSessionId),
                getLatestSessionPresentationSlidevSidecar(currentSessionId),
              ])
                .then(([slidev, slidevSidecar]) => {
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
                    notesState: slidevSidecar?.speaker_notes ?? {},
                    audioState: slidevSidecar?.speaker_audio ?? {},
                  });
                })
                .catch(() => {
                  setPresentationSlidevState({
                    outputMode: "slidev",
                    markdown: null,
                    meta: null,
                    buildUrl: null,
                    notesState: {},
                    audioState: {},
                  });
                });
            } else if (payload.output_mode === "html" && currentSessionId) {
              void Promise.all([
                getLatestSessionPresentationCentiDeck(currentSessionId),
                getLatestSessionPresentationCentiDeckArtifact(currentSessionId),
              ])
                .then(([summary, artifact]) => {
                  setPresentationCentiDeckRender(summary?.render ?? null);
                  setPresentationCentiDeckArtifact(artifact ?? null);
                })
                .catch(() => {
                  setPresentationCentiDeckRender(null);
                  setPresentationCentiDeckArtifact(null);
                });
            }
            updateJobState({
              jobId,
              jobStatus: nextJobStatus,
              currentStage: null,
              hardIssueSlideIds: [],
              advisoryIssueCount: 0,
              fixPreviewSourceIds: [],
              fixPreviewSlidev: null,
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
              fixPreviewSourceIds: [],
              fixPreviewSlidev: null,
            });
            clearFixReviewState();
            resetIssueReviewState();
            finishGeneration();
            toast.info("任务已取消");
            return;
          }

          // Stub handler for centi-deck events. The next task will populate real state.
          const evtTypeAsString = String(evt.type);
          if (evtTypeAsString === "centi_deck_update") {
            const payload = evt.payload as Record<string, unknown> | undefined;
            setPresentationCentiDeckArtifact(payload?.artifact ?? null);
            setPresentationCentiDeckRender(payload?.render ?? null);
          }
        },
        onError: (err) => {
          updateJobState({
            jobId,
            jobStatus: "failed",
            currentStage: null,
            hardIssueSlideIds: [],
            advisoryIssueCount: 0,
            fixPreviewSourceIds: [],
            fixPreviewSlidev: null,
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
    clearFixReviewState,
    resetIssueReviewState,
    setIsGenerating,
    setIssueDecision,
    setPresentationRenderState,
    setPresentationSlidevState,
    setPresentationCentiDeckArtifact,
    setPresentationCentiDeckRender,
    updateJobState,
  ]);

  return null;
}

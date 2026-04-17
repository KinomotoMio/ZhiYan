"use client";

import { useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  FileOutput,
  LayoutPanelLeft,
  Loader2,
  Play,
  Share2,
} from "lucide-react";
import { Progress } from "@/components/ui/progress";
import CentiDeckPreview from "@/components/editor/CentiDeckPreview";
import { useAppStore } from "@/lib/store";
import {
  acceptOutline,
  type CentiDeckArtifactPayload,
  cancelJob,
  ensureSpeakerAudio,
  exportSessionPdf,
  exportSessionPptx,
  fetchSpeakerAudio,
  fixApply,
  fixPreview,
  fixSkip,
  generateSpeakerNotes,
  createOrGetSessionShareLink,
  getLatestSessionPresentation,
  getLatestSessionPresentationSlidev,
  getLatestSessionPresentationSlidevSidecar,
  saveLatestSessionSlidevPresentation,
  saveSlidevSpeakerNotes,
} from "@/lib/api";
import { collectIssueSlideIds, groupIssuesBySlide } from "@/lib/verification-issues";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { canResumeGenerationJob, getSessionPresenterPath } from "@/lib/routes";
import { resumeGenerationJob } from "@/components/editor/resume-job";
import SpeakerNotes from "@/components/slides/SpeakerNotes";
import SlidevPreview from "@/components/slides/SlidevPreview";
import FloatingChatPanel from "@/components/chat/FloatingChatPanel";
import UserMenu from "@/components/settings/UserMenu";
import IssueReviewDrawer from "@/components/editor/IssueReviewDrawer";
import ShareLinkDialog from "@/components/editor/ShareLinkDialog";
import SessionTitleInlineEditor from "@/components/session/SessionTitleInlineEditor";
import { resolveSlidevPreviewState } from "@/lib/slidev-preview-state";
import { mergeSpeakerNotesDrafts } from "@/components/editor/speakerNotesDrafts";

interface EditorWorkspaceProps {
  returnHref: string;
  returnLabel?: string;
  sessionTitle: string;
  onRenameSessionTitle: (nextTitle: string) => Promise<void>;
}

function getJobStatusBadge(
  jobStatus: string | null,
  isGenerating: boolean,
  outputMode: string | null,
  renderStatus: string | null,
  previewReady: boolean
) {
  if (isGenerating || jobStatus === "running") {
    return {
      label: "生成进行中",
      className: "border-cyan-200 bg-cyan-50 text-cyan-700",
    };
  }
  if (jobStatus === "artifact_ready") {
    return {
      label:
        outputMode === "slidev"
          ? previewReady
            ? "预览已就绪"
            : renderStatus === "failed"
              ? "原始产物已就绪"
              : "正在构建预览"
          : "原始产物已就绪",
      className: "border-sky-200 bg-sky-50 text-sky-700",
    };
  }
  if (jobStatus === "waiting_outline_review") {
    return {
      label: "等待确认大纲",
      className: "border-emerald-200 bg-emerald-50 text-emerald-700",
    };
  }
  if (jobStatus === "waiting_fix_review") {
    return {
      label: "等待处理校验问题",
      className: "border-amber-200 bg-amber-50 text-amber-700",
    };
  }
  if (jobStatus === "completed") {
    return {
      label: "已完成",
      className: "border-slate-200 bg-white/80 text-slate-600",
    };
  }
  if (jobStatus === "render_failed") {
    return {
      label: "预览构建失败",
      className: "border-amber-200 bg-amber-50 text-amber-700",
    };
  }
  if (jobStatus === "failed") {
    return {
      label: "生成失败",
      className: "border-rose-200 bg-rose-50 text-rose-700",
    };
  }
  if (jobStatus === "cancelled") {
    return {
      label: "已取消",
      className: "border-slate-200 bg-slate-100 text-slate-600",
    };
  }
  return null;
}

export default function EditorWorkspace({
  returnHref,
  returnLabel = "返回",
  sessionTitle,
  onRenameSessionTitle,
}: EditorWorkspaceProps) {
  const router = useRouter();
  const {
    presentationOutputMode,
    presentationSlidevBuildUrl,
    presentationSlidevMeta,
    presentationSlidevMarkdown,
    presentationSlidevDeckArtifact,
    presentationSlidevBuildArtifact,
    presentationSlidevNotesState,
    presentationSlidevAudioState,
    presentationRenderStatus,
    presentationRenderError,
    currentSessionId,
    currentSlideIndex,
    setCurrentSlideIndex,
    isGenerating,
    jobId,
    jobStatus,
    updateJobState,
    setIsGenerating,
    setIssuePanelOpen,
    openIssuePanelForSlide,
    setIssueDecision,
    markSlidesProcessed,
    issues,
    hardIssueSlideIds,
    fixPreviewSourceIds,
    fixPreviewSlidev,
    issuePanelOpen,
    issuePanelSlideId,
    issueDecisionBySlideId,
    setPresentationSlidevState,
    setPresentationRenderState,
    presentationCentiDeckArtifact,
  } = useAppStore();
  const [showReveal, setShowReveal] = useState(false);
  const [revealSlideIndex, setRevealSlideIndex] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [creatingShareLink, setCreatingShareLink] = useState(false);
  const [shareDialogOpen, setShareDialogOpen] = useState(false);
  const [shareUrl, setShareUrl] = useState("");
  const [previewingFix, setPreviewingFix] = useState(false);
  const [applyingFix, setApplyingFix] = useState(false);
  const [skippingFix, setSkippingFix] = useState(false);
  const [acceptingOutline, setAcceptingOutline] = useState(false);
  const [retryingSlidevRender, setRetryingSlidevRender] = useState(false);
  const [speakerNotesDrafts, setSpeakerNotesDrafts] = useState<Record<string, string>>({});
  const [savingSpeakerNotes, setSavingSpeakerNotes] = useState(false);
  const [generatingSpeakerNotesScope, setGeneratingSpeakerNotesScope] = useState<
    "current" | "all" | null
  >(null);
  const isSlidevMode = presentationOutputMode === "slidev";
  const slidevPreviewState = resolveSlidevPreviewState({
    buildUrl: presentationSlidevBuildUrl,
    renderStatus: presentationRenderStatus,
    renderError: presentationRenderError,
  });
  const prevSlidevNotesRef = useRef<Array<{ slideId: string; speakerNotes?: string }> | null>(null);

  const canResume = canResumeGenerationJob(jobId, jobStatus);
  const waitingOutlineReview = jobStatus === "waiting_outline_review";
  const slidevHasContent = Boolean(presentationSlidevMarkdown);
  const canShare = Boolean(
    currentSessionId &&
      !isGenerating &&
      !isSlidevMode &&
      false // Slidev sharing/centi-deck sharing not wired yet
  );
  const canExport = Boolean(
    currentSessionId &&
      !isGenerating &&
      !isSlidevMode &&
      slidevHasContent === false // centi-deck export not wired yet
  );

  const refreshSlidevPreviewState = async () => {
    if (!currentSessionId) return;
    if (!isSlidevMode) return;
    const [latestPresentation, latestSlidev, latestSlidevSidecar] = await Promise.all([
      getLatestSessionPresentation(currentSessionId),
      getLatestSessionPresentationSlidev(currentSessionId),
      getLatestSessionPresentationSlidevSidecar(currentSessionId),
    ]);
    const nextPreviewState = resolveSlidevPreviewState({
      buildUrl: latestSlidev?.build_url ?? null,
      renderStatus: latestSlidev?.render_status ?? latestPresentation?.render_status ?? null,
      renderError: latestSlidev?.render_error ?? latestPresentation?.render_error ?? null,
    });
    setPresentationSlidevState({
      outputMode: "slidev",
      markdown: latestSlidev?.markdown ?? presentationSlidevMarkdown,
      meta: latestSlidev?.meta ?? presentationSlidevMeta,
      deckArtifact: latestPresentation?.artifacts?.slidev_deck ?? presentationSlidevDeckArtifact,
      buildArtifact: latestPresentation?.artifacts?.slidev_build ?? null,
      buildUrl: nextPreviewState.buildUrl,
      notesState: latestSlidevSidecar?.speaker_notes ?? {},
      audioState: latestSlidevSidecar?.speaker_audio ?? {},
    });
    setPresentationRenderState({
      artifactStatus: latestPresentation?.artifact_status ?? latestSlidev?.artifact_status ?? null,
      renderStatus: nextPreviewState.renderStatus,
      renderError: nextPreviewState.renderError,
    });
    if (
      latestPresentation?.output_mode === "slidev" &&
      jobStatus === "artifact_ready"
    ) {
      if (nextPreviewState.previewReady) {
        updateJobState({
          jobStatus: "completed",
          currentStage: "complete",
        });
      } else if (nextPreviewState.buildFailed) {
        updateJobState({
          jobStatus: "render_failed",
          currentStage: null,
        });
      }
    }
  };
  const refreshSlidevPreviewStateEffect = useEffectEvent(async () => {
    await refreshSlidevPreviewState();
  });

  useEffect(() => {
    if (
      !currentSessionId ||
      !isSlidevMode ||
      jobStatus !== "artifact_ready" ||
      presentationRenderStatus === "failed" ||
      Boolean(presentationSlidevBuildUrl)
    ) {
      return;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        await refreshSlidevPreviewStateEffect();
      } catch {
        // Keep polling until render settles or the effect is torn down.
      }
      if (cancelled) return;
      const state = useAppStore.getState();
      const settled =
        state.jobStatus === "completed" ||
        state.jobStatus === "render_failed" ||
        Boolean(state.presentationSlidevBuildUrl);
      if (!settled) {
        window.setTimeout(() => {
          if (!cancelled) {
            void poll();
          }
        }, 1200);
      }
    };
    void poll();
    return () => {
      cancelled = true;
    };
  }, [
    currentSessionId,
    isSlidevMode,
    jobStatus,
    presentationRenderStatus,
    presentationSlidevBuildUrl,
  ]);

  const handleResume = async () => {
    if (!jobId || resuming) return;
    setResuming(true);
    try {
      if (!currentSessionId) throw new Error("缺少 session_id");
      const resumed = await resumeGenerationJob(currentSessionId, jobId);
      updateJobState({
        lastJobEventSeq: resumed.eventsSeq,
      });
      setIsGenerating(true);
      updateJobState({
        jobId: resumed.resumedJobId,
        jobStatus: resumed.resumedStatus,
        currentStage: resumed.resumedStage,
      });
      toast.success("已继续生成任务");
    } catch (err) {
      setIsGenerating(false);
      toast.error(err instanceof Error ? err.message : "继续任务失败");
    } finally {
      setResuming(false);
    }
  };

  const handleCancelGeneration = async () => {
    if (!jobId) return;
    try {
      if (!currentSessionId) throw new Error("缺少 session_id");
      await cancelJob(currentSessionId, jobId);
      updateJobState({
        jobStatus: "cancelled",
        currentStage: null,
      });
      setIsGenerating(false);
      toast.info("已取消生成");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "取消任务失败");
    }
  };

  const handleAcceptOutline = async () => {
    if (!jobId || acceptingOutline) return;
    setAcceptingOutline(true);
    try {
      if (!currentSessionId) throw new Error("缺少 session_id");
      const result = await acceptOutline(currentSessionId, jobId);
      updateJobState({
        jobId: result.job_id,
        jobStatus: result.status,
        currentStage: result.current_stage,
      });
      setIsGenerating(result.status === "running");
      toast.success("已确认大纲，继续生成");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "确认大纲失败");
    } finally {
      setAcceptingOutline(false);
    }
  };

  const handleShare = async () => {
    if (!currentSessionId || creatingShareLink) return;
    setCreatingShareLink(true);
    try {
      const result = await createOrGetSessionShareLink(currentSessionId);
      setShareUrl(result.share_url);
      setShareDialogOpen(true);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "生成分享链接失败");
    } finally {
      setCreatingShareLink(false);
    }
  };

  const handleRetrySlidevRender = async () => {
    if (
      retryingSlidevRender ||
      !currentSessionId ||
      !presentationSlidevMarkdown ||
      !isSlidevMode
    ) {
      return;
    }
    setRetryingSlidevRender(true);
    try {
      await saveLatestSessionSlidevPresentation(
        currentSessionId,
        presentationSlidevMarkdown,
        presentationSlidevDeckArtifact?.selected_style_id ?? null,
        presentationSlidevMeta ?? undefined,
        null,
        "editor"
      );
      await refreshSlidevPreviewState();
      const nextStoreState = useAppStore.getState();
      const nextPreviewState = resolveSlidevPreviewState({
        buildUrl: nextStoreState.presentationSlidevBuildUrl,
        renderStatus: nextStoreState.presentationRenderStatus,
        renderError: nextStoreState.presentationRenderError,
      });
      if (nextPreviewState.previewReady) {
        toast.success("已重新完成 Slidev 预览构建");
      } else {
        toast.warning("已重新尝试构建，但预览仍不可用");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "重新构建 Slidev 预览失败");
    } finally {
      setRetryingSlidevRender(false);
    }
  };

  const handleCopyShareLink = async () => {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      toast.success("已复制分享链接");
    } catch {
      toast.error("复制失败，请手动复制链接");
    }
  };

  const handlePreviewFix = async (targetSlideIds?: string[]) => {
    if (!jobId || previewingFix || applyingFix || skippingFix) return;
    setPreviewingFix(true);
    try {
      if (!currentSessionId) throw new Error("缺少 session_id");
      const job = await fixPreview(
        currentSessionId,
        jobId,
        targetSlideIds && targetSlideIds.length > 0
          ? targetSlideIds
          : hardIssueSlideIds.length > 0
            ? hardIssueSlideIds
            : undefined
      );
      const sourceIds = Array.isArray(job.fix_preview_source_ids)
        ? job.fix_preview_source_ids
        : [];
      updateJobState({
        jobStatus: job.status,
        currentStage: job.current_stage,
        issues: Array.isArray(job.issues)
          ? (job.issues as Array<Record<string, unknown>>)
          : [],
        failedSlideIndices: Array.isArray(job.failed_slide_indices)
          ? job.failed_slide_indices
          : [],
        hardIssueSlideIds: Array.isArray(job.hard_issue_slide_ids)
          ? job.hard_issue_slide_ids
          : [],
        advisoryIssueCount:
          typeof job.advisory_issue_count === "number"
            ? job.advisory_issue_count
            : 0,
        fixPreviewSourceIds: sourceIds,
        fixPreviewSlidev: job.fix_preview_slidev ?? null,
      });
      toast.success(`已生成 ${sourceIds.length} 页修复建议`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "生成修复建议失败");
    } finally {
      setPreviewingFix(false);
    }
  };

  const handleApplyFix = async () => {
    if (!jobId || applyingFix || previewingFix || skippingFix) return;
    if (fixPreviewSourceIds.length === 0) {
      toast.info("请先生成并确认当前 deck 修复预览");
      return;
    }
    setApplyingFix(true);
    try {
      if (!currentSessionId) throw new Error("缺少 session_id");
      const job = await fixApply(currentSessionId, jobId, fixPreviewSourceIds);
      if (isSlidevMode) {
        await refreshSlidevPreviewState();
      }
      const normalizedIssues = Array.isArray(job.issues)
        ? (job.issues as Array<Record<string, unknown>>)
        : [];
      const allIssueSlideIds = collectIssueSlideIds(normalizedIssues);
      const selectedSet = new Set(fixPreviewSourceIds);
      const skippedSlideIds = allIssueSlideIds.filter((slideId) => !selectedSet.has(slideId));
      markSlidesProcessed(fixPreviewSourceIds, "applied");
      markSlidesProcessed(skippedSlideIds, "skipped");
      updateJobState({
        jobStatus: job.status,
        currentStage: job.current_stage,
        issues: normalizedIssues,
        failedSlideIndices: Array.isArray(job.failed_slide_indices)
          ? job.failed_slide_indices
          : [],
        hardIssueSlideIds: Array.isArray(job.hard_issue_slide_ids)
          ? job.hard_issue_slide_ids
          : [],
        advisoryIssueCount:
          typeof job.advisory_issue_count === "number"
            ? job.advisory_issue_count
            : 0,
        fixPreviewSourceIds: [],
        fixPreviewSlidev: null,
      });
      setIsGenerating(false);
      toast.success(isSlidevMode ? "已应用当前 Slidev deck 修复预览" : "已应用修复");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "应用修复失败");
    } finally {
      setApplyingFix(false);
    }
  };

  const handleSkipFix = async () => {
    if (!jobId || skippingFix || previewingFix || applyingFix) return;
    setSkippingFix(true);
    try {
      if (!currentSessionId) throw new Error("缺少 session_id");
      const job = await fixSkip(currentSessionId, jobId);
      if (isSlidevMode) {
        await refreshSlidevPreviewState();
      }
      const normalizedIssues = Array.isArray(job.issues)
        ? (job.issues as Array<Record<string, unknown>>)
        : [];
      const allIssueSlideIds = collectIssueSlideIds(normalizedIssues);
      markSlidesProcessed(allIssueSlideIds, "skipped");
      updateJobState({
        jobStatus: job.status,
        currentStage: job.current_stage,
        issues: normalizedIssues,
        failedSlideIndices: Array.isArray(job.failed_slide_indices)
          ? job.failed_slide_indices
          : [],
        hardIssueSlideIds: Array.isArray(job.hard_issue_slide_ids)
          ? job.hard_issue_slide_ids
          : [],
        advisoryIssueCount:
          typeof job.advisory_issue_count === "number"
            ? job.advisory_issue_count
            : 0,
        fixPreviewSourceIds: [],
        fixPreviewSlidev: null,
      });
      setIsGenerating(false);
      toast.success("已完成当前版本");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "完成当前版本失败");
    } finally {
      setSkippingFix(false);
    }
  };

  const handleDiscardFixPreview = () => {
    updateJobState({
      fixPreviewSourceIds: [],
      fixPreviewSlidev: null,
    });
    toast.info("已丢弃当前修复候选");
  };

  const handleMarkSlideHandled = (slideId: string) => {
    setIssueDecision(slideId, "skipped");
    toast.success(`已将 ${slideId} 标记为已处理`);
  };

  const slidevMetaSlides = useMemo(
    () =>
      Array.isArray(presentationSlidevMeta?.slides)
        ? (presentationSlidevMeta.slides as Array<Record<string, unknown>>)
        : [],
    [presentationSlidevMeta]
  );
  const centiDeckSlides = useMemo(() => {
    const artifact = presentationCentiDeckArtifact as
      | { slides?: Array<Record<string, unknown>> }
      | null;
    return Array.isArray(artifact?.slides) ? artifact.slides : [];
  }, [presentationCentiDeckArtifact]);
  const centiDeckArtifact = useMemo(
    () => presentationCentiDeckArtifact as CentiDeckArtifactPayload | null,
    [presentationCentiDeckArtifact]
  );
  const currentSlideMeta = slidevMetaSlides[currentSlideIndex] ?? null;
  const currentSlideId = isSlidevMode
    ? currentSlideMeta
      ? String(currentSlideMeta.slide_id ?? "")
      : null
    : centiDeckSlides[currentSlideIndex]
      ? String(
          (centiDeckSlides[currentSlideIndex] as { slideId?: unknown }).slideId ?? ""
        )
      : null;
  const currentCanonicalSpeakerNotes = currentSlideId && isSlidevMode
    ? presentationSlidevNotesState[currentSlideId] ?? ""
    : !isSlidevMode && centiDeckSlides[currentSlideIndex]
      ? String(
          (centiDeckSlides[currentSlideIndex] as { notes?: unknown }).notes ?? ""
        )
      : "";
  const loadedCount = isSlidevMode
    ? slidevMetaSlides.length
    : centiDeckSlides.length;
  const totalCount = isSlidevMode
    ? slidevMetaSlides.length
    : centiDeckSlides.length;
  const genPct = totalCount > 0 ? Math.round((loadedCount / totalCount) * 100) : 0;
  const waitingFixReview = jobStatus === "waiting_fix_review";
  const statusBadge = getJobStatusBadge(
    jobStatus,
    isGenerating,
    presentationOutputMode,
    slidevPreviewState.renderStatus,
    slidevPreviewState.previewReady
  );
  const groupedIssues = groupIssuesBySlide(issues);
  const issueSlideIds = Array.from(groupedIssues.keys());
  const totalIssueCount = Array.from(groupedIssues.values()).reduce(
    (sum, item) => sum + item.total,
    0
  );
  const activeIssueSlideId =
    issuePanelSlideId && groupedIssues.has(issuePanelSlideId)
      ? issuePanelSlideId
      : currentSlideId && groupedIssues.has(currentSlideId)
        ? currentSlideId
        : issueSlideIds[0] ?? null;
  const speakerNotesDraft = currentSlideId
    ? speakerNotesDrafts[currentSlideId] ?? currentCanonicalSpeakerNotes
    : "";
  const hasUnsavedSpeakerNotes = currentSlideId
    ? speakerNotesDraft !== currentCanonicalSpeakerNotes
    : false;

  useEffect(() => {
    if (!isSlidevMode) {
      prevSlidevNotesRef.current = null;
      return;
    }

    const currentSlides = slidevMetaSlides
      .map((slide) => ({
        slideId: String(slide.slide_id ?? ""),
        speakerNotes: String(
          presentationSlidevNotesState[String(slide.slide_id ?? "")] ?? ""
        ),
      }))
      .filter((slide) => slide.slideId);

    setSpeakerNotesDrafts((current) => {
      const next = mergeSpeakerNotesDrafts({
        currentDrafts: current,
        previousSlides: prevSlidevNotesRef.current ?? undefined,
        currentSlides,
      });
      const currentKeys = Object.keys(current);
      const nextKeys = Object.keys(next);
      const unchanged =
        currentKeys.length === nextKeys.length &&
        nextKeys.every((key) => current[key] === next[key]);
      return unchanged ? current : next;
    });

    prevSlidevNotesRef.current = currentSlides;
  }, [isSlidevMode, presentationSlidevNotesState, slidevMetaSlides]);

  useEffect(() => {
    const missingSlideIds = issueSlideIds.filter(
      (slideId) => !issueDecisionBySlideId[slideId]
    );
    if (missingSlideIds.length === 0) return;
    for (const slideId of missingSlideIds) {
      setIssueDecision(slideId, "pending");
    }
  }, [issueDecisionBySlideId, issueSlideIds, setIssueDecision]);

  useEffect(() => {
    if (totalIssueCount === 0 && issuePanelOpen) {
      setIssuePanelOpen(false);
    }
  }, [issuePanelOpen, setIssuePanelOpen, totalIssueCount]);

  const buildRetryRef = useRef(false);
  useEffect(() => {
    if (
      isSlidevMode &&
      presentationRenderStatus === "ready" &&
      !presentationSlidevBuildUrl &&
      !isGenerating &&
      !buildRetryRef.current
    ) {
      buildRetryRef.current = true;
      void refreshSlidevPreviewStateEffect().finally(() => {
        buildRetryRef.current = false;
      });
    }
  }, [isSlidevMode, presentationRenderStatus, presentationSlidevBuildUrl, isGenerating]);

  if (!isSlidevMode && !slidevHasContent && centiDeckSlides.length === 0 && !jobId) {
    return (
      <div className="zy-bg-page flex min-h-screen items-center justify-center p-6">
        <div className="zy-card-glass w-full max-w-xl p-8 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl border border-white/80 bg-white/75 text-slate-700 shadow-sm">
            <LayoutPanelLeft className="h-5 w-5" />
          </div>
          <div className="mt-5 space-y-2">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
              还没有可编辑的演示稿
            </h1>
            <p className="text-sm leading-6 text-slate-600">
              当前会话还没有生成出可进入编辑器的结果。你可以继续任务，或者回到创建页继续整理素材与指令。
            </p>
          </div>
          {canResume && (
            <button
              onClick={() => {
                void handleResume();
              }}
              disabled={resuming}
              className="mt-6 inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-cyan-200 bg-cyan-50 px-4 text-sm font-medium text-cyan-700 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md disabled:opacity-60"
            >
              {resuming && <Loader2 className="h-4 w-4 animate-spin" />}
              {resuming ? "继续中..." : "继续任务"}
            </button>
          )}

          <div className="mt-4 flex items-center justify-center gap-3">
            <button
              onClick={() => router.push(returnHref)}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white transition-all duration-200 hover:-translate-y-0.5 hover:bg-slate-800 hover:shadow-lg"
            >
              <ArrowLeft className="h-4 w-4" />
              返回创建
            </button>
          </div>
        </div>
      </div>
    );
  }

  const handleCloseReveal = () => {
    if (revealSlideIndex !== currentSlideIndex) {
      setCurrentSlideIndex(revealSlideIndex);
    }
    setShowReveal(false);
  };

  const handleExport = async (format: "pptx" | "pdf") => {
    if (exporting || !canExport || !currentSessionId) return;
    setExporting(true);

    try {
      const blob =
        format === "pptx"
          ? await exportSessionPptx(currentSessionId)
          : await exportSessionPdf(currentSessionId);

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(sessionTitle || "presentation").slice(0, 30)}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success(`${format.toUpperCase()} 导出成功`);
    } catch (err) {
      console.error("导出失败:", err);
      toast.error(`导出失败: ${err instanceof Error ? err.message : "未知错误"}`);
    } finally {
      setExporting(false);
    }
  };

  const handleSaveSpeakerNotes = async (): Promise<boolean> => {
    if (!currentSessionId || !currentSlideId) return false;
    if (speakerNotesDraft === currentCanonicalSpeakerNotes) return true;

    setSavingSpeakerNotes(true);

    try {
      if (isSlidevMode) {
        const response = await saveSlidevSpeakerNotes(
          currentSessionId,
          currentSlideId,
          speakerNotesDraft
        );
        setPresentationSlidevState({
          outputMode: "slidev",
          markdown: presentationSlidevMarkdown,
          meta: presentationSlidevMeta,
          deckArtifact: presentationSlidevDeckArtifact,
          buildArtifact: presentationSlidevBuildArtifact,
          buildUrl: presentationSlidevBuildUrl,
          notesState: response.slidevNotesState ?? {
            ...presentationSlidevNotesState,
            [currentSlideId]: speakerNotesDraft,
          },
          audioState: {
            ...presentationSlidevAudioState,
            [currentSlideId]: undefined,
          },
        });
        setSpeakerNotesDrafts((current) => ({
          ...current,
          [currentSlideId]: speakerNotesDraft,
        }));
        toast.success("已保存当前页演讲者注解");
        return true;
      }
      return false;
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存演讲者注解失败");
      return false;
    } finally {
      setSavingSpeakerNotes(false);
    }
  };

  const handleGenerateSpeakerNotes = async (scope: "current" | "all") => {
    if (generatingSpeakerNotesScope || !currentSessionId) return;
    const slidevSnapshotNotesState =
      isSlidevMode && currentSlideId
        ? {
            ...presentationSlidevNotesState,
            [currentSlideId]: speakerNotesDraft,
          }
        : presentationSlidevNotesState;

    setGeneratingSpeakerNotesScope(scope);
    try {
      const response = await generateSpeakerNotes(currentSessionId, {
        presentation: null,
        slidevNotesState: isSlidevMode ? slidevSnapshotNotesState : undefined,
        scope,
        currentSlideIndex: currentSlideIndex,
      });
      if (isSlidevMode) {
        const clearedAudioState = { ...presentationSlidevAudioState };
        for (const slideId of response.updatedSlideIds) {
          delete clearedAudioState[slideId];
        }
        setPresentationSlidevState({
          outputMode: "slidev",
          markdown: presentationSlidevMarkdown,
          meta: presentationSlidevMeta,
          deckArtifact: presentationSlidevDeckArtifact,
          buildArtifact: presentationSlidevBuildArtifact,
          buildUrl: presentationSlidevBuildUrl,
          notesState: response.slidevNotesState ?? slidevSnapshotNotesState,
          audioState: clearedAudioState,
        });
      }
      toast.success(
        scope === "current"
          ? "已生成并覆盖当前页演讲者注解"
          : `已生成并覆盖 ${response.updatedSlideIds.length} 页演讲者注解`
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "生成演讲者注解失败");
    } finally {
      setGeneratingSpeakerNotesScope(null);
    }
  };

  const handlePlaySpeakerAudio = async (signal: AbortSignal): Promise<Blob> => {
    if (!currentSessionId || !currentSlideId) {
      throw new Error("当前没有可朗读的页面");
    }
    if (speakerNotesDraft !== currentCanonicalSpeakerNotes) {
      const saved = await handleSaveSpeakerNotes();
      if (!saved) {
        throw new Error("保存当前注解失败，无法生成录音");
      }
    }
    const response = await ensureSpeakerAudio(currentSessionId, currentSlideId);
    if (isSlidevMode) {
      setPresentationSlidevState({
        outputMode: "slidev",
        markdown: presentationSlidevMarkdown,
        meta: presentationSlidevMeta,
        deckArtifact: presentationSlidevDeckArtifact,
        buildArtifact: presentationSlidevBuildArtifact,
        buildUrl: presentationSlidevBuildUrl,
        notesState: presentationSlidevNotesState,
        audioState: {
          ...presentationSlidevAudioState,
          [currentSlideId]: response.speakerAudio,
        },
      });
    }
    return fetchSpeakerAudio(currentSessionId, currentSlideId, signal);
  };

  if (showReveal && isSlidevMode) {
    return (
      <div className="fixed inset-0 z-50 bg-black">
        <button
          onClick={handleCloseReveal}
          className="absolute top-4 right-4 z-50 rounded-md border border-slate-300 bg-white/95 px-3 py-1 text-sm text-slate-900 shadow-sm backdrop-blur hover:bg-white"
        >
          退出演示
        </button>
        <SlidevPreview
          src={presentationSlidevBuildUrl}
          startSlide={revealSlideIndex}
          onSlideChange={setRevealSlideIndex}
        />
      </div>
    );
  }

  return (
    <div className="zy-bg-page flex h-screen flex-col overflow-hidden">
      <header className="shrink-0 border-b border-slate-200/70 bg-white/75 backdrop-blur-xl">
        <div className="flex min-h-12 items-center justify-between gap-4 px-4 py-2">
          <div className="flex min-w-0 items-center gap-3">
            <button
              onClick={() => router.push(returnHref)}
              className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
            >
              <ArrowLeft className="h-4 w-4" />
              {returnLabel}
            </button>
            <div className="h-4 w-px bg-slate-200" />
            <SessionTitleInlineEditor
              title={sessionTitle}
              onSave={onRenameSessionTitle}
              className="min-w-0"
            />
            {statusBadge && (
              <span
                className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${statusBadge.className}`}
              >
                {statusBadge.label}
              </span>
            )}
            {isGenerating && totalCount > 0 && (
              <span className="hidden items-center gap-1.5 text-xs text-slate-500 lg:inline-flex">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                生成中 ({loadedCount}/{totalCount})
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  disabled={exporting || !canExport}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-300 bg-white/80 px-3 text-sm text-slate-700 transition-all duration-200 hover:-translate-y-0.5 hover:bg-white hover:shadow-md focus-visible:ring-2 focus-visible:ring-cyan-500/60 disabled:opacity-50"
                >
                  {exporting ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <FileOutput className="h-3.5 w-3.5" />
                  )}
                  {exporting ? "正在导出..." : "导出"}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => handleExport("pptx")}>
                  导出 PPTX
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleExport("pdf")}>
                  导出 PDF
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <button
              type="button"
              onClick={() => {
                void handleShare();
              }}
              disabled={!canShare || creatingShareLink}
              title={canShare ? "生成并查看分享链接" : "当前暂无可分享的演示稿"}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-300 bg-white/80 px-3 text-sm text-slate-700 transition-all duration-200 hover:-translate-y-0.5 hover:bg-white hover:shadow-md focus-visible:ring-2 focus-visible:ring-cyan-500/60 disabled:opacity-50"
            >
              {creatingShareLink ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Share2 className="h-3.5 w-3.5" />
              )}
              {creatingShareLink ? "生成中..." : "分享"}
            </button>
            {canResume && (
              <button
                onClick={() => {
                  void handleResume();
                }}
                disabled={resuming || isGenerating}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-cyan-200 bg-cyan-50 px-3 text-sm font-medium text-cyan-700 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md disabled:opacity-50"
              >
                {resuming && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                {resuming ? "继续中..." : "继续任务"}
              </button>
            )}
            {waitingOutlineReview && (
              <button
                onClick={() => {
                  void handleAcceptOutline();
                }}
                disabled={acceptingOutline || isGenerating}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 text-sm font-medium text-emerald-700 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md disabled:opacity-50"
              >
                {acceptingOutline ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-3.5 w-3.5" />
                )}
                {acceptingOutline ? "确认中..." : "确认大纲并继续"}
              </button>
            )}
            {isGenerating && (
              <button
                onClick={() => {
                  void handleCancelGeneration();
                }}
                className="inline-flex h-9 items-center rounded-lg border border-slate-300 bg-white/80 px-3 text-sm text-slate-700 transition-all duration-200 hover:bg-white hover:shadow-sm"
              >
                取消生成
              </button>
            )}
            {totalIssueCount > 0 && (
              <button
                type="button"
                onClick={() => {
                  if (activeIssueSlideId) {
                    openIssuePanelForSlide(activeIssueSlideId);
                  } else {
                    setIssuePanelOpen(true);
                  }
                }}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 text-sm font-medium text-amber-700 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-sm"
              >
                <AlertTriangle className="h-3.5 w-3.5" />
                校验问题（{totalIssueCount}）
              </button>
            )}
            <button
              onClick={() => {
                if (!currentSessionId) return;
                if (isSlidevMode) {
                  setRevealSlideIndex(currentSlideIndex);
                  setShowReveal(true);
                  return;
                }
                router.push(
                  getSessionPresenterPath(currentSessionId, {
                    slide: currentSlideIndex + 1,
                  })
                );
              }}
              disabled={isGenerating || (isSlidevMode && (!presentationSlidevBuildUrl || presentationRenderStatus !== "ready"))}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-slate-900 px-3 text-sm font-medium text-white transition-all duration-200 hover:-translate-y-0.5 hover:bg-slate-800 hover:shadow-lg focus-visible:ring-2 focus-visible:ring-cyan-500/70 disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5" />
              演示
            </button>
            <UserMenu compact />
          </div>
        </div>
        {isGenerating && (
          <div className="px-4 pb-3">
            <div className="overflow-hidden rounded-full border border-white/70 bg-white/60 shadow-sm">
              <Progress value={genPct} className="h-1.5 rounded-none" />
            </div>
          </div>
        )}
      </header>

      <div className="flex min-h-0 flex-1 gap-4 overflow-hidden p-4">
        <aside className="zy-card-glass flex w-64 shrink-0 flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b border-white/70 px-4 py-3">
            <div className="flex items-baseline gap-2">
              <h2 className="text-sm font-semibold text-slate-900">页面目录</h2>
              <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">
                Slides
              </p>
            </div>
            <div className="rounded-full border border-white/80 bg-white/75 px-2 py-1 text-xs font-medium text-slate-600">
              {totalCount} 页
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            <div className="space-y-2">
              {isSlidevMode ? (
                slidevMetaSlides.map((slide, i) => (
                  <button
                    key={String(slide.slide_id ?? `slide-${i + 1}`)}
                    type="button"
                    onClick={() => setCurrentSlideIndex(i)}
                    className={`zy-list-item w-full p-3 text-left ${
                      i === currentSlideIndex
                        ? "border-cyan-300 bg-white shadow-[0_18px_40px_-28px_rgba(14,165,233,0.45)] ring-1 ring-cyan-200"
                        : ""
                    }`}
                  >
                    <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">
                      {slide.role ? String(slide.role) : `Slide ${i + 1}`}
                    </div>
                    <div className="mt-1 text-sm font-semibold text-slate-900">
                      {String(slide.title ?? `第 ${i + 1} 页`)}
                    </div>
                  </button>
                ))
              ) : centiDeckSlides.length > 0 ? (
                centiDeckSlides.map((slide, i) => {
                  const slideRecord = slide as {
                    slideId?: unknown;
                    title?: unknown;
                  };
                  const slideKey = String(slideRecord.slideId ?? `slide-${i + 1}`);
                  const slideTitle = String(slideRecord.title ?? `第 ${i + 1} 页`);
                  return (
                    <button
                      key={slideKey}
                      type="button"
                      onClick={() => setCurrentSlideIndex(i)}
                      className={`zy-list-item w-full p-3 text-left ${
                        i === currentSlideIndex
                          ? "border-cyan-300 bg-white shadow-[0_18px_40px_-28px_rgba(14,165,233,0.45)] ring-1 ring-cyan-200"
                          : ""
                      }`}
                    >
                      <div className="overflow-hidden rounded-xl border border-slate-200 bg-slate-950 shadow-[0_18px_40px_-32px_rgba(15,23,42,0.45)]">
                        <div className="aspect-[16/9] w-full">
                          {centiDeckArtifact ? (
                            <CentiDeckPreview
                              artifactOverride={centiDeckArtifact}
                              startSlide={i}
                              mode="thumbnail"
                              className="pointer-events-none h-full w-full"
                            />
                          ) : (
                            <div className="flex h-full w-full items-center justify-center text-[11px] text-slate-400">
                              缩略图加载中…
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="mt-3 text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">
                        Slide {i + 1}
                      </div>
                      <div className="mt-1 text-sm font-semibold text-slate-900">
                        {slideTitle}
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="rounded border border-dashed border-slate-200 bg-white/70 p-3 text-xs text-slate-500">
                  演示稿尚未生成，目录将在就绪后显示。
                </div>
              )}
            </div>
          </div>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <section className="zy-card-glass flex min-h-0 flex-1 flex-col overflow-hidden">
            <div className="flex items-center justify-between border-b border-white/70 px-5 py-3">
              <div className="flex items-baseline gap-2">
                <h2 className="text-sm font-semibold text-slate-900">当前画布</h2>
                <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">
                  Preview
                </p>
              </div>
              <div className="rounded-full border border-white/80 bg-white/75 px-3 py-1 text-xs font-medium text-slate-600">
                第 {Math.min(currentSlideIndex + 1, totalCount)} / {totalCount} 页
              </div>
            </div>
            <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto p-5 lg:p-7">
              <div className="flex min-h-full w-full items-center justify-center rounded-[28px] border border-white/70 bg-white/35 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)] lg:p-6">
                {isSlidevMode ? (
                  Boolean(currentSlideMeta) ? (
                    slidevPreviewState.previewReady && slidevPreviewState.buildUrl ? (
                      <div className="w-full max-w-5xl">
                        <div className="aspect-[16/9] overflow-hidden rounded-[20px] border border-white/80 bg-white shadow-[0_28px_80px_-48px_rgba(15,23,42,0.55)]">
                          <SlidevPreview
                            src={slidevPreviewState.buildUrl}
                            startSlide={currentSlideIndex}
                            onSlideChange={setCurrentSlideIndex}
                            className="rounded-[20px]"
                          />
                        </div>
                      </div>
                    ) : presentationSlidevMarkdown ? (
                      <div className="flex w-full max-w-5xl flex-col gap-4">
                        <div className="rounded-[20px] border border-amber-200 bg-amber-50/90 p-4 text-sm text-amber-900">
                          <div className="font-medium">
                            {slidevPreviewState.buildFailed
                              ? "Slidev 预览构建失败，已保留原始 markdown artifact。"
                              : "Slidev 预览正在构建，完成后会自动切换到真实预览。"}
                          </div>
                          {slidevPreviewState.renderError && (
                            <div className="mt-2 whitespace-pre-wrap text-xs leading-6 text-amber-800">
                              {slidevPreviewState.renderError}
                            </div>
                          )}
                          <div className="mt-3 flex gap-3">
                            <button
                              type="button"
                              onClick={() => {
                                void handleRetrySlidevRender();
                              }}
                              disabled={retryingSlidevRender || isGenerating}
                              className="inline-flex items-center justify-center rounded-lg border border-amber-300 bg-white/90 px-3 py-2 text-sm font-medium text-amber-900 transition hover:bg-white disabled:opacity-50"
                            >
                              {retryingSlidevRender ? "重试中..." : "手动重试渲染"}
                            </button>
                          </div>
                        </div>
                        <div className="overflow-hidden rounded-[20px] border border-white/80 bg-slate-950 shadow-[0_28px_80px_-48px_rgba(15,23,42,0.55)]">
                          <pre className="max-h-[65vh] overflow-auto p-5 text-xs leading-6 text-slate-100">
                            <code>{presentationSlidevMarkdown}</code>
                          </pre>
                        </div>
                      </div>
                    ) : (
                      <div className="flex aspect-[16/9] w-full items-center justify-center rounded-lg border border-dashed border-slate-200 bg-white/70 px-6 text-center text-sm text-slate-500">
                        Slidev 演示稿还在生成中，完成后会自动切换到真实预览。
                      </div>
                    )
                  ) : (
                    <div className="w-full max-w-4xl">
                      <div className="flex aspect-[16/9] items-center justify-center rounded-lg border border-dashed border-slate-200 bg-white/70 text-sm text-slate-500">
                        当前没有可预览的页面
                      </div>
                    </div>
                  )
                ) : (
                  <div className="w-full max-w-4xl">
                    <div className="relative aspect-[16/9] overflow-hidden rounded-lg border border-slate-200 bg-slate-950">
                      <CentiDeckPreview
                        sessionId={currentSessionId}
                        artifactOverride={centiDeckArtifact}
                        startSlide={currentSlideIndex}
                        onSlideChange={setCurrentSlideIndex}
                        mode="interactive"
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
            <SpeakerNotes
              value={speakerNotesDraft}
              onChange={(nextValue) => {
                if (!currentSlideId) return;
                setSpeakerNotesDrafts((current) => ({
                  ...current,
                  [currentSlideId]: nextValue,
                }));
              }}
              onSave={() => {
                void handleSaveSpeakerNotes();
              }}
              onGenerateCurrent={() => {
                void handleGenerateSpeakerNotes("current");
              }}
              onGenerateAll={() => {
                void handleGenerateSpeakerNotes("all");
              }}
              onPlayAudio={handlePlaySpeakerAudio}
              isSaving={savingSpeakerNotes}
              generatingScope={generatingSpeakerNotesScope}
              canGenerate={Boolean(currentSlideId)}
              canSave={Boolean(currentSlideId) && hasUnsavedSpeakerNotes}
            />
          </section>
        </main>
      </div>

      <IssueReviewDrawer
        open={issuePanelOpen}
        onOpenChange={setIssuePanelOpen}
        isSlidevMode={isSlidevMode}
        slidevMetaSlides={slidevMetaSlides}
        slidevBuildUrl={presentationSlidevBuildUrl}
        groupedIssues={groupedIssues}
        issueDecisionBySlideId={issueDecisionBySlideId}
        focusSlideId={activeIssueSlideId}
        onFocusSlide={(slideId) => {
          const targetIndex = isSlidevMode
            ? slidevMetaSlides.findIndex((slide) => String(slide.slide_id ?? "") === slideId)
            : -1;
          if (targetIndex >= 0) {
            setCurrentSlideIndex(targetIndex);
          }
          openIssuePanelForSlide(slideId);
        }}
        fixPreviewSlidev={fixPreviewSlidev}
        fixPreviewSourceIds={fixPreviewSourceIds}
        waitingFixReview={waitingFixReview}
        previewingFix={previewingFix}
        applyingFix={applyingFix}
        skippingFix={skippingFix}
        onGeneratePreview={(slideId) => {
          void handlePreviewFix([slideId]);
        }}
        onApplySelected={() => {
          void handleApplyFix();
        }}
        onSkipAll={() => {
          void handleSkipFix();
        }}
        onDiscardPreview={handleDiscardFixPreview}
        onMarkHandled={handleMarkSlideHandled}
      />
      <ShareLinkDialog
        open={shareDialogOpen}
        shareUrl={shareUrl}
        loading={creatingShareLink}
        onCopy={() => {
          void handleCopyShareLink();
        }}
        onClose={() => setShareDialogOpen(false)}
      />

      <FloatingChatPanel />
    </div>
  );
}

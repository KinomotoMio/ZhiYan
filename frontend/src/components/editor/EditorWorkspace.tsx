"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ExternalLink,
  FileOutput,
  LayoutPanelLeft,
  Loader2,
  Play,
  Share2,
} from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { useAppStore } from "@/lib/store";
import {
  acceptOutline,
  cancelJob,
  ensureSpeakerAudio,
  exportPptx,
  exportPdf,
  exportSessionPdf,
  exportSessionPptx,
  fetchSpeakerAudio,
  fixApply,
  fixPreview,
  fixSkip,
  generateSpeakerNotes,
  createOrGetSessionShareLink,
  getLatestSessionPresentation,
  getLatestSessionPresentationHtmlManifest,
  getLatestSessionPresentationHtmlRender,
  getLatestSessionPresentationSlidev,
  saveLatestSessionPresentation,
  saveLatestSessionHtmlPresentation,
  saveLatestSessionSlidevPresentation,
} from "@/lib/api";
import { collectIssueSlideIds, groupIssuesBySlide } from "@/lib/verification-issues";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { canResumeGenerationJob, getSessionPresenterPath } from "@/lib/routes";
import { useHtmlRuntimeRoomSync } from "@/lib/use-html-runtime-room-sync";
import { resumeGenerationJob } from "@/components/editor/resume-job";
import SlidePreview from "@/components/slides/SlidePreview";
import SlideThumbnail from "@/components/slides/SlideThumbnail";
import SpeakerNotes from "@/components/slides/SpeakerNotes";
import RevealPreview from "@/components/slides/RevealPreview";
import HtmlRuntimePreview from "@/components/slides/HtmlRuntimePreview";
import SlidevPreview from "@/components/slides/SlidevPreview";
import HtmlPreviewSurface from "@/components/slides/HtmlPreviewSurface";
import FloatingChatPanel from "@/components/chat/FloatingChatPanel";
import UserMenu from "@/components/settings/UserMenu";
import IssueReviewDrawer from "@/components/editor/IssueReviewDrawer";
import ShareLinkDialog from "@/components/editor/ShareLinkDialog";
import SessionTitleInlineEditor from "@/components/session/SessionTitleInlineEditor";
import { mergeSpeakerNotesDrafts } from "@/components/editor/speakerNotesDrafts";
import {
  applySpeakerAudioMetaToSlides,
  applySpeakerNotesDraftToSlides,
  buildSpeakerNotesDraftMap,
} from "@/components/editor/speaker-notes-flow";
import type { Presentation } from "@/types/slide";

interface EditorWorkspaceProps {
  returnHref: string;
  returnLabel?: string;
  sessionTitle: string;
  onRenameSessionTitle: (nextTitle: string) => Promise<void>;
}

function getJobStatusBadge(jobStatus: string | null, isGenerating: boolean) {
  if (isGenerating || jobStatus === "running") {
    return {
      label: "生成进行中",
      className: "border-cyan-200 bg-cyan-50 text-cyan-700",
    };
  }
  if (jobStatus === "artifact_ready") {
    return {
      label: "原始产物已就绪",
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
    presentation,
    presentationOutputMode,
    presentationHtml,
    presentationHtmlManifest,
    presentationHtmlRender,
    presentationSlidevBuildUrl,
    presentationSlidevMeta,
    presentationSlidevMarkdown,
    presentationHtmlArtifact,
    presentationSlidevDeckArtifact,
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
    initGenerationShell,
    setFixPreviewSelection,
    toggleFixPreviewSelection,
    setIssuePanelOpen,
    openIssuePanelForSlide,
    setIssueDecision,
    markSlidesProcessed,
    issues,
    hardIssueSlideIds,
    fixPreviewSlides,
    selectedFixPreviewSlideIds,
    issuePanelOpen,
    issuePanelSlideId,
    issueDecisionBySlideId,
    setPresentation,
    setPresentationHtmlState,
    setPresentationSlidevState,
    setPresentationRenderState,
    updateSlides,
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
  const [retryingHtmlRender, setRetryingHtmlRender] = useState(false);
  const [retryingSlidevRender, setRetryingSlidevRender] = useState(false);
  const [speakerNotesDrafts, setSpeakerNotesDrafts] = useState<Record<string, string>>({});
  const [savingSpeakerNotes, setSavingSpeakerNotes] = useState(false);
  const [generatingSpeakerNotesScope, setGeneratingSpeakerNotesScope] = useState<
    "current" | "all" | null
  >(null);
  const isHtmlMode = presentationOutputMode === "html";
  const isSlidevMode = presentationOutputMode === "slidev";
  const prevPresentationRef = useRef(presentation);
  const htmlPreviewAutoRefreshKeyRef = useRef<string | null>(null);
  const htmlPreviewReady = Boolean(presentationHtmlRender?.documentHtml);
  const htmlRenderFailed =
    isHtmlMode && (jobStatus === "render_failed" || presentationRenderStatus === "failed");
  const htmlRenderPending =
    isHtmlMode &&
    !htmlPreviewReady &&
    (isGenerating ||
      jobStatus === "running" ||
      jobStatus === "artifact_ready" ||
      presentationRenderStatus === "pending");
  const htmlPreviewMissingAfterCompletion =
    isHtmlMode &&
    !htmlPreviewReady &&
    !htmlRenderFailed &&
    !htmlRenderPending &&
    (jobStatus === "completed" || presentationRenderStatus === "ready");
  const canRetryHtmlRender = Boolean(
    isHtmlMode && currentSessionId && presentation && presentationHtmlManifest && !isGenerating
  );

  const canResume = canResumeGenerationJob(jobId, jobStatus);
  const waitingOutlineReview = jobStatus === "waiting_outline_review";
  const canShare = Boolean(
    currentSessionId &&
      !isGenerating &&
      !isSlidevMode &&
      (isHtmlMode
        ? presentationHtmlRender?.documentHtml
        : presentation && presentation.slides.length > 0)
  );
  const canExport = Boolean(
    currentSessionId &&
      !isGenerating &&
      !isSlidevMode &&
      (isHtmlMode
        ? presentationHtmlRender?.documentHtml
        : presentation && presentation.slides.length > 0)
  );
  const syncedHtmlSlideIndex = isHtmlMode && showReveal ? revealSlideIndex : currentSlideIndex;
  const { roomId: presenterRoomId, status: presenterRoomStatus } = useHtmlRuntimeRoomSync({
    sessionId: isHtmlMode ? currentSessionId : null,
    room: null,
    slideIndex: syncedHtmlSlideIndex,
    onRemoteSlideChange: (nextSlideIndex) => {
      if (showReveal && isHtmlMode) {
        setRevealSlideIndex(nextSlideIndex);
        return;
      }
      setCurrentSlideIndex(nextSlideIndex);
    },
    enabled: isHtmlMode && Boolean(presentationHtmlRender?.documentHtml),
  });

  const refreshHtmlPreviewState = async () => {
    if (!currentSessionId) return;
    const [latestPresentation, latestManifest, latestRender] = await Promise.all([
      getLatestSessionPresentation(currentSessionId),
      getLatestSessionPresentationHtmlManifest(currentSessionId),
      getLatestSessionPresentationHtmlRender(currentSessionId),
    ]);
    setPresentationHtmlState(
      "html",
      latestRender?.documentHtml ?? null,
      latestManifest ?? null,
      latestRender ?? null,
      latestPresentation?.artifacts?.html_deck ?? presentationHtmlArtifact
    );
    setPresentationRenderState({
      artifactStatus: latestPresentation?.artifact_status ?? null,
      renderStatus: latestPresentation?.render_status ?? null,
      renderError: latestPresentation?.render_error ?? null,
    });
  };

  useEffect(() => {
    if (!isHtmlMode || !currentSessionId || htmlPreviewReady) {
      htmlPreviewAutoRefreshKeyRef.current = null;
      return;
    }
    const shouldRefresh =
      jobStatus === "completed" ||
      jobStatus === "artifact_ready" ||
      presentationRenderStatus === "ready";
    if (!shouldRefresh) {
      htmlPreviewAutoRefreshKeyRef.current = null;
      return;
    }
    const refreshKey = [
      currentSessionId,
      jobStatus ?? "none",
      presentationRenderStatus ?? "none",
      presentationHtmlManifest ? "manifest" : "no-manifest",
    ].join(":");
    if (htmlPreviewAutoRefreshKeyRef.current === refreshKey) {
      return;
    }
    htmlPreviewAutoRefreshKeyRef.current = refreshKey;
    void (async () => {
      try {
        const [latestPresentation, latestManifest, latestRender] = await Promise.all([
          getLatestSessionPresentation(currentSessionId),
          getLatestSessionPresentationHtmlManifest(currentSessionId),
          getLatestSessionPresentationHtmlRender(currentSessionId),
        ]);
        setPresentationHtmlState(
          "html",
          latestRender?.documentHtml ?? null,
          latestManifest ?? null,
          latestRender ?? null,
          latestPresentation?.artifacts?.html_deck ?? presentationHtmlArtifact
        );
        setPresentationRenderState({
          artifactStatus: latestPresentation?.artifact_status ?? null,
          renderStatus: latestPresentation?.render_status ?? null,
          renderError: latestPresentation?.render_error ?? null,
        });
      } catch {
        htmlPreviewAutoRefreshKeyRef.current = null;
      }
    })();
  }, [
    currentSessionId,
    htmlPreviewReady,
    isHtmlMode,
    jobStatus,
    presentationHtmlArtifact,
    presentationHtmlManifest,
    presentationRenderStatus,
    setPresentationHtmlState,
    setPresentationRenderState,
  ]);

  const refreshSlidevPreviewState = async () => {
    if (!currentSessionId) return;
    const [latestPresentation, latestSlidev] = await Promise.all([
      getLatestSessionPresentation(currentSessionId),
      getLatestSessionPresentationSlidev(currentSessionId),
    ]);
    setPresentationSlidevState({
      outputMode: "slidev",
      markdown: latestSlidev?.markdown ?? presentationSlidevMarkdown,
      meta: latestSlidev?.meta ?? presentationSlidevMeta,
      deckArtifact: latestPresentation?.artifacts?.slidev_deck ?? presentationSlidevDeckArtifact,
      buildArtifact: latestPresentation?.artifacts?.slidev_build ?? null,
      buildUrl: latestSlidev?.build_url ?? null,
    });
    setPresentationRenderState({
      artifactStatus: latestPresentation?.artifact_status ?? latestSlidev?.artifact_status ?? null,
      renderStatus: latestPresentation?.render_status ?? latestSlidev?.render_status ?? null,
      renderError: latestPresentation?.render_error ?? latestSlidev?.render_error ?? null,
    });
  };

  const handleResume = async () => {
    if (!jobId || resuming) return;
    setResuming(true);
    try {
      if (!currentSessionId) throw new Error("缺少 session_id");
      const resumed = await resumeGenerationJob(currentSessionId, jobId);
      updateJobState({
        lastJobEventSeq: resumed.eventsSeq,
      });
      if (!presentation) {
        initGenerationShell(resumed.requestTitle, resumed.requestNumPages);
      }
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

  const handleRetryHtmlRender = async () => {
    if (
      retryingHtmlRender ||
      !currentSessionId ||
      !presentation ||
      !presentationHtmlManifest ||
      !isHtmlMode
    ) {
      return;
    }
    setRetryingHtmlRender(true);
    try {
      await saveLatestSessionHtmlPresentation(
        currentSessionId,
        presentation,
        presentationHtmlManifest,
        "editor"
      );
      await refreshHtmlPreviewState();
      const nextRender = useAppStore.getState().presentationHtmlRender?.documentHtml;
      if (nextRender) {
        toast.success("已重新完成 HTML 预览构建");
      } else {
        toast.warning("已重新尝试构建，但 HTML 预览仍不可用");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "重新构建 HTML 预览失败");
    } finally {
      setRetryingHtmlRender(false);
    }
  };

  const handleRetrySlidevRender = async () => {
    if (
      retryingSlidevRender ||
      !currentSessionId ||
      !presentation ||
      !presentationSlidevMarkdown ||
      !isSlidevMode
    ) {
      return;
    }
    setRetryingSlidevRender(true);
    try {
      await saveLatestSessionSlidevPresentation(
        currentSessionId,
        presentation,
        presentationSlidevMarkdown,
        presentationSlidevDeckArtifact?.selected_style_id ?? null,
        presentationSlidevMeta ?? undefined,
        "editor"
      );
      await refreshSlidevPreviewState();
      const nextState = useAppStore.getState().presentationRenderStatus;
      if (nextState === "ready") {
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
        fixPreviewSlides: Array.isArray(job.fix_preview_slides)
          ? job.fix_preview_slides
          : [],
        fixPreviewSourceIds: sourceIds,
        selectedFixPreviewSlideIds: sourceIds,
      });
      setFixPreviewSelection(sourceIds);
      toast.success(`已生成 ${sourceIds.length} 页修复建议`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "生成修复建议失败");
    } finally {
      setPreviewingFix(false);
    }
  };

  const handleApplyFix = async () => {
    if (!jobId || applyingFix || previewingFix || skippingFix) return;
    if (selectedFixPreviewSlideIds.length === 0) {
      toast.info("请先勾选要应用的页面");
      return;
    }
    setApplyingFix(true);
    try {
      if (!currentSessionId) throw new Error("缺少 session_id");
      const job = await fixApply(currentSessionId, jobId, selectedFixPreviewSlideIds);
      if (job.presentation) {
        setPresentation(job.presentation);
      }
      const normalizedIssues = Array.isArray(job.issues)
        ? (job.issues as Array<Record<string, unknown>>)
        : [];
      const allIssueSlideIds = collectIssueSlideIds(normalizedIssues);
      const selectedSet = new Set(selectedFixPreviewSlideIds);
      const skippedSlideIds = allIssueSlideIds.filter((slideId) => !selectedSet.has(slideId));
      markSlidesProcessed(selectedFixPreviewSlideIds, "applied");
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
        fixPreviewSlides: [],
        fixPreviewSourceIds: [],
        selectedFixPreviewSlideIds: [],
      });
      setIsGenerating(false);
      toast.success("已按所选页面应用修复");
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
      if (job.presentation) {
        setPresentation(job.presentation);
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
        fixPreviewSlides: [],
        fixPreviewSourceIds: [],
        selectedFixPreviewSlideIds: [],
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
      fixPreviewSlides: [],
      fixPreviewSourceIds: [],
      selectedFixPreviewSlideIds: [],
    });
    setFixPreviewSelection([]);
    toast.info("已丢弃当前修复候选");
  };

  const handleMarkSlideHandled = (slideId: string) => {
    setIssueDecision(slideId, "skipped");
    toast.success(`已将 ${slideId} 标记为已处理`);
  };

  const slides = presentation?.slides ?? [];
  const currentSlide = slides[currentSlideIndex] ?? null;
  const loadedCount = slides.filter(
    (s) => !(s.contentData as Record<string, unknown> | undefined)?._loading
  ).length;
  const totalCount = slides.length;
  const genPct = totalCount > 0 ? Math.round((loadedCount / totalCount) * 100) : 0;
  const waitingFixReview = jobStatus === "waiting_fix_review";
  const statusBadge = getJobStatusBadge(jobStatus, isGenerating);
  const groupedIssues = groupIssuesBySlide(issues);
  const issueSlideIds = Array.from(groupedIssues.keys());
  const totalIssueCount = Array.from(groupedIssues.values()).reduce(
    (sum, item) => sum + item.total,
    0
  );
  const fixPreviewBySlideId = new Map(fixPreviewSlides.map((slide) => [slide.slideId, slide]));
  const activeIssueSlideId =
    issuePanelSlideId && groupedIssues.has(issuePanelSlideId)
      ? issuePanelSlideId
      : currentSlide && groupedIssues.has(currentSlide.slideId)
        ? currentSlide.slideId
        : issueSlideIds[0] ?? null;
  const speakerNotesDraft = currentSlide
    ? speakerNotesDrafts[currentSlide.slideId] ?? currentSlide.speakerNotes ?? ""
    : "";
  const hasUnsavedSpeakerNotes = currentSlide
    ? speakerNotesDraft !== (currentSlide.speakerNotes ?? "")
    : false;

  useEffect(() => {
    if (!presentation) {
      setSpeakerNotesDrafts({});
      prevPresentationRef.current = presentation;
      return;
    }

    setSpeakerNotesDrafts((current) => {
      const next = mergeSpeakerNotesDrafts({
        currentDrafts: current,
        previousSlides: prevPresentationRef.current?.slides,
        currentSlides: presentation.slides,
      });
      const currentKeys = Object.keys(current);
      const nextKeys = Object.keys(next);
      const unchanged =
        currentKeys.length === nextKeys.length &&
        nextKeys.every((key) => current[key] === next[key]);
      return unchanged ? current : next;
    });

    prevPresentationRef.current = presentation;
  }, [presentation]);

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

  if (!presentation) {
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
        isHtmlMode
          ? format === "pptx"
            ? await exportSessionPptx(currentSessionId)
            : await exportSessionPdf(currentSessionId)
          : format === "pptx"
            ? await exportPptx(presentation as Presentation)
            : await exportPdf(presentation as Presentation);

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(presentation?.title || sessionTitle || "presentation").slice(0, 30)}.${format}`;
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

  const handleSaveSpeakerNotes = async (): Promise<Presentation | null> => {
    if (!presentation || !currentSlide || !currentSessionId) return null;

    const currentNotes = currentSlide.speakerNotes ?? "";
    if (speakerNotesDraft === currentNotes) return presentation;

    const nextSlides = applySpeakerNotesDraftToSlides(
      presentation.slides,
      currentSlideIndex,
      speakerNotesDraft
    );
    const nextPresentation = { ...presentation, slides: nextSlides };

    updateSlides(nextSlides);
    setSavingSpeakerNotes(true);

    try {
      if (isHtmlMode) {
        if (!presentationHtmlManifest) {
          throw new Error("HTML 演示稿尚未加载完成，暂时无法保存演讲者注解");
        }
        await saveLatestSessionHtmlPresentation(
          currentSessionId,
          nextPresentation,
          presentationHtmlManifest,
          "editor"
        );
        await refreshHtmlPreviewState();
      } else {
        await saveLatestSessionPresentation(currentSessionId, nextPresentation, "editor");
      }
      setSpeakerNotesDrafts((current) => ({
        ...current,
        [currentSlide.slideId]: nextSlides[currentSlideIndex]?.speakerNotes ?? "",
      }));
      toast.success("已保存当前页演讲者注解");
      return nextPresentation;
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存演讲者注解失败");
      return null;
    } finally {
      setSavingSpeakerNotes(false);
    }
  };

  const handleGenerateSpeakerNotes = async (scope: "current" | "all") => {
    if (generatingSpeakerNotesScope || !presentation || !currentSessionId) return;
    const snapshot =
      speakerNotesDraft !== (currentSlide?.speakerNotes ?? "")
        ? {
            ...presentation,
            slides: applySpeakerNotesDraftToSlides(
              presentation.slides,
              currentSlideIndex,
              speakerNotesDraft
            ),
          }
        : presentation;

    setGeneratingSpeakerNotesScope(scope);
    try {
      const response = await generateSpeakerNotes(currentSessionId, {
        presentation: snapshot,
        scope,
        currentSlideIndex: currentSlideIndex,
      });
      setPresentation(response.presentation);
      setSpeakerNotesDrafts(buildSpeakerNotesDraftMap(response.presentation.slides));
      if (isHtmlMode) {
        await refreshHtmlPreviewState();
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
    if (!currentSessionId || !currentSlide) {
      throw new Error("当前没有可朗读的页面");
    }
    if (speakerNotesDraft !== (currentSlide.speakerNotes ?? "")) {
      const saved = await handleSaveSpeakerNotes();
      if (!saved) {
        throw new Error("保存当前注解失败，无法生成录音");
      }
    }
    const response = await ensureSpeakerAudio(currentSessionId, currentSlide.slideId);
    const latestPresentation = useAppStore.getState().presentation;
    if (latestPresentation) {
      updateSlides(
        applySpeakerAudioMetaToSlides(
          latestPresentation.slides,
          currentSlide.slideId,
          response.speakerAudio
        )
      );
    }
    return fetchSpeakerAudio(currentSessionId, currentSlide.slideId, signal);
  };

  const handleOpenPresenter = () => {
    if (!currentSessionId || !isHtmlMode) return;
    const href = getSessionPresenterPath(currentSessionId, {
      slide: syncedHtmlSlideIndex + 1,
      room: presenterRoomId,
    });
    window.open(href, "_blank", "noopener,noreferrer");
  };

  if (showReveal) {
    return (
      <div className="fixed inset-0 z-50 bg-black">
        <button
          onClick={handleCloseReveal}
          className="absolute top-4 right-4 z-50 rounded-md border border-slate-300 bg-white/95 px-3 py-1 text-sm text-slate-900 shadow-sm backdrop-blur hover:bg-white"
        >
          退出演示
        </button>
        {isSlidevMode ? (
          <SlidevPreview
            src={presentationSlidevBuildUrl}
            startSlide={revealSlideIndex}
            onSlideChange={setRevealSlideIndex}
          />
        ) : isHtmlMode ? (
          <HtmlRuntimePreview
            renderPayload={presentationHtmlRender}
            startSlide={revealSlideIndex}
            onSlideChange={setRevealSlideIndex}
          />
        ) : (
          <RevealPreview
            presentation={presentation}
            htmlContent={null}
            startSlide={revealSlideIndex}
            onSlideChange={setRevealSlideIndex}
          />
        )}
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
            {isHtmlMode && currentSessionId && presentationHtmlRender?.documentHtml && (
              <button
                type="button"
                onClick={handleOpenPresenter}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-300 bg-white/80 px-3 text-sm text-slate-700 transition-all duration-200 hover:-translate-y-0.5 hover:bg-white hover:shadow-sm"
                title={
                  presenterRoomStatus === "connected"
                    ? "打开 Presenter 路由（房间同步已就绪）"
                    : "打开 Presenter 路由"
                }
              >
                <ExternalLink className="h-3.5 w-3.5" />
                Presenter
              </button>
            )}
            <button
              onClick={() => {
                setRevealSlideIndex(currentSlideIndex);
                setShowReveal(true);
              }}
              disabled={isGenerating || (isSlidevMode && !presentationSlidevBuildUrl)}
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
              {presentation.slides.map((slide, i) =>
                isSlidevMode ? (
                  <button
                    key={slide.slideId}
                    type="button"
                    onClick={() => setCurrentSlideIndex(i)}
                    className={`zy-list-item w-full p-3 text-left ${
                      i === currentSlideIndex
                        ? "border-cyan-300 bg-white shadow-[0_18px_40px_-28px_rgba(14,165,233,0.45)] ring-1 ring-cyan-200"
                        : ""
                    }`}
                  >
                    <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">
                      {(presentationSlidevMeta?.slides as Array<Record<string, unknown>> | undefined)?.[i]?.role
                        ? String((presentationSlidevMeta?.slides as Array<Record<string, unknown>>)[i]?.role)
                        : `Slide ${i + 1}`}
                    </div>
                    <div className="mt-1 text-sm font-semibold text-slate-900">
                      {String(
                        (presentationSlidevMeta?.slides as Array<Record<string, unknown>> | undefined)?.[i]?.title ??
                          (slide.contentData?.title || `第 ${i + 1} 页`)
                      )}
                    </div>
                  </button>
                ) : (
                  <div
                    key={slide.slideId}
                    className={`zy-list-item p-2 ${
                      i === currentSlideIndex
                        ? "border-cyan-300 bg-white shadow-[0_18px_40px_-28px_rgba(14,165,233,0.45)] ring-1 ring-cyan-200"
                        : ""
                    }`}
                  >
                    <SlideThumbnail
                      slide={slide}
                      index={i}
                      isActive={i === currentSlideIndex}
                      onClick={() => setCurrentSlideIndex(i)}
                      htmlRender={isHtmlMode ? presentationHtmlRender : null}
                      htmlDocument={isHtmlMode ? presentationHtml : null}
                      htmlStartSlide={i}
                      issueMeta={
                        groupedIssues.has(slide.slideId)
                          ? {
                              hard: groupedIssues.get(slide.slideId)?.hard ?? 0,
                              advisory: groupedIssues.get(slide.slideId)?.advisory ?? 0,
                              total: groupedIssues.get(slide.slideId)?.total ?? 0,
                              decision: issueDecisionBySlideId[slide.slideId] ?? "pending",
                            }
                          : undefined
                      }
                      onIssueClick={
                        groupedIssues.has(slide.slideId)
                          ? () => {
                              setCurrentSlideIndex(i);
                              openIssuePanelForSlide(slide.slideId);
                            }
                          : undefined
                      }
                    />
                  </div>
                )
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
                {currentSlide ? (
                  isHtmlMode ? (
                    htmlPreviewReady ? (
                      <HtmlPreviewSurface
                        renderPayload={presentationHtmlRender}
                        documentHtml={presentationHtml}
                        startSlide={currentSlideIndex}
                        onSlideChange={setCurrentSlideIndex}
                        className="h-full min-h-0 w-full"
                        frameClassName="border border-white/80 bg-white shadow-[0_28px_80px_-48px_rgba(15,23,42,0.55)]"
                      />
                    ) : (
                      <div
                        className={`flex aspect-[16/9] w-full max-w-5xl flex-col items-center justify-center rounded-[20px] px-6 text-center ${
                          htmlRenderFailed || htmlPreviewMissingAfterCompletion
                            ? "border border-amber-200 bg-amber-50/90 text-amber-900"
                            : "border border-dashed border-slate-200 bg-white/70 text-slate-500"
                        }`}
                      >
                        <div className="font-medium">
                          {htmlRenderFailed
                            ? "HTML 预览构建失败，内容已生成但无法显示真实预览。"
                            : htmlPreviewMissingAfterCompletion
                              ? "内容已生成，但 HTML 预览文件暂未就绪。"
                              : "HTML 演示稿还在生成中，完成后会自动切换到真实预览。"}
                        </div>
                        {(htmlRenderFailed ||
                          htmlPreviewMissingAfterCompletion ||
                          presentationRenderError) && (
                          <div className="mt-2 max-w-2xl whitespace-pre-wrap text-xs leading-6 text-amber-800">
                            {presentationRenderError ??
                              (htmlPreviewMissingAfterCompletion
                                ? "这通常表示预览产物缺失或未成功落盘，可以手动重试构建。"
                                : "可以手动重试构建 HTML 预览。")}
                          </div>
                        )}
                        {canRetryHtmlRender &&
                          (htmlRenderFailed || htmlPreviewMissingAfterCompletion) && (
                            <div className="mt-4">
                              <button
                                type="button"
                                onClick={() => {
                                  void handleRetryHtmlRender();
                                }}
                                disabled={retryingHtmlRender}
                                className="inline-flex items-center justify-center rounded-lg border border-amber-300 bg-white/90 px-3 py-2 text-sm font-medium text-amber-900 transition hover:bg-white disabled:opacity-50"
                              >
                                {retryingHtmlRender ? "重试中..." : "重试构建 HTML 预览"}
                              </button>
                            </div>
                          )}
                      </div>
                    )
                  ) : isSlidevMode ? (
                    presentationSlidevBuildUrl && presentationRenderStatus !== "failed" ? (
                      <div className="w-full max-w-5xl">
                        <div className="aspect-[16/9] overflow-hidden rounded-[20px] border border-white/80 bg-white shadow-[0_28px_80px_-48px_rgba(15,23,42,0.55)]">
                          <SlidevPreview
                            src={presentationSlidevBuildUrl}
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
                            {presentationRenderStatus === "failed"
                              ? "Slidev 预览构建失败，已保留原始 markdown artifact。"
                              : "Slidev 预览尚未就绪，先展示原始 markdown artifact。"}
                          </div>
                          {presentationRenderError && (
                            <div className="mt-2 whitespace-pre-wrap text-xs leading-6 text-amber-800">
                              {presentationRenderError}
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
                      <SlidePreview
                        slide={currentSlide}
                        className="shadow-[0_28px_80px_-48px_rgba(15,23,42,0.55)]"
                      />
                    </div>
                  )
                ) : (
                  <div className="w-full max-w-4xl">
                    <div className="flex aspect-[16/9] items-center justify-center rounded-lg border border-dashed border-slate-200 bg-white/70 text-sm text-slate-500">
                      当前没有可预览的页面
                    </div>
                  </div>
                )}
              </div>
            </div>
            <SpeakerNotes
              value={speakerNotesDraft}
              onChange={(nextValue) => {
                if (!currentSlide) return;
                setSpeakerNotesDrafts((current) => ({
                  ...current,
                  [currentSlide.slideId]: nextValue,
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
              canGenerate={Boolean(currentSlide)}
              canSave={Boolean(currentSlide) && hasUnsavedSpeakerNotes}
            />
          </section>
        </main>
      </div>

      <IssueReviewDrawer
        open={issuePanelOpen}
        onOpenChange={setIssuePanelOpen}
        slides={slides}
        groupedIssues={groupedIssues}
        issueDecisionBySlideId={issueDecisionBySlideId}
        focusSlideId={activeIssueSlideId}
        onFocusSlide={(slideId) => {
          const targetIndex = slides.findIndex((slide) => slide.slideId === slideId);
          if (targetIndex >= 0) {
            setCurrentSlideIndex(targetIndex);
          }
          openIssuePanelForSlide(slideId);
        }}
        fixPreviewBySlideId={fixPreviewBySlideId}
        selectedFixPreviewSlideIds={selectedFixPreviewSlideIds}
        waitingFixReview={waitingFixReview}
        previewingFix={previewingFix}
        applyingFix={applyingFix}
        skippingFix={skippingFix}
        onGeneratePreview={(slideId) => {
          void handlePreviewFix([slideId]);
        }}
        onToggleApplySlide={toggleFixPreviewSelection}
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

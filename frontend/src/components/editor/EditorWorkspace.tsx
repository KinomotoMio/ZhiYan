"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { useAppStore } from "@/lib/store";
import {
  acceptOutline,
  cancelJob,
  exportPdf,
  exportPptx,
  fixApply,
  fixPreview,
  fixSkip,
} from "@/lib/api";
import { getExportSuccessMessage } from "@/lib/export-feedback";
import { collectIssueSlideIds, groupIssuesBySlide } from "@/lib/verification-issues";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { canResumeGenerationJob } from "@/lib/routes";
import { resumeGenerationJob } from "@/components/editor/resume-job";
import SlidePreview from "@/components/slides/SlidePreview";
import SlideThumbnail from "@/components/slides/SlideThumbnail";
import SpeakerNotes from "@/components/slides/SpeakerNotes";
import RevealPreview from "@/components/slides/RevealPreview";
import FloatingChatPanel from "@/components/chat/FloatingChatPanel";
import UserMenu from "@/components/settings/UserMenu";
import IssueReviewDrawer from "@/components/editor/IssueReviewDrawer";
import SessionTitleInlineEditor from "@/components/session/SessionTitleInlineEditor";

interface EditorWorkspaceProps {
  returnHref: string;
  returnLabel?: string;
  sessionTitle: string;
  onRenameSessionTitle: (nextTitle: string) => Promise<void>;
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
  } = useAppStore();
  const [showReveal, setShowReveal] = useState(false);
  const [revealSlideIndex, setRevealSlideIndex] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [previewingFix, setPreviewingFix] = useState(false);
  const [applyingFix, setApplyingFix] = useState(false);
  const [skippingFix, setSkippingFix] = useState(false);
  const [acceptingOutline, setAcceptingOutline] = useState(false);

  const canResume = canResumeGenerationJob(jobId, jobStatus);
  const waitingOutlineReview = jobStatus === "waiting_outline_review";

  const handleResume = async () => {
    if (!jobId || resuming) return;
    setResuming(true);
    try {
      const resumed = await resumeGenerationJob(jobId);
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
      await cancelJob(jobId);
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
      const result = await acceptOutline(jobId);
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

  const handlePreviewFix = async (targetSlideIds?: string[]) => {
    if (!jobId || previewingFix || applyingFix || skippingFix) return;
    setPreviewingFix(true);
    try {
      const job = await fixPreview(
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
      const job = await fixApply(jobId, selectedFixPreviewSlideIds);
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
      const job = await fixSkip(jobId);
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
  const layerOrder: Record<string, number> = { content: 1, assets: 2, verify: 3 };
  const loadedCount = slides.filter(
    (s) => !(s.contentData as Record<string, unknown> | undefined)?._loading
  ).length;
  const totalCount = slides.length;
  const genPct = totalCount > 0 ? Math.round((loadedCount / totalCount) * 100) : 0;
  const contentReadyCount = slides.filter((slide) => {
    const data = (slide.contentData ?? {}) as Record<string, unknown>;
    if (data._loading) return false;
    const layer = typeof data._readyLayer === "string" ? data._readyLayer : "content";
    return (layerOrder[layer] ?? 1) >= 1;
  }).length;
  const assetsReadyCount = slides.filter((slide) => {
    const data = (slide.contentData ?? {}) as Record<string, unknown>;
    if (data._loading) return false;
    const layer = typeof data._readyLayer === "string" ? data._readyLayer : "content";
    return (layerOrder[layer] ?? 1) >= 2;
  }).length;
  const verifyReadyCount = slides.filter((slide) => {
    const data = (slide.contentData ?? {}) as Record<string, unknown>;
    if (data._loading) return false;
    const layer = typeof data._readyLayer === "string" ? data._readyLayer : "content";
    return (layerOrder[layer] ?? 1) >= 3;
  }).length;
  const waitingFixReview = jobStatus === "waiting_fix_review";
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
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-slate-500 dark:text-slate-400">尚未生成演示文稿</p>
          {canResume && (
            <button
              onClick={() => {
                void handleResume();
              }}
              disabled={resuming}
              className="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:-translate-y-0.5 hover:shadow-lg disabled:opacity-60 transition-all duration-200 inline-flex items-center gap-2"
            >
              {resuming && <Loader2 className="h-4 w-4 animate-spin" />}
              {resuming ? "继续中..." : "继续任务"}
            </button>
          )}
          <button
            onClick={() => router.push(returnHref)}
            className="px-4 py-2 bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 rounded-lg hover:-translate-y-0.5 hover:shadow-lg transition-all duration-200"
          >
            返回创建
          </button>
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
    if (!presentation || exporting) return;
    setExporting(true);

    try {
      const exportResult =
        format === "pptx"
          ? await exportPptx(presentation)
          : { blob: await exportPdf(presentation), mode: "structured" as const };
      const { blob, mode } = exportResult;

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${presentation.title.slice(0, 30)}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success(getExportSuccessMessage(format, mode));
    } catch (err) {
      console.error("导出失败:", err);
      toast.error(`导出失败: ${err instanceof Error ? err.message : "未知错误"}`);
    } finally {
      setExporting(false);
    }
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
        <RevealPreview
          presentation={presentation}
          startSlide={currentSlideIndex}
          onSlideChange={setRevealSlideIndex}
        />
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col">
      {isGenerating && (
        <div className="shrink-0">
          <Progress value={genPct} className="h-1 rounded-none" />
        </div>
      )}

      <header className="h-12 border-b border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push(returnHref)}
            className="text-sm text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 transition-colors"
          >
            &larr; {returnLabel}
          </button>
          <SessionTitleInlineEditor
            title={sessionTitle}
            onSave={onRenameSessionTitle}
            className="min-w-0"
          />
          {isGenerating && (
            <span className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              生成中 · 内容 {contentReadyCount}/{totalCount} · 资源 {assetsReadyCount}/{totalCount} · 验证 {verifyReadyCount}/{totalCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <UserMenu compact />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                disabled={exporting || isGenerating}
                className="flex items-center gap-1.5 px-3 py-1 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white/70 dark:bg-slate-800/70 hover:shadow-sm focus-visible:ring-2 focus-visible:ring-cyan-500/60 disabled:opacity-50 transition-all duration-200"
              >
                {exporting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
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
          {canResume && (
            <button
              onClick={() => {
                void handleResume();
              }}
              disabled={resuming || isGenerating}
              className="px-3 py-1 text-sm rounded-lg border border-cyan-300 bg-cyan-50 text-cyan-700 hover:-translate-y-0.5 hover:shadow-lg disabled:opacity-50 transition-all duration-200 inline-flex items-center gap-1.5"
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
              className="px-3 py-1 text-sm rounded-lg border border-emerald-300 bg-emerald-50 text-emerald-700 hover:-translate-y-0.5 hover:shadow-lg disabled:opacity-50 transition-all duration-200 inline-flex items-center gap-1.5"
            >
              {acceptingOutline && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {acceptingOutline ? "确认中..." : "确认大纲并继续"}
            </button>
          )}
          {isGenerating && (
            <button
              onClick={() => {
                void handleCancelGeneration();
              }}
              className="px-3 py-1 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white/70 dark:bg-slate-800/70 hover:shadow-sm transition-all duration-200"
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
              className="px-3 py-1 text-sm rounded-lg border border-amber-300 bg-amber-50 text-amber-700 hover:shadow-sm transition-all duration-200"
            >
              校验问题（{totalIssueCount}）
            </button>
          )}
          <button
            onClick={() => {
              setRevealSlideIndex(currentSlideIndex);
              setShowReveal(true);
            }}
            disabled={isGenerating}
            className="px-3 py-1 text-sm bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 rounded-lg hover:-translate-y-0.5 hover:shadow-lg focus-visible:ring-2 focus-visible:ring-cyan-500/70 disabled:opacity-50 transition-all duration-200"
          >
            演示
          </button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <aside className="w-48 border-r border-slate-200 dark:border-slate-700 bg-slate-50/40 dark:bg-slate-900/40 overflow-y-auto p-3 space-y-2 shrink-0">
          {presentation.slides.map((slide, i) => (
            <SlideThumbnail
              key={slide.slideId}
              slide={slide}
              index={i}
              isActive={i === currentSlideIndex}
              onClick={() => setCurrentSlideIndex(i)}
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
          ))}
        </aside>

        <main className="flex-1 flex flex-col overflow-hidden">
          <div className="flex-1 flex items-center justify-center p-6 bg-slate-50/30 dark:bg-slate-900/30">
            <div className="w-full max-w-4xl">
              <SlidePreview slide={currentSlide} className="shadow-xl" />
            </div>
          </div>
          <SpeakerNotes notes={currentSlide?.speakerNotes} />
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

      <FloatingChatPanel />
    </div>
  );
}

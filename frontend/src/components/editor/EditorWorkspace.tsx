"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { useAppStore } from "@/lib/store";
import { cancelJob, exportPptx, exportPdf } from "@/lib/api";
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

interface EditorWorkspaceProps {
  returnHref: string;
  returnLabel?: string;
}

export default function EditorWorkspace({
  returnHref,
  returnLabel = "返回",
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
  } = useAppStore();
  const [showReveal, setShowReveal] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [resuming, setResuming] = useState(false);

  const canResume = canResumeGenerationJob(jobId, jobStatus);

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

  const slides = presentation.slides ?? [];
  const currentSlide = presentation.slides[currentSlideIndex];
  const loadedCount = slides.filter(
    (s) => !(s.contentData as Record<string, unknown> | undefined)?._loading
  ).length;
  const totalCount = slides.length;
  const genPct = totalCount > 0 ? Math.round((loadedCount / totalCount) * 100) : 0;

  const handleExport = async (format: "pptx" | "pdf") => {
    if (!presentation || exporting) return;
    setExporting(true);

    try {
      const blob =
        format === "pptx"
          ? await exportPptx(presentation)
          : await exportPdf(presentation);

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${presentation.title.slice(0, 30)}.${format}`;
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

  if (showReveal) {
    return (
      <div className="fixed inset-0 z-50 bg-black">
        <button
          onClick={() => setShowReveal(false)}
          className="absolute top-4 right-4 z-50 px-3 py-1 bg-white/20 text-white rounded-md text-sm hover:bg-white/30"
        >
          退出演示
        </button>
        <RevealPreview
          presentation={presentation}
          startSlide={currentSlideIndex}
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
          <span className="font-medium text-sm">{presentation.title}</span>
          {isGenerating && (
            <span className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              生成中 ({loadedCount}/{totalCount})
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
          <button
            onClick={() => setShowReveal(true)}
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

      <FloatingChatPanel />
    </div>
  );
}

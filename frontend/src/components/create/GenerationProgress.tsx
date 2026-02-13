"use client";

import { Loader2 } from "lucide-react";
import { Progress } from "@/components/ui/progress";

interface GenerationProgressProps {
  progress: {
    stage: string | null;
    step: number;
    totalSteps: number;
    message: string;
    readySlides: number;
    totalSlides: number;
    error: string | null;
  } | null;
  jobStatus: string | null;
  currentStage: string | null;
  failedSlideIndices: number[];
  issues: Array<Record<string, unknown>>;
  onCancel: () => void;
  onRetry?: () => void;
}

export default function GenerationProgress({
  progress,
  jobStatus,
  currentStage,
  failedSlideIndices,
  issues,
  onCancel,
  onRetry,
}: GenerationProgressProps) {
  const stageMap: Record<string, string> = {
    parse: "解析文档",
    outline: "生成大纲",
    layout: "匹配布局",
    slides: "生成页面",
    assets: "处理资源",
    verify: "质量验证",
    fix: "自动修复",
    complete: "完成",
  };

  const stageLabel = currentStage ? (stageMap[currentStage] ?? currentStage) : "准备中";
  const stagePct =
    progress && progress.totalSteps > 0
      ? Math.round((progress.step / progress.totalSteps) * 100)
      : 0;
  const slidePct =
    progress && progress.totalSlides > 0
      ? Math.round((progress.readySlides / progress.totalSlides) * 100)
      : 0;
  const pct = Math.max(stagePct, slidePct);

  const errorCount = issues.filter((issue) => issue.severity === "error").length;
  const canRetry = jobStatus === "failed" || jobStatus === "cancelled";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="w-full max-w-md space-y-4 rounded-xl border bg-background p-6 shadow-lg">
        <div className="flex items-center gap-3">
          <Loader2 className="h-5 w-5 animate-spin text-primary" />
          <span className="text-sm font-medium">AI 正在生成演示文稿</span>
        </div>
        <Progress value={pct} className="h-2" />
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{progress?.message || "准备中..."}</span>
          <span>{stageLabel}</span>
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>
            {progress
              ? `阶段 ${progress.step}/${progress.totalSteps}`
              : "阶段 0/0"}
          </span>
          <span>
            {progress
              ? `页面 ${progress.readySlides}/${progress.totalSlides}`
              : "页面 0/0"}
          </span>
        </div>
        {(progress?.error || failedSlideIndices.length > 0 || errorCount > 0) && (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-700">
            {progress?.error || "存在失败页或验证问题"}
            {(failedSlideIndices.length > 0 || errorCount > 0) && (
              <div className="mt-1">
                失败页: {failedSlideIndices.length}，error 级问题: {errorCount}
              </div>
            )}
          </div>
        )}
        <button
          type="button"
          onClick={onCancel}
          className="w-full py-2 text-sm border rounded-md hover:bg-muted transition-colors"
        >
          取消生成
        </button>
        {canRetry && onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="w-full py-2 text-sm border rounded-md hover:bg-muted transition-colors"
          >
            重试生成
          </button>
        )}
      </div>
    </div>
  );
}

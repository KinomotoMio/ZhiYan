"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import type { GenerationErrorCode } from "@/lib/api";

interface GenerationProgressProps {
  progress: {
    stage: string | null;
    step: number;
    totalSteps: number;
    message: string;
    readySlides: number;
    totalSlides: number;
    error: string | null;
    errorCode: GenerationErrorCode | null;
    timeoutSeconds: number | null;
  } | null;
  jobStatus: string | null;
  currentStage: string | null;
  lastEventAt: number | null;
  connectionStale: boolean;
  slowStageWarning: boolean;
  failedSlideIndices: number[];
  issues: Array<Record<string, unknown>>;
  onCancel: () => void;
  onRetry?: () => void;
}

function resolveErrorMessage(
  errorCode: GenerationErrorCode | null,
  fallback: string | null,
  timeoutSeconds: number | null
): string | null {
  if (errorCode === "STAGE_TIMEOUT") {
    return `大纲生成超时（${Math.round(timeoutSeconds ?? 90)}秒）`;
  }
  if (errorCode === "PROVIDER_NETWORK") {
    return "网络或供应商连接异常";
  }
  if (errorCode === "PROVIDER_TIMEOUT") {
    return "模型响应超时";
  }
  if (errorCode === "PROVIDER_RATE_LIMIT") {
    return "请求频率受限，请稍后重试";
  }
  if (errorCode === "CANCELLED") {
    return "任务已取消";
  }
  return fallback;
}

export default function GenerationProgress({
  progress,
  jobStatus,
  currentStage,
  lastEventAt,
  connectionStale,
  slowStageWarning,
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
    agent_generate_artifact: "生成原始产物",
    artifact_validate: "校验原始产物",
    artifact_render: "构建预览",
    artifact_publish: "保存产物",
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
  const [nowTs, setNowTs] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNowTs(Date.now());
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const secondsSinceLastEvent =
    typeof lastEventAt === "number" ? Math.max(0, Math.floor((nowTs - lastEventAt) / 1000)) : null;
  const resolvedError = resolveErrorMessage(
    progress?.errorCode ?? null,
    progress?.error ?? null,
    progress?.timeoutSeconds ?? null
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-white/60 dark:bg-slate-900/60 backdrop-blur-xl">
      <div className="w-full max-w-md space-y-4 rounded-2xl border border-white/60 dark:border-slate-700 bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl p-6 shadow-[0_20px_60px_-40px_rgba(15,23,42,0.35)]">
        <div className="flex items-center gap-3">
          <Loader2 className="h-5 w-5 animate-spin text-cyan-600" />
          <span className="text-sm font-medium">AI 正在生成演示文稿</span>
        </div>
        <Progress value={pct} className="h-2" />
        <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
          <span>{progress?.message || "准备中..."}</span>
          <span>{stageLabel}</span>
        </div>
        <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
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
        <div className="rounded-md border border-slate-200 dark:border-slate-700 bg-white/60 dark:bg-slate-800/60 px-3 py-2 text-xs text-slate-500 dark:text-slate-400">
          <div className="flex items-center justify-between">
            <span>连接状态</span>
            <span className={connectionStale ? "text-amber-600" : "text-emerald-600"}>
              {connectionStale ? "可能中断" : "活跃"}
            </span>
          </div>
          <div className="mt-1 flex items-center justify-between">
            <span>最近事件</span>
            <span>{secondsSinceLastEvent === null ? "--" : `${secondsSinceLastEvent} 秒前`}</span>
          </div>
        </div>
        {slowStageWarning && jobStatus === "running" && (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-700">
            模型响应较慢，可取消后重试
          </div>
        )}
        {(resolvedError || failedSlideIndices.length > 0 || errorCount > 0) && (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-700">
            {resolvedError || "存在失败页或验证问题"}
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
          className="w-full py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white/70 dark:bg-slate-800/70 hover:shadow-sm transition-all duration-200"
        >
          取消生成
        </button>
        {canRetry && onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="w-full py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white/70 dark:bg-slate-800/70 hover:shadow-sm transition-all duration-200"
          >
            重试生成
          </button>
        )}
      </div>
    </div>
  );
}

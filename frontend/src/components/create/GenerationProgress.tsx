"use client";

import { Loader2 } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import type { ProgressEvent } from "@/lib/api";

interface GenerationProgressProps {
  progress: ProgressEvent | null;
  onCancel: () => void;
}

export default function GenerationProgress({
  progress,
  onCancel,
}: GenerationProgressProps) {
  const pct = progress
    ? Math.round((progress.step / progress.total_steps) * 100)
    : 0;

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
          <span>
            {progress
              ? `${progress.step} / ${progress.total_steps}`
              : ""}
          </span>
        </div>
        <button
          type="button"
          onClick={onCancel}
          className="w-full py-2 text-sm border rounded-md hover:bg-muted transition-colors"
        >
          取消生成
        </button>
      </div>
    </div>
  );
}

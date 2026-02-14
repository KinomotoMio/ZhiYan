"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { useAppStore } from "@/lib/store";
import {
  acceptOutline,
  cancelJob,
  createJob,
  runJob,
  subscribeJobEvents,
  type GenerationErrorCode,
  type GenerationEvent,
} from "@/lib/api";
import { canShowContinueEditorEntry, getSessionEditorPath } from "@/lib/routes";
import type { Presentation, Slide } from "@/types/slide";
import TemplateSelector from "./TemplateSelector";
import GenerationProgress from "./GenerationProgress";
import { useSettingsStatus } from "@/hooks/useSettingsStatus";

const EXAMPLE_PROMPTS = [
  {
    icon: "\u{1F4CA}",
    text: "设计一个针对寻求融资的初创公司提案演示文稿",
  },
  {
    icon: "\u{1F393}",
    text: "准备一个关于人工智能对未来工作影响的演示文稿",
  },
  {
    icon: "\u{1F512}",
    text: "准备一个关于网络安全最佳实践的培训模块",
  },
  {
    icon: "\u{1F4BC}",
    text: "创建一个关于 B2B 软件解决方案的销售演示文稿",
  },
];

const CONNECTION_STALE_THRESHOLD_MS = 25_000;
const SLOW_STAGE_THRESHOLD_MS = 45_000;
const WATCHDOG_INTERVAL_MS = 5_000;

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

export default function CreateForm() {
  const router = useRouter();
  const {
    workspaceSources,
    selectedSourceIds,
    topic,
    setTopic,
    selectedTemplateId,
    numPages,
    currentSessionId,
    setCurrentSessionId,
    sessions,
    isGenerating,
    setIsGenerating,
    setPresentation,
    initSkeletonPresentation,
    updateSlideAtIndex,
    finishGeneration: storeFinishGeneration,
    updateJobState,
    resetJobState,
    jobId,
    jobStatus,
    currentStage,
    issues,
    failedSlideIndices,
  } = useAppStore();

  const currentSessionHasPresentation =
    sessions.find((s) => s.id === currentSessionId)?.has_presentation ?? false;
  const [progress, setProgress] = useState<{
    stage: string | null;
    step: number;
    totalSteps: number;
    message: string;
    readySlides: number;
    totalSlides: number;
    error: string | null;
    errorCode: GenerationErrorCode | null;
    timeoutSeconds: number | null;
  } | null>(null);
  const [lastEventAt, setLastEventAt] = useState<number | null>(null);
  const [lastProgressAt, setLastProgressAt] = useState<number | null>(null);
  const [connectionStale, setConnectionStale] = useState(false);
  const [slowStageWarning, setSlowStageWarning] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const navigatedRef = useRef(false);
  const cancellingRef = useRef(false);
  const { status: settingsStatus, message: settingsMessage } = useSettingsStatus();

  const readySources = workspaceSources.filter((s) => s.status === "ready");
  const selectedReadySources = readySources.filter((s) =>
    selectedSourceIds.includes(s.id)
  );
  const hasUploadingOrParsing = workspaceSources.some(
    (s) => s.status === "uploading" || s.status === "parsing"
  );
  const canGenerate =
    (selectedReadySources.length > 0 || topic.trim().length > 0) &&
    !hasUploadingOrParsing;

  const cleanupGeneration = () => {
    setIsGenerating(false);
    abortRef.current = null;
    cancellingRef.current = false;
    setConnectionStale(false);
    setSlowStageWarning(false);
  };

  useEffect(() => {
    if (!isGenerating || jobStatus !== "running") {
      return;
    }
    const timer = window.setInterval(() => {
      const now = Date.now();
      const stale =
        typeof lastEventAt === "number" &&
        now - lastEventAt > CONNECTION_STALE_THRESHOLD_MS;
      const slow =
        typeof lastProgressAt === "number" &&
        !!currentStage &&
        now - lastProgressAt > SLOW_STAGE_THRESHOLD_MS;
      setConnectionStale(stale);
      setSlowStageWarning(slow);
    }, WATCHDOG_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [currentStage, isGenerating, jobStatus, lastEventAt, lastProgressAt]);

  const updateFromEvent = (
    evt: GenerationEvent,
    currentJobId: string,
    targetSessionId: string | null
  ) => {
    if (evt.stage) {
      updateJobState({
        jobId: currentJobId,
        jobStatus: "running",
        currentStage: evt.stage,
      });
    }

    if (evt.type === "stage_progress" || evt.type === "stage_started") {
      if (evt.type === "stage_progress") {
        setLastProgressAt(Date.now());
        setSlowStageWarning(false);
      }
      setProgress((prev) => ({
        stage: evt.stage ?? prev?.stage ?? null,
        step:
          typeof evt.payload.step === "number"
            ? evt.payload.step
            : prev?.step ?? 0,
        totalSteps:
          typeof evt.payload.total_steps === "number"
            ? evt.payload.total_steps
            : prev?.totalSteps ?? 7,
        message: evt.message || prev?.message || "处理中...",
        readySlides: prev?.readySlides ?? 0,
        totalSlides: prev?.totalSlides ?? numPages,
        error: prev?.error ?? null,
        errorCode: prev?.errorCode ?? null,
        timeoutSeconds: prev?.timeoutSeconds ?? null,
      }));
      return;
    }

    if (evt.type === "layout_ready") {
      setLastProgressAt(Date.now());
      setSlowStageWarning(false);
      setProgress((prev) => ({
        stage: "layout",
        step: prev?.step ?? 3,
        totalSteps: prev?.totalSteps ?? 7,
        message: evt.message || "布局已就绪",
        readySlides: prev?.readySlides ?? 0,
        totalSlides: prev?.totalSlides ?? numPages,
        error: prev?.error ?? null,
        errorCode: prev?.errorCode ?? null,
        timeoutSeconds: prev?.timeoutSeconds ?? null,
      }));
      return;
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
            suggested_layout_category: String(obj.suggested_layout_category ?? "bullets"),
          };
        })
        .filter((item) => item.slide_number > 0);
      const title = typeof payload.topic === "string" ? payload.topic : topic || "新演示文稿";

      if (items.length > 0) {
        setLastProgressAt(Date.now());
        setSlowStageWarning(false);
        initSkeletonPresentation(title, items);
        setProgress((prev) => ({
          stage: "outline",
          step: 2,
          totalSteps: prev?.totalSteps ?? 7,
          message: evt.message || "大纲已生成",
          readySlides: 0,
          totalSlides: items.length,
          error: null,
          errorCode: null,
          timeoutSeconds: null,
        }));
        if (!navigatedRef.current) {
          navigatedRef.current = true;
          if (targetSessionId) {
            router.push(getSessionEditorPath(targetSessionId));
          } else {
            router.push("/editor");
          }
        }
      }

      if (payload.requires_accept === true) {
        void (async () => {
          try {
            await acceptOutline(currentJobId);
            await runJob(currentJobId);
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
      if (index >= 0 && slide) {
        setLastProgressAt(Date.now());
        setSlowStageWarning(false);
        updateSlideAtIndex(index, slide);
        setProgress((prev) => ({
          stage: "slides",
          step: prev?.step ?? 4,
          totalSteps: prev?.totalSteps ?? 7,
          message: evt.message || `第 ${index + 1} 页已生成`,
          readySlides: Math.max(prev?.readySlides ?? 0, index + 1),
          totalSlides: prev?.totalSlides ?? numPages,
          error: prev?.error ?? null,
          errorCode: prev?.errorCode ?? null,
          timeoutSeconds: prev?.timeoutSeconds ?? null,
        }));
      }
      return;
    }

    if (evt.type === "stage_failed") {
      const payload = evt.payload as Record<string, unknown>;
      const errorCode = asErrorCode(payload.error_code);
      const timeoutSeconds =
        typeof payload.timeout_seconds === "number" ? payload.timeout_seconds : null;
      const message =
        typeof payload.error_message === "string"
          ? payload.error_message
          : typeof payload.error === "string"
            ? payload.error
          : evt.message || "阶段失败";
      setProgress((prev) => ({
        stage: evt.stage ?? prev?.stage ?? null,
        step: prev?.step ?? 0,
        totalSteps: prev?.totalSteps ?? 7,
        message: prev?.message ?? "处理中...",
        readySlides: prev?.readySlides ?? 0,
        totalSlides: prev?.totalSlides ?? numPages,
        error: message,
        errorCode,
        timeoutSeconds,
      }));
      return;
    }

    if (evt.type === "job_completed") {
      const payload = evt.payload as Record<string, unknown>;
      const presentation = payload.presentation as Presentation | undefined;
      if (presentation) {
        setPresentation(presentation);
      }
      updateJobState({
        jobId: currentJobId,
        jobStatus: "completed",
        currentStage: "complete",
        issues: Array.isArray(payload.issues)
          ? (payload.issues as Array<Record<string, unknown>>)
          : [],
        failedSlideIndices: Array.isArray(payload.failed_slide_indices)
          ? (payload.failed_slide_indices as number[])
          : [],
      });
      storeFinishGeneration();
      return;
    }

    if (evt.type === "job_failed") {
      const payload = evt.payload as Record<string, unknown>;
      const errorCode = asErrorCode(payload.error_code);
      const timeoutSeconds =
        typeof payload.timeout_seconds === "number" ? payload.timeout_seconds : null;
      const message =
        typeof payload.error_message === "string"
          ? payload.error_message
          : typeof payload.error === "string"
            ? payload.error
          : evt.message || "任务失败";
      updateJobState({
        jobId: currentJobId,
        jobStatus: "failed",
        currentStage: null,
      });
      setProgress((prev) => ({
        stage: prev?.stage ?? null,
        step: prev?.step ?? 0,
        totalSteps: prev?.totalSteps ?? 7,
        message: prev?.message ?? "处理中...",
        readySlides: prev?.readySlides ?? 0,
        totalSlides: prev?.totalSlides ?? numPages,
        error: message,
        errorCode,
        timeoutSeconds,
      }));
      toast.error(message);
      storeFinishGeneration();
      return;
    }

    if (evt.type === "job_cancelled") {
      updateJobState({
        jobId: currentJobId,
        jobStatus: "cancelled",
        currentStage: null,
      });
      if (!cancellingRef.current) {
        toast.info("任务已取消");
      }
      storeFinishGeneration();
    }
  };

  const handleGenerate = async () => {
    if (!canGenerate) return;
    resetJobState();
    setIsGenerating(true);
    setProgress({
      stage: null,
      step: 0,
      totalSteps: 7,
      message: "创建任务中...",
      readySlides: 0,
      totalSlides: numPages,
      error: null,
      errorCode: null,
      timeoutSeconds: null,
    });
    const now = Date.now();
    setLastEventAt(now);
    setLastProgressAt(now);
    setConnectionStale(false);
    setSlowStageWarning(false);
    navigatedRef.current = false;

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const created = await createJob({
        content: "",
        topic,
        session_id: currentSessionId ?? undefined,
        source_ids: selectedReadySources.map((s) => s.id),
        template_id: selectedTemplateId,
        num_pages: numPages,
        mode: "auto",
      });
      if (created.session_id) {
        setCurrentSessionId(created.session_id);
      }
      const eventSessionId =
        created.session_id ?? currentSessionId ?? useAppStore.getState().currentSessionId;

      updateJobState({
        jobId: created.job_id,
        jobStatus: created.status,
        currentStage: null,
        issues: [],
        failedSlideIndices: [],
      });

      await subscribeJobEvents(
        created.job_id,
        {
          onEvent: (evt) => {
            setLastEventAt(Date.now());
            setConnectionStale(false);
            updateFromEvent(evt, created.job_id, eventSessionId);
          },
          onError: (err) => {
            console.error("生成失败:", err);
            toast.error(err.message || "生成失败，请稍后重试");
            updateJobState({
              jobId: created.job_id,
              jobStatus: "failed",
              currentStage: null,
            });
            storeFinishGeneration();
          },
          onDone: () => {
            cleanupGeneration();
          },
        },
        controller.signal
      );
    } catch (err) {
      console.error("创建任务失败:", err);
      toast.error(err instanceof Error ? err.message : "创建任务失败");
      updateJobState({ jobStatus: "failed", currentStage: null });
      storeFinishGeneration();
      cleanupGeneration();
    }
  };

  const handleCancel = async () => {
    cancellingRef.current = true;
    const currentJobId = jobId;
    if (currentJobId) {
      try {
        await cancelJob(currentJobId);
      } catch (err) {
        console.warn("取消任务失败:", err);
      }
    }
    abortRef.current?.abort();
    storeFinishGeneration();
    cleanupGeneration();
    updateJobState({ jobStatus: "cancelled", currentStage: null });
    toast.info("已取消生成");
  };

  return (
    <>
      {isGenerating && (
        <GenerationProgress
          progress={progress}
          jobStatus={jobStatus}
          currentStage={currentStage}
          lastEventAt={lastEventAt}
          connectionStale={connectionStale}
          slowStageWarning={slowStageWarning}
          failedSlideIndices={failedSlideIndices}
          issues={issues}
          onCancel={() => {
            void handleCancel();
          }}
          onRetry={() => {
            void handleGenerate();
          }}
        />
      )}
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="w-full max-w-xl space-y-8">
          {/* 标题 */}
          <div className="text-center space-y-2">
            <h1 className="text-4xl font-bold tracking-tight">知演 ZhiYan</h1>
            <p className="text-muted-foreground text-lg">
              知识变演示，更懂演示的 AI PPT 智能体
            </p>
          </div>

          <div className="space-y-5">
            {/* 主题描述 */}
            <div className="space-y-2">
              <label className="text-sm font-medium">主题描述</label>
              <textarea
                className="w-full h-28 p-4 border border-input rounded-lg bg-background text-foreground resize-none focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="描述演示文稿的主题和重点（可选，也可以只通过左侧来源生成）"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
              />

              {/* 示例提示词 */}
              {!topic.trim() && (
                <div className="grid grid-cols-2 gap-2">
                  {EXAMPLE_PROMPTS.map((p) => (
                    <button
                      key={p.text}
                      onClick={() => setTopic(p.text)}
                      className="flex items-start gap-2 rounded-lg border border-input p-3 text-left text-xs leading-relaxed text-muted-foreground transition-colors hover:border-primary/50 hover:bg-accent/50 hover:text-foreground"
                    >
                      <span className="text-sm shrink-0">{p.icon}</span>
                      <span>{p.text}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* 模板选择（含内联页数） */}
            <TemplateSelector />

            {/* 生成按钮 */}
            <div className="space-y-2">
              <button
                onClick={() => {
                  void handleGenerate();
                }}
                disabled={!canGenerate || isGenerating}
                className="w-full py-3 rounded-lg bg-primary text-primary-foreground font-medium text-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
              >
                {isGenerating && <Loader2 className="h-5 w-5 animate-spin" />}
                {isGenerating ? "AI 正在生成..." : "开始生成"}
              </button>
              {canShowContinueEditorEntry(currentSessionId, isGenerating, currentSessionHasPresentation) && (
                <button
                  onClick={() => {
                    if (!currentSessionId) return;
                    router.push(getSessionEditorPath(currentSessionId));
                  }}
                  className="w-full py-2 rounded-lg border border-input text-sm font-medium hover:bg-accent transition-colors"
                >
                  继续编辑当前结果
                </button>
              )}

              {/* 状态提示 */}
              {settingsStatus === "unconfigured" ? (
                <p className="text-center text-xs text-amber-600 dark:text-amber-400">
                  {settingsMessage || "默认模型未就绪，请先在左下角设置中调整模型/API 信息"}
                </p>
              ) : (
                <p className="text-center text-xs text-muted-foreground">
                  {hasUploadingOrParsing
                    ? "等待来源解析完成..."
                    : selectedReadySources.length > 0
                      ? `将基于 ${selectedReadySources.length} 个已选来源生成`
                      : topic.trim()
                        ? "将基于主题描述生成"
                        : "请添加来源或描述主题"}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

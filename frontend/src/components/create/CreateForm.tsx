"use client";

import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { useAppStore } from "@/lib/store";
import { createJob } from "@/lib/api";
import {
  canShowContinueEditorEntry,
  getSessionEditorPath,
  resolvePostCreateEditorPath,
} from "@/lib/routes";
import TemplateSelector from "./TemplateSelector";
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
    initGenerationShell,
    updateJobState,
    resetJobState,
  } = useAppStore();

  const currentSessionHasPresentation =
    sessions.find((s) => s.id === currentSessionId)?.has_presentation ?? false;
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

  const handleGenerate = async () => {
    if (!canGenerate) return;
    resetJobState();
    setIsGenerating(true);

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

      updateJobState({
        jobId: created.job_id,
        jobStatus: "running",
        currentStage: null,
        lastJobEventSeq: 0,
        issues: [],
        failedSlideIndices: [],
      });
      initGenerationShell(topic.trim() || "生成中...", numPages);

      const targetPath = resolvePostCreateEditorPath(
        created.session_id ?? null,
        currentSessionId,
        useAppStore.getState().currentSessionId
      );
      if (targetPath) {
        router.push(targetPath);
      }
    } catch (err) {
      console.error("创建任务失败:", err);
      toast.error(err instanceof Error ? err.message : "创建任务失败");
      updateJobState({ jobStatus: "failed", currentStage: null });
      setIsGenerating(false);
    }
  };

  return (
    <>
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="w-full max-w-xl space-y-8">
          <div className="text-center space-y-2">
            <h1 className="text-4xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">知演 ZhiYan</h1>
            <p className="text-slate-600 dark:text-slate-400 text-lg">
              知识变演示，更懂演示的 AI PPT 智能体
            </p>
          </div>

          <div className="space-y-5">
            <div className="space-y-2">
              <label className="text-sm font-medium">主题描述</label>
              <textarea
                className="w-full h-28 p-4 border border-slate-300 dark:border-slate-600 rounded-lg bg-white/80 dark:bg-slate-800/80 text-foreground resize-none focus:outline-none focus:ring-2 focus:ring-cyan-500/60"
                placeholder="描述演示文稿的主题和重点（可选，也可以只通过左侧来源生成）"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
              />

              {!topic.trim() && (
                <div className="grid grid-cols-2 gap-2">
                  {EXAMPLE_PROMPTS.map((p) => (
                    <button
                      key={p.text}
                      onClick={() => setTopic(p.text)}
                      className="flex items-start gap-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-800/80 p-3 text-left text-xs leading-relaxed text-slate-500 dark:text-slate-400 transition-all duration-200 hover:shadow-sm hover:-translate-y-0.5 hover:text-foreground"
                    >
                      <span className="text-sm shrink-0">{p.icon}</span>
                      <span>{p.text}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <TemplateSelector />

            <div className="space-y-2">
              <button
                onClick={() => {
                  void handleGenerate();
                }}
                disabled={!canGenerate || isGenerating}
                className="w-full py-3 rounded-lg bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 font-medium text-lg hover:-translate-y-0.5 hover:shadow-lg focus-visible:ring-2 focus-visible:ring-cyan-500/70 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 flex items-center justify-center gap-2"
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
                  className="w-full py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white/70 dark:bg-slate-800/70 text-sm font-medium hover:shadow-md hover:-translate-y-0.5 transition-all duration-200"
                >
                  继续编辑当前结果
                </button>
              )}

              {settingsStatus === "unconfigured" ? (
                <p className="text-center text-xs text-amber-600 dark:text-amber-400">
                  {settingsMessage || "默认模型未就绪，请先在左下角设置中调整模型/API 信息"}
                </p>
              ) : (
                <p className="text-center text-xs text-slate-500 dark:text-slate-400">
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

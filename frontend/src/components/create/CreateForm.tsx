"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { useAppStore } from "@/lib/store";
import { generatePresentationStream, type ProgressEvent, type OutlineReadyEvent } from "@/lib/api";
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

export default function CreateForm() {
  const router = useRouter();
  const {
    sources,
    selectedSourceIds,
    topic,
    setTopic,
    selectedTemplateId,
    numPages,
    isGenerating,
    setIsGenerating,
    setPresentation,
    initSkeletonPresentation,
    updateSlideAtIndex,
    finishGeneration: storeFinishGeneration,
  } = useAppStore();
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const { status: settingsStatus, message: settingsMessage } = useSettingsStatus();

  const readySources = sources.filter((s) => s.status === "ready");
  const selectedReadySources = readySources.filter((s) =>
    selectedSourceIds.includes(s.id)
  );
  const hasUploadingOrParsing = sources.some(
    (s) => s.status === "uploading" || s.status === "parsing"
  );
  const canGenerate =
    (selectedReadySources.length > 0 || topic.trim().length > 0) &&
    !hasUploadingOrParsing;

  const [navigated, setNavigated] = useState(false);

  const cleanupGeneration = () => {
    setIsGenerating(false);
    setProgress(null);
    abortRef.current = null;
  };

  const handleGenerate = () => {
    if (!canGenerate) return;
    setIsGenerating(true);
    setProgress(null);
    setNavigated(false);

    const controller = new AbortController();
    abortRef.current = controller;

    generatePresentationStream(
      {
        content: "",
        topic,
        source_ids: selectedReadySources.map((s) => s.id),
        template_id: selectedTemplateId,
        num_pages: numPages,
      },
      {
        onProgress: (evt) => setProgress(evt),
        onOutlineReady: (evt) => {
          // outline 完成 → 创建 skeleton slides → 跳转 editor
          initSkeletonPresentation(topic || evt.topic, evt.items);
          if (!navigated) {
            setNavigated(true);
            router.push("/editor");
          }
        },
        onSlideReady: (slide, index) => {
          updateSlideAtIndex(index, slide);
        },
        onResult: (evt) => {
          // 最终校对覆盖
          setPresentation(evt.presentation);
          storeFinishGeneration();
        },
        onError: (err) => {
          console.error("生成失败:", err);
          toast.error(err.message || "生成失败，请稍后重试");
        },
        onDone: () => {
          cleanupGeneration();
        },
      },
      controller.signal
    );
  };

  const handleCancel = () => {
    abortRef.current?.abort();
    storeFinishGeneration();
    cleanupGeneration();
    toast.info("已取消生成");
  };

  return (
    <>
      {isGenerating && (
        <GenerationProgress progress={progress} onCancel={handleCancel} />
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
                onClick={handleGenerate}
                disabled={!canGenerate || isGenerating}
                className="w-full py-3 rounded-lg bg-primary text-primary-foreground font-medium text-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
              >
                {isGenerating && <Loader2 className="h-5 w-5 animate-spin" />}
                {isGenerating ? "AI 正在生成..." : "开始生成"}
              </button>

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

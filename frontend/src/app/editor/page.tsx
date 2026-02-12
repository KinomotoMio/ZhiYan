"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { useAppStore } from "@/lib/store";
import { exportPptx, exportPdf } from "@/lib/api";
import SlidePreview from "@/components/slides/SlidePreview";
import SlideThumbnail from "@/components/slides/SlideThumbnail";
import SpeakerNotes from "@/components/slides/SpeakerNotes";
import RevealPreview from "@/components/slides/RevealPreview";
import FloatingChatPanel from "@/components/chat/FloatingChatPanel";

export default function EditorPage() {
  const router = useRouter();
  const { presentation, currentSlideIndex, setCurrentSlideIndex } =
    useAppStore();
  const [showReveal, setShowReveal] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const [exporting, setExporting] = useState(false);
  const exportMenuRef = useRef<HTMLDivElement>(null);

  // 点击外部关闭导出菜单
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target as Node)) {
        setShowExportMenu(false);
      }
    };
    if (showExportMenu) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showExportMenu]);

  if (!presentation) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-muted-foreground">尚未生成演示文稿</p>
          <button
            onClick={() => router.push("/")}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md"
          >
            返回创建
          </button>
        </div>
      </div>
    );
  }

  const currentSlide = presentation.slides[currentSlideIndex];

  const handleExport = async (format: "pptx" | "pdf") => {
    if (!presentation || exporting) return;
    setExporting(true);
    setShowExportMenu(false);

    try {
      const blob = format === "pptx"
        ? await exportPptx(presentation)
        : await exportPdf(presentation);

      // 触发下载
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

  // 全屏演示模式
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
      {/* 顶部栏 */}
      <header className="h-12 border-b flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/")}
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            &larr; 返回
          </button>
          <span className="font-medium text-sm">{presentation.title}</span>
        </div>
        <div className="flex items-center gap-2">
          {/* 导出下拉菜单 */}
          <div className="relative" ref={exportMenuRef}>
            <button
              onClick={() => setShowExportMenu(!showExportMenu)}
              disabled={exporting}
              className="flex items-center gap-1.5 px-3 py-1 text-sm border rounded-md hover:bg-muted disabled:opacity-50"
            >
              {exporting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {exporting ? "正在导出..." : "导出"}
            </button>
            {showExportMenu && (
              <div className="absolute right-0 top-full mt-1 w-40 border rounded-md bg-background shadow-lg z-10">
                <button
                  onClick={() => handleExport("pptx")}
                  className="w-full px-3 py-2 text-sm text-left hover:bg-muted"
                >
                  导出 PPTX
                </button>
                <button
                  onClick={() => handleExport("pdf")}
                  className="w-full px-3 py-2 text-sm text-left hover:bg-muted border-t"
                >
                  导出 PDF
                </button>
              </div>
            )}
          </div>
          <button
            onClick={() => setShowReveal(true)}
            className="px-3 py-1 text-sm bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
          >
            演示
          </button>
        </div>
      </header>

      {/* 主体区域 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 左侧缩略图 */}
        <aside className="w-48 border-r overflow-y-auto p-3 space-y-2 shrink-0">
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

        {/* 主预览区（全宽） */}
        <main className="flex-1 flex flex-col overflow-hidden">
          <div className="flex-1 flex items-center justify-center p-6 bg-muted/20">
            <div className="w-full max-w-4xl">
              <SlidePreview slide={currentSlide} className="shadow-xl" />
            </div>
          </div>
          <SpeakerNotes notes={currentSlide?.speakerNotes} />
        </main>
      </div>

      {/* 浮动 AI 助手面板 */}
      <FloatingChatPanel />
    </div>
  );
}

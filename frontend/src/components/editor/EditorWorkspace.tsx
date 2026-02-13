"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { useAppStore } from "@/lib/store";
import { exportPptx, exportPdf } from "@/lib/api";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
  const { presentation, currentSlideIndex, setCurrentSlideIndex, isGenerating } =
    useAppStore();
  const [showReveal, setShowReveal] = useState(false);
  const [exporting, setExporting] = useState(false);

  if (!presentation) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-muted-foreground">尚未生成演示文稿</p>
          <button
            onClick={() => router.push(returnHref)}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md"
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

      <header className="h-12 border-b flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push(returnHref)}
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            &larr; {returnLabel}
          </button>
          <span className="font-medium text-sm">{presentation.title}</span>
          {isGenerating && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
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
                className="flex items-center gap-1.5 px-3 py-1 text-sm border rounded-md hover:bg-muted disabled:opacity-50"
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
          <button
            onClick={() => setShowReveal(true)}
            disabled={isGenerating}
            className="px-3 py-1 text-sm bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50"
          >
            演示
          </button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
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

        <main className="flex-1 flex flex-col overflow-hidden">
          <div className="flex-1 flex items-center justify-center p-6 bg-muted/20">
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


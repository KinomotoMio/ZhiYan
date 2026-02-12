"use client";

import { useRef, useState } from "react";
import { Upload, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useAppStore } from "@/lib/store";
import { uploadTemplate } from "@/lib/api";
import { cn } from "@/lib/utils";

interface TemplateConfig {
  id: string;
  name: string;
  previewColors: { bg: string; accent: string; text: string; bar: string };
}

const TEMPLATES: TemplateConfig[] = [
  {
    id: "default",
    name: "默认模板",
    previewColors: {
      bg: "#ffffff",
      accent: "#3b82f6",
      text: "#e5e7eb",
      bar: "#3b82f6",
    },
  },
  {
    id: "hust",
    name: "华科官方",
    previewColors: {
      bg: "#ffffff",
      accent: "#c41e3a",
      text: "#dbeafe",
      bar: "#1e40af",
    },
  },
  {
    id: "dark",
    name: "暗色主题",
    previewColors: {
      bg: "#1e1e2e",
      accent: "#a78bfa",
      text: "#374151",
      bar: "#7c3aed",
    },
  },
];

function MiniPreview({ colors }: { colors: TemplateConfig["previewColors"] }) {
  return (
    <div
      className="aspect-[16/10] w-full rounded-sm overflow-hidden border border-border/50"
      style={{ backgroundColor: colors.bg }}
    >
      <div className="px-2 pt-2">
        <div
          className="h-1.5 w-3/5 rounded-full"
          style={{ backgroundColor: colors.accent }}
        />
      </div>
      <div className="flex gap-1.5 px-2 pt-1.5">
        <div className="flex-1 space-y-1">
          <div
            className="h-1 w-full rounded-full"
            style={{ backgroundColor: colors.text }}
          />
          <div
            className="h-1 w-4/5 rounded-full"
            style={{ backgroundColor: colors.text }}
          />
          <div
            className="h-1 w-3/5 rounded-full"
            style={{ backgroundColor: colors.text }}
          />
        </div>
        <div
          className="h-6 w-8 rounded-sm"
          style={{ backgroundColor: colors.bar }}
        />
      </div>
      <div className="px-2 pt-1.5">
        <div
          className="h-0.5 w-2/5 rounded-full opacity-40"
          style={{ backgroundColor: colors.accent }}
        />
      </div>
    </div>
  );
}

export default function TemplateSelector() {
  const { selectedTemplateId, setSelectedTemplateId, numPages, setNumPages } =
    useAppStore();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadedTemplates, setUploadedTemplates] = useState<TemplateConfig[]>([]);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.endsWith(".pptx")) {
      toast.error("仅支持 .pptx 格式");
      return;
    }

    setUploading(true);
    try {
      const result = await uploadTemplate(file);
      const newTemplate: TemplateConfig = {
        id: result.template_id,
        name: result.name,
        previewColors: {
          bg: "#f8fafc",
          accent: "#6366f1",
          text: "#cbd5e1",
          bar: "#6366f1",
        },
      };
      setUploadedTemplates((prev) => [...prev, newTemplate]);
      setSelectedTemplateId(result.template_id);
      toast.success(`模板「${result.name}」导入成功`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "模板导入失败");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const allTemplates = [...TEMPLATES, ...uploadedTemplates];

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium">选择模板</label>
        <div className="flex items-center gap-1.5">
          <label className="text-xs text-muted-foreground">页数</label>
          <select
            value={numPages}
            onChange={(e) => setNumPages(Number(e.target.value))}
            className="h-7 rounded-md border border-input bg-background px-2 text-xs"
          >
            {Array.from({ length: 12 - 3 + 1 }, (_, i) => i + 3).map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
            <option value={15}>15</option>
            <option value={20}>20</option>
            <option value={30}>30</option>
            <option value={50}>50</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2.5">
        {/* 导入模板入口 */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="flex flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed border-muted-foreground/30 p-2 transition-colors hover:border-primary/50 hover:bg-accent/30 disabled:opacity-50"
        >
          {uploading ? (
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          ) : (
            <Upload className="h-5 w-5 text-muted-foreground" />
          )}
          <span className="text-xs text-muted-foreground">
            {uploading ? "导入中..." : "导入模板"}
          </span>
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pptx"
          className="hidden"
          onChange={handleFileChange}
        />

        {/* 模板卡片 */}
        {allTemplates.map((t) => {
          const isSelected = selectedTemplateId === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setSelectedTemplateId(t.id)}
              className={cn(
                "flex flex-col gap-1.5 rounded-lg border p-2 text-left transition-all",
                isSelected
                  ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                  : "border-input hover:border-primary/50"
              )}
            >
              <MiniPreview colors={t.previewColors} />
              <span className="text-xs font-medium text-center w-full truncate">
                {t.name}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

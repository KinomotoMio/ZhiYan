"use client";

import { useState, useRef } from "react";
import { Volume2, Square, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { synthesizeSpeech } from "@/lib/api";

interface SpeakerNotesProps {
  value: string;
  onChange: (nextValue: string) => void;
  onSave?: () => void | Promise<void>;
  onGenerate?: () => void | Promise<void>;
  isSaving?: boolean;
  isGenerating?: boolean;
  canGenerate?: boolean;
  placeholder?: string;
}

export default function SpeakerNotes({
  value,
  onChange,
  onSave,
  onGenerate,
  isSaving = false,
  isGenerating = false,
  canGenerate = true,
  placeholder = "输入当前页的演讲提示，帮助演示时更顺畅地衔接内容。",
}: SpeakerNotesProps) {
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const hasNotes = value.trim().length > 0;

  const handlePlay = async () => {
    if (!hasNotes) return;

    if (playing) {
      audioRef.current?.pause();
      audioRef.current = null;
      abortRef.current?.abort();
      abortRef.current = null;
      setPlaying(false);
      return;
    }

    setLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const blob = await synthesizeSpeech(value, undefined, controller.signal);
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;

      audio.onended = () => {
        setPlaying(false);
        abortRef.current = null;
        URL.revokeObjectURL(url);
      };
      audio.onerror = () => {
        setPlaying(false);
        abortRef.current = null;
        URL.revokeObjectURL(url);
      };

      await audio.play();
      setPlaying(true);
    } catch (err) {
      abortRef.current = null;
      if (err instanceof DOMException && err.name === "AbortError") return;
      toast.error("语音合成失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex shrink-0 flex-col border-t border-white/70 bg-white/44">
      <div className="flex items-center justify-between gap-3 px-5 py-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
            Speaker Notes
          </p>
          <h3 className="mt-1 text-sm font-semibold text-slate-900">演讲者注解</h3>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              void onGenerate?.();
            }}
            disabled={!canGenerate || isGenerating}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white/88 px-3 text-xs font-medium text-slate-700 transition-all duration-200 hover:-translate-y-0.5 hover:bg-white hover:shadow-sm disabled:opacity-50"
            title="生成当前页演讲者注解"
          >
            {isGenerating ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="h-3.5 w-3.5" />
            )}
            {isGenerating ? "生成中..." : "生成"}
          </button>
          <button
            type="button"
            onClick={handlePlay}
            disabled={loading || !hasNotes}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white/88 text-slate-500 transition-all duration-200 hover:-translate-y-0.5 hover:bg-white hover:text-slate-800 hover:shadow-sm disabled:opacity-50"
            title={playing ? "停止朗读" : "朗读注解"}
          >
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : playing ? (
              <Square className="h-3.5 w-3.5" />
            ) : (
              <Volume2 className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>

      <div className="px-5 pb-5">
        <div className="overflow-hidden rounded-[22px] border border-white/85 bg-white/82 shadow-[0_20px_50px_-44px_rgba(15,23,42,0.4)]">
          <textarea
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onBlur={() => {
              void onSave?.();
            }}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                event.preventDefault();
                void onSave?.();
              }
            }}
            placeholder={placeholder}
            className="min-h-28 w-full resize-none bg-transparent px-4 py-3 text-sm leading-7 text-slate-700 outline-none placeholder:text-slate-400"
          />
        </div>

        <div className="mt-2 flex items-center justify-between gap-3 text-xs text-slate-500">
          <span>{isSaving ? "正在保存..." : "失焦自动保存，Cmd/Ctrl + Enter 也可保存"}</span>
          <span>{hasNotes ? `${value.trim().length} 字` : "当前页还没有演讲者注解"}</span>
        </div>
      </div>
    </div>
  );
}

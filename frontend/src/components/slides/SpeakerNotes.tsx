"use client";

import { useState, useRef } from "react";
import { Volume2, Square, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { synthesizeSpeech } from "@/lib/api";

interface SpeakerNotesProps {
  notes: string | undefined;
}

export default function SpeakerNotes({ notes }: SpeakerNotesProps) {
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  if (!notes) return null;

  const handlePlay = async () => {
    if (playing) {
      audioRef.current?.pause();
      audioRef.current = null;
      setPlaying(false);
      return;
    }

    setLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const blob = await synthesizeSpeech(notes, undefined, controller.signal);
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;

      audio.onended = () => {
        setPlaying(false);
        URL.revokeObjectURL(url);
      };
      audio.onerror = () => {
        setPlaying(false);
        URL.revokeObjectURL(url);
      };

      await audio.play();
      setPlaying(true);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      toast.error("语音合成失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="zy-card-inner border-white/80 bg-white/72 p-4 shadow-[0_20px_50px_-40px_rgba(15,23,42,0.35)]">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-sm font-medium text-slate-800">演讲者注释</span>
        <button
          type="button"
          onClick={handlePlay}
          disabled={loading}
          className="rounded-md p-1 text-slate-500 transition-colors hover:bg-white/80 hover:text-slate-800 disabled:opacity-50"
          title={playing ? "停止朗读" : "朗读注释"}
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
      <p className="text-sm leading-relaxed text-slate-600">{notes}</p>
    </div>
  );
}

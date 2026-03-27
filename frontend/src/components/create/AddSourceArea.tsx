"use client";

import { useEffect, useRef, useState } from "react";
import { Plus, Link } from "lucide-react";

const ACCEPTED_TYPES = ".pdf,.doc,.docx,.pptx,.ppt,.md,.markdown,.txt,.csv,.json,.png,.jpg,.jpeg,.gif,.webp";

interface AddSourceAreaProps {
  onFilesSelected: (files: File[]) => void;
  onUrlSubmit: (url: string) => void;
}

export default function AddSourceArea({
  onFilesSelected,
  onUrlSubmit,
}: AddSourceAreaProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [showUrlInput, setShowUrlInput] = useState(false);
  const [urlValue, setUrlValue] = useState("");

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) onFilesSelected(files);
    e.target.value = "";
  };

  const handleUrlSubmit = () => {
    const trimmed = urlValue.trim();
    if (!trimmed) return;
    onUrlSubmit(trimmed);
    setUrlValue("");
    setShowUrlInput(false);
  };

  const handleUrlKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleUrlSubmit();
    if (e.key === "Escape") {
      setShowUrlInput(false);
      setUrlValue("");
    }
  };

  useEffect(() => {
    if (!showUrlInput) return;

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (!target) return;
      if (containerRef.current?.contains(target)) return;
      setShowUrlInput(false);
      setUrlValue("");
    };

    document.addEventListener("pointerdown", handlePointerDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [showUrlInput]);

  return (
    <div
      ref={containerRef}
      className="rounded-[24px] border border-white/85 bg-[linear-gradient(180deg,rgba(255,255,255,0.88),rgba(247,249,252,0.82))] p-3 shadow-[0_20px_44px_-36px_rgba(15,23,42,0.42)]"
    >
      <button
        onClick={() => fileInputRef.current?.click()}
        className="flex w-full items-center justify-center gap-2 rounded-[18px] border border-dashed border-slate-300/90 bg-white/80 px-4 py-3 text-sm font-medium text-slate-600 transition-all duration-200 hover:border-slate-400 hover:bg-white hover:text-slate-900 hover:shadow-[0_16px_32px_-28px_rgba(15,23,42,0.45)]"
      >
        <Plus className="h-4 w-4" />
        添加素材
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_TYPES}
        multiple
        className="hidden"
        onChange={handleFileChange}
      />

      {showUrlInput ? (
        <div className="mt-3 flex gap-2">
          <input
            type="url"
            value={urlValue}
            onChange={(e) => setUrlValue(e.target.value)}
            onKeyDown={handleUrlKeyDown}
            placeholder="https://..."
            className="flex-1 rounded-2xl border border-white/90 bg-white/92 px-3 py-2 text-sm text-slate-700 outline-none transition focus:border-cyan-200 focus:ring-2 focus:ring-cyan-500/15"
            autoFocus
          />
          <button
            onClick={handleUrlSubmit}
            disabled={!urlValue.trim()}
            className="rounded-2xl bg-slate-900 px-4 py-2 text-sm text-white transition-colors hover:bg-slate-800 disabled:opacity-50"
          >
            添加
          </button>
        </div>
      ) : (
        <button
          onClick={() => setShowUrlInput(true)}
          className="mt-3 flex w-full items-center justify-center gap-1.5 text-xs text-slate-500 transition-colors hover:text-slate-700"
        >
          <Link className="h-3 w-3" />
          或粘贴网页链接
        </button>
      )}
    </div>
  );
}

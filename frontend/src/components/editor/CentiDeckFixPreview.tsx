"use client";

import type { CentiDeckArtifactPayload } from "@/lib/api";
import CentiDeckPreview from "@/components/editor/CentiDeckPreview";

interface CentiDeckFixPreviewProps {
  sessionId: string;
  proposedArtifact: CentiDeckArtifactPayload;
  currentSlideIndex?: number;
  onSlideChange?: (slideIndex: number) => void;
  onApply?: () => void;
  onDiscard?: () => void;
  applying?: boolean;
  discarding?: boolean;
  className?: string;
}

export default function CentiDeckFixPreview({
  sessionId,
  proposedArtifact,
  currentSlideIndex = 0,
  onSlideChange,
  onApply,
  onDiscard,
  applying = false,
  discarding = false,
  className = "",
}: CentiDeckFixPreviewProps) {
  return (
    <div className={`flex h-full w-full flex-col gap-2 ${className}`}>
      <div className="grid min-h-0 flex-1 grid-cols-2 gap-2">
        <div className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-950/60">
          <div className="flex items-center justify-between px-3 py-1.5 text-xs uppercase tracking-wider text-slate-400">
            <span>当前版本</span>
          </div>
          <div className="flex-1 min-h-0">
            <CentiDeckPreview
              sessionId={sessionId}
              startSlide={currentSlideIndex}
              onSlideChange={onSlideChange}
              mode="interactive"
            />
          </div>
        </div>
        <div className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-violet-800 bg-violet-950/20">
          <div className="flex items-center justify-between px-3 py-1.5 text-xs uppercase tracking-wider text-violet-300">
            <span>提议改稿</span>
          </div>
          <div className="flex-1 min-h-0">
            <CentiDeckPreview
              artifactOverride={proposedArtifact}
              startSlide={currentSlideIndex}
              onSlideChange={onSlideChange}
              mode="interactive"
            />
          </div>
        </div>
      </div>
      <div className="flex items-center justify-end gap-2 px-1">
        <button
          type="button"
          className="rounded-full border border-slate-700 px-4 py-1.5 text-sm text-slate-300 transition hover:border-slate-500 hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
          onClick={onDiscard}
          disabled={discarding || applying || !onDiscard}
        >
          {discarding ? "放弃中…" : "放弃"}
        </button>
        <button
          type="button"
          className="rounded-full bg-violet-600 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
          onClick={onApply}
          disabled={applying || discarding || !onApply}
        >
          {applying ? "应用中…" : "应用改稿"}
        </button>
      </div>
    </div>
  );
}

"use client";

import type { QuoteSlideData } from "@/types/layout-data";

export const layoutId = "quote-slide";
export const layoutName = "引用页";
export const layoutDescription = "重点引述/金句/结论，适合强调核心观点";

export default function QuoteSlideLayout({ data }: { data: QuoteSlideData }) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-24">
      <div style={{ fontSize: 80, lineHeight: 1 }} className="text-[var(--primary-color,#3b82f6)]/20 mb-2">
        &ldquo;
      </div>
      <blockquote style={{ fontSize: 30, lineHeight: 1.6, fontWeight: 500 }} className="text-[var(--background-text,#111827)] text-center max-w-[850px] mb-6">
        {data.quote}
      </blockquote>
      {(data.author || data.context) && (
        <div className="flex items-center gap-3">
          <div className="w-8 h-0.5 bg-[var(--primary-color,#3b82f6)]/30" />
          <span style={{ fontSize: 16 }} className="text-[var(--background-text,#111827)]/50">
            {data.author}{data.author && data.context ? " · " : ""}{data.context}
          </span>
        </div>
      )}
    </div>
  );
}

"use client";

import type { QuoteSlideData } from "@/types/layout-data";

export const layoutId = "quote-banner";
export const layoutName = "强调页（横幅）";
export const layoutDescription = "用横向强调带突出一句宣告式主张，适合发布会或关键判断页。";

export default function QuoteBannerLayout({ data }: { data: QuoteSlideData }) {
  return (
    <div className="flex h-full items-center justify-center bg-[linear-gradient(145deg,var(--slide-bg-start,#f8fafc)_0%,var(--slide-bg-end,#ffffff)_100%)] px-16 py-14 text-[var(--background-text,#111827)]">
      <div className="w-full max-w-[1080px] rounded-[40px] bg-slate-900 px-12 py-14 text-white shadow-2xl shadow-slate-900/12">
        <div className="text-xs font-semibold uppercase tracking-[0.24em] text-white/55">
          Key Takeaway
        </div>
        <blockquote style={{ fontSize: 38, fontWeight: 750, lineHeight: 1.28, letterSpacing: "-0.04em" }} className="mt-5 max-w-[920px]">
          {data.quote}
        </blockquote>
        {(data.author || data.context) ? (
          <div style={{ fontSize: 15, lineHeight: 1.6 }} className="mt-7 text-white/65">
            {[data.author, data.context].filter(Boolean).join(" · ")}
          </div>
        ) : null}
      </div>
    </div>
  );
}

"use client";

import type { IntroSlideData } from "@/types/layout-data";

export const layoutId = "intro-slide-left";
export const layoutName = "标题页（左对齐）";
export const layoutDescription = "演示首页，标题与说明左对齐展开，适合承载更完整的开场上下文。";

export default function IntroSlideLeftLayout({ data }: { data: IntroSlideData }) {
  const meta = [data.author, data.date].filter(Boolean);

  return (
    <div className="flex h-full bg-[linear-gradient(135deg,var(--slide-bg-start,#f8fafc)_0%,var(--slide-bg-end,#ffffff)_100%)] px-16 py-14 text-[var(--background-text,#111827)]">
      <div className="flex flex-1 flex-col justify-between">
        <div className="max-w-[780px]">
          <div className="mb-8 h-1.5 w-20 rounded-full bg-[var(--primary-color,#3b82f6)]" />
          <h1
            style={{ fontSize: 54, fontWeight: 800, lineHeight: 1.08, letterSpacing: "-0.05em" }}
            className="max-w-[720px]"
          >
            {data.title}
          </h1>
          <p
            style={{ fontSize: 22, lineHeight: 1.65 }}
            className="mt-6 max-w-[640px] text-[color:color-mix(in_srgb,var(--background-text,#111827)_66%,transparent)]"
          >
            {data.subtitle}
          </p>
        </div>

        <div className="flex items-end justify-between gap-8">
          <div className="max-w-[520px] rounded-3xl border border-slate-200 bg-white/80 px-6 py-5 shadow-sm backdrop-blur-sm">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--primary-color,#3b82f6)]">
              Opening Context
            </div>
            <p style={{ fontSize: 15, lineHeight: 1.7 }} className="mt-3 text-slate-600">
              Use this cover when the opening slide needs to carry more context than a pure hero title.
            </p>
          </div>
          {meta.length > 0 ? (
            <div className="text-right text-sm text-slate-500">
              {meta.map((item) => (
                <div key={item}>{item}</div>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

"use client";

import type { OutlineSlideData } from "@/types/layout-data";

export const layoutId = "outline-slide-rail";
export const layoutName = "目录导航页（导轨）";
export const layoutDescription = "展示整体汇报框架的导轨式目录页，强调章节推进顺序。";

export default function OutlineSlideRailLayout({ data }: { data: OutlineSlideData }) {
  return (
    <div className="flex h-full bg-[linear-gradient(160deg,var(--slide-bg-start,#ffffff)_0%,var(--slide-bg-end,#f8fafc)_100%)] px-16 py-14 text-[var(--background-text,#111827)]">
      <div className="flex w-full gap-12">
        <section className="w-[38%] shrink-0">
          <div className="mb-5 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--primary-color,#3b82f6)]">
            Chapter Rail
          </div>
          <h2 style={{ fontSize: 42, fontWeight: 800, lineHeight: 1.08, letterSpacing: "-0.05em" }}>
            {data.title}
          </h2>
          {data.subtitle ? (
            <p style={{ fontSize: 17, lineHeight: 1.65 }} className="mt-5 text-slate-600">
              {data.subtitle}
            </p>
          ) : null}
        </section>

        <section className="flex-1 rounded-[32px] border border-slate-200 bg-white p-8 shadow-sm">
          <div className="relative flex h-full flex-col gap-5">
            <div className="absolute left-[22px] top-3 bottom-3 w-px bg-slate-200" />
            {data.sections.map((section, index) => (
              <article key={`${section.title}-${index}`} className="relative flex gap-5">
                <div className="relative z-10 flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[var(--primary-color,#3b82f6)] text-sm font-bold text-white shadow-sm">
                  {String(index + 1).padStart(2, "0")}
                </div>
                <div className="min-w-0 rounded-2xl border border-slate-100 bg-slate-50 px-5 py-4">
                  <h3 style={{ fontSize: 23, fontWeight: 700, lineHeight: 1.2 }}>
                    {section.title}
                  </h3>
                  {section.description ? (
                    <p style={{ fontSize: 14, lineHeight: 1.65 }} className="mt-2 text-slate-600">
                      {section.description}
                    </p>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

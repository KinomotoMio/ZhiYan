"use client";

import type { SectionHeaderData } from "@/types/layout-data";

export const layoutId = "section-header-side";
export const layoutName = "章节过渡（侧标）";
export const layoutDescription = "章节分隔页，带编号侧标和标题说明，用于更强的导航式章节切换。";

export default function SectionHeaderSideLayout({ data }: { data: SectionHeaderData }) {
  return (
    <div className="flex h-full items-center px-16 py-14 text-[var(--background-text,#111827)]">
      <div className="grid w-full grid-cols-[220px_minmax(0,1fr)] gap-10 rounded-[36px] border border-slate-200 bg-[linear-gradient(135deg,rgba(255,255,255,0.98),rgba(248,250,252,0.96))] p-12 shadow-sm">
        <div className="flex flex-col justify-between rounded-[28px] bg-slate-900 px-7 py-8 text-white">
          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-white/65">
            Section
          </div>
          <div style={{ fontSize: 54, fontWeight: 800, lineHeight: 1 }}>
            02
          </div>
        </div>
        <div className="flex flex-col justify-center">
          <div className="mb-4 h-1.5 w-16 rounded-full bg-[var(--primary-color,#3b82f6)]" />
          <h2 style={{ fontSize: 46, fontWeight: 800, lineHeight: 1.08, letterSpacing: "-0.05em" }}>
            {data.title}
          </h2>
          {data.subtitle ? (
            <p style={{ fontSize: 18, lineHeight: 1.65 }} className="mt-5 max-w-[760px] text-slate-600">
              {data.subtitle}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

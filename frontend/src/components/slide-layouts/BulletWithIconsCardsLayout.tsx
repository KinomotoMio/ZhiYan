"use client";

import { LayoutIcon } from "./_shared";
import type { BulletWithIconsData } from "@/types/layout-data";

export const layoutId = "bullet-with-icons-cards";
export const layoutName = "图标要点（卡片）";
export const layoutDescription = "带图标的 3-4 个能力卡片，适合展示模块化功能、卖点和解决方案。";

export default function BulletWithIconsCardsLayout({ data }: { data: BulletWithIconsData }) {
  return (
    <div className="flex h-full flex-col bg-[linear-gradient(180deg,var(--slide-bg-start,#ffffff)_0%,var(--slide-bg-end,#f8fafc)_100%)] px-16 py-14 text-[var(--background-text,#111827)]">
      <h2 style={{ fontSize: 36, fontWeight: 800, lineHeight: 1.2, letterSpacing: "-0.04em" }} className="mb-10 max-w-[760px]">
        {data.title}
      </h2>
      <div className="grid flex-1 grid-cols-2 gap-6">
        {data.items.map((item, index) => (
          <article key={`${item.title}-${index}`} className="flex min-h-0 flex-col rounded-[28px] border border-slate-200 bg-white p-7 shadow-sm">
            <div className="mb-6 flex items-center justify-between gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[color:color-mix(in_srgb,var(--primary-color,#3b82f6)_12%,white)] text-[var(--primary-color,#3b82f6)]">
                <LayoutIcon query={item.icon.query} className="h-6 w-6" />
              </div>
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                {String(index + 1).padStart(2, "0")}
              </div>
            </div>
            <h3 style={{ fontSize: 24, fontWeight: 700, lineHeight: 1.18 }} className="max-w-[360px]">
              {item.title}
            </h3>
            <p style={{ fontSize: 15, lineHeight: 1.7 }} className="mt-4 text-slate-600">
              {item.description}
            </p>
          </article>
        ))}
      </div>
    </div>
  );
}

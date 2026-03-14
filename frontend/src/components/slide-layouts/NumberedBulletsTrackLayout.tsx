"use client";

import type { NumberedBulletsData } from "@/types/layout-data";

export const layoutId = "numbered-bullets-track";
export const layoutName = "编号要点（轨道）";
export const layoutDescription = "沿一条进度轨道排列步骤，适合表达连续推进的 rollout 或执行路径。";

export default function NumberedBulletsTrackLayout({ data }: { data: NumberedBulletsData }) {
  return (
    <div className="flex h-full flex-col px-16 py-14 text-[var(--background-text,#111827)]">
      <h2 style={{ fontSize: 36, fontWeight: 800, lineHeight: 1.18, letterSpacing: "-0.04em" }} className="mb-10 max-w-[760px]">
        {data.title}
      </h2>
      <div className="relative flex flex-1 flex-col justify-between gap-5 pl-16">
        <div className="absolute left-[30px] top-3 bottom-3 w-1 rounded-full bg-[color:color-mix(in_srgb,var(--primary-color,#3b82f6)_18%,white)]" />
        {data.items.map((item, index) => (
          <article key={`${item.title}-${index}`} className="relative rounded-[28px] border border-slate-200 bg-white px-6 py-5 shadow-sm">
            <div className="absolute -left-[52px] top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full bg-[var(--primary-color,#3b82f6)] text-base font-bold text-white shadow-sm">
              {index + 1}
            </div>
            <h3 style={{ fontSize: 23, fontWeight: 700, lineHeight: 1.2 }}>
              {item.title}
            </h3>
            <p style={{ fontSize: 15, lineHeight: 1.7 }} className="mt-3 text-slate-600">
              {item.description}
            </p>
          </article>
        ))}
      </div>
    </div>
  );
}

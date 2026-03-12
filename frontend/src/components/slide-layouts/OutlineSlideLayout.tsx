"use client";

import type { OutlineSlideData } from "@/types/layout-data";

export const layoutId = "outline-slide";
export const layoutName = "目录导航页";
export const layoutDescription = "展示整体汇报框架的目录页，使用 4-6 个网格卡片呈现章节结构。";

export default function OutlineSlideLayout({ data }: { data: OutlineSlideData }) {
  const columns = data.sections.length >= 5 ? 3 : 2;

  return (
    <div className="flex h-full flex-col px-16 py-14 text-[var(--background-text,#111827)]">
      <div className="max-w-[640px]">
        <h2
          style={{ fontSize: 42, fontWeight: 700, lineHeight: 1.15, letterSpacing: "-0.04em" }}
          className="mb-4"
        >
          {data.title}
        </h2>
        {data.subtitle && (
          <p
            style={{ fontSize: 17, lineHeight: 1.55 }}
            className="max-w-[560px] text-[color:color-mix(in_srgb,var(--background-text,#111827)_60%,transparent)]"
          >
            {data.subtitle}
          </p>
        )}
      </div>

      <div
        className="mt-10 grid flex-1 content-start"
        style={{
          gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
          columnGap: 22,
          rowGap: 24,
        }}
      >
        {data.sections.map((section, index) => (
          <article
            key={`${section.title}-${index}`}
            className="overflow-hidden rounded-[18px] border border-black/6 bg-white shadow-[0_12px_30px_rgba(15,23,42,0.06)]"
          >
            <div className="border-b border-black/6 px-7 py-6">
              <div
                style={{ fontSize: 14, fontWeight: 600, letterSpacing: "0.08em" }}
                className="mb-4 uppercase text-[color:color-mix(in_srgb,var(--background-text,#111827)_42%,transparent)]"
              >
                {String(index + 1).padStart(2, "0")}
              </div>
              <h3
                style={{ fontSize: 30, fontWeight: 500, lineHeight: 0.96, letterSpacing: "-0.06em" }}
                className="min-h-[58px]"
              >
                {section.title}
              </h3>
            </div>

            <div className="h-[132px] bg-[linear-gradient(135deg,color-mix(in_srgb,var(--primary-color,#3b82f6)_16%,white),color-mix(in_srgb,var(--background-text,#111827)_10%,white))]" />

            <div className="bg-[color:color-mix(in_srgb,var(--background-text,#111827)_84%,black)] px-7 py-4 text-white">
              <div
                style={{ fontSize: 14, lineHeight: 1.45 }}
                className="min-h-[40px] text-white/88"
              >
                {section.description || section.title}
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

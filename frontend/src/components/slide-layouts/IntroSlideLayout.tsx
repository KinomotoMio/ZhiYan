"use client";

import type { IntroSlideData } from "@/types/layout-data";

export const layoutId = "intro-slide";
export const layoutName = "标题页";
export const layoutDescription = "演示首页，大标题+副标题+作者信息，适合开场";

export default function IntroSlideLayout({ data }: { data: IntroSlideData }) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-20 text-center">
      <h1 style={{ fontSize: 52, fontWeight: 700, lineHeight: 1.2 }} className="text-[var(--background-text,#111827)] mb-4 max-w-[900px]">
        {data.title}
      </h1>
      <p style={{ fontSize: 24 }} className="text-[var(--background-text,#111827)]/60 mb-10 max-w-[700px]">
        {data.subtitle}
      </p>
      {(data.author || data.date) && (
        <div style={{ fontSize: 16 }} className="text-[var(--background-text,#111827)]/40 flex items-center gap-4">
          {data.author && <span>{data.author}</span>}
          {data.author && data.date && <span>·</span>}
          {data.date && <span>{data.date}</span>}
        </div>
      )}
    </div>
  );
}

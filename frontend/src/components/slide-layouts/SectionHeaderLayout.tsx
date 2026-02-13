"use client";

import type { SectionHeaderData } from "@/types/layout-data";

export const layoutId = "section-header";
export const layoutName = "章节过渡";
export const layoutDescription = "章节分隔页，大标题+简述，用于主题切换过渡";

export default function SectionHeaderLayout({ data }: { data: SectionHeaderData }) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-24">
      <div className="w-12 h-1 rounded-full bg-[var(--primary-color,#3b82f6)] mb-8" />
      <h2 style={{ fontSize: 44, fontWeight: 700, lineHeight: 1.3 }} className="text-[var(--background-text,#111827)] text-center mb-4 max-w-[800px]">
        {data.title}
      </h2>
      {data.subtitle && (
        <p style={{ fontSize: 20 }} className="text-[var(--background-text,#111827)]/50 text-center max-w-[600px]">
          {data.subtitle}
        </p>
      )}
    </div>
  );
}

"use client";

import type { TwoColumnCompareData } from "@/types/layout-data";
import { LayoutIcon } from "./_shared";

export const layoutId = "two-column-compare";
export const layoutName = "双栏对比";
export const layoutDescription = "左右两栏对比内容，适合方案比较、优劣分析";

export default function TwoColumnCompareLayout({ data }: { data: TwoColumnCompareData }) {
  return (
    <div className="flex flex-col h-full px-16 py-14">
      <h2 style={{ fontSize: 36, fontWeight: 700, lineHeight: 1.3 }} className="text-[var(--background-text,#111827)] mb-8">
        {data.title}
      </h2>
      <div className="flex gap-8 flex-1">
        {[data.left, data.right].map((col, ci) => (
          <div key={ci} className="flex-1 rounded-2xl bg-[var(--primary-color,#3b82f6)]/5 p-8">
            <div className="flex items-center gap-3 mb-6">
              {col.icon && <LayoutIcon query={col.icon.query} className="w-6 h-6 text-[var(--primary-color,#3b82f6)]" />}
              <h3 style={{ fontSize: 24, fontWeight: 700 }} className="text-[var(--background-text,#111827)]">
                {col.heading}
              </h3>
            </div>
            <div className="flex flex-col gap-4">
              {col.items.map((item, i) => (
                <div key={i} className="flex items-start gap-3">
                  <div className="w-2 h-2 rounded-full bg-[var(--primary-color,#3b82f6)] mt-2 shrink-0" />
                  <p style={{ fontSize: 17, lineHeight: 1.5 }} className="text-[var(--background-text,#111827)]/70">
                    {item}
                  </p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

"use client";

import type { BulletIconsOnlyData } from "@/types/layout-data";
import { LayoutIcon } from "./_shared";

export const layoutId = "bullet-icons-only";
export const layoutName = "纯图标网格";
export const layoutDescription = "4-8 个图标+标签的网格，适合技术栈、特性一览";

export default function BulletIconsOnlyLayout({ data }: { data: BulletIconsOnlyData }) {
  const cols = data.items.length <= 4 ? 4 : data.items.length <= 6 ? 3 : 4;
  return (
    <div className="flex flex-col h-full px-16 py-14">
      <h2 style={{ fontSize: 36, fontWeight: 700, lineHeight: 1.3 }} className="text-[var(--background-text,#111827)] mb-10">
        {data.title}
      </h2>
      <div className={`grid gap-8 flex-1 items-center`} style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
        {data.items.map((item, i) => (
          <div key={i} className="flex flex-col items-center text-center">
            <div className="w-16 h-16 rounded-2xl bg-[var(--primary-color,#3b82f6)]/10 flex items-center justify-center mb-4">
              <LayoutIcon query={item.icon.query} className="w-8 h-8 text-[var(--primary-color,#3b82f6)]" />
            </div>
            <span style={{ fontSize: 16, fontWeight: 600 }} className="text-[var(--background-text,#111827)]">
              {item.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

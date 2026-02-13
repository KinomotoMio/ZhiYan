"use client";

import type { BulletWithIconsData } from "@/types/layout-data";
import { LayoutIcon } from "./_shared";

export const layoutId = "bullet-with-icons";
export const layoutName = "图标要点";
export const layoutDescription = "带图标的 3-4 个要点，适合功能介绍、优势列举";

export default function BulletWithIconsLayout({ data }: { data: BulletWithIconsData }) {
  return (
    <div className="flex flex-col h-full px-16 py-14">
      <h2 style={{ fontSize: 36, fontWeight: 700, lineHeight: 1.3 }} className="text-[var(--background-text,#111827)] mb-10">
        {data.title}
      </h2>
      <div className={`grid gap-8 flex-1 ${data.items.length <= 3 ? "grid-cols-3" : "grid-cols-4"}`}>
        {data.items.map((item, i) => (
          <div key={i} className="flex flex-col items-start">
            <div className="w-14 h-14 rounded-xl bg-[var(--primary-color,#3b82f6)]/10 flex items-center justify-center mb-4">
              <LayoutIcon query={item.icon.query} className="w-7 h-7 text-[var(--primary-color,#3b82f6)]" />
            </div>
            <h3 style={{ fontSize: 20, fontWeight: 600 }} className="text-[var(--background-text,#111827)] mb-2">
              {item.title}
            </h3>
            <p style={{ fontSize: 16, lineHeight: 1.5 }} className="text-[var(--background-text,#111827)]/60">
              {item.description}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

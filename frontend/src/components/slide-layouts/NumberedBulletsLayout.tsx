"use client";

import type { NumberedBulletsData } from "@/types/layout-data";

export const layoutId = "numbered-bullets";
export const layoutName = "编号要点";
export const layoutDescription = "带编号的步骤列表，适合流程、步骤、方法论";

export default function NumberedBulletsLayout({ data }: { data: NumberedBulletsData }) {
  return (
    <div className="flex flex-col h-full px-16 py-14">
      <h2 style={{ fontSize: 36, fontWeight: 700, lineHeight: 1.3 }} className="text-[var(--background-text,#111827)] mb-10">
        {data.title}
      </h2>
      <div className="flex flex-col gap-6 flex-1">
        {data.items.map((item, i) => (
          <div key={i} className="flex items-start gap-5">
            <div className="w-10 h-10 rounded-full bg-[var(--primary-color,#3b82f6)] flex items-center justify-center shrink-0">
              <span style={{ fontSize: 18, fontWeight: 700 }} className="text-[var(--primary-text,#ffffff)]">
                {i + 1}
              </span>
            </div>
            <div className="pt-1">
              <h3 style={{ fontSize: 22, fontWeight: 600 }} className="text-[var(--background-text,#111827)] mb-1">
                {item.title}
              </h3>
              <p style={{ fontSize: 16, lineHeight: 1.5 }} className="text-[var(--background-text,#111827)]/60">
                {item.description}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

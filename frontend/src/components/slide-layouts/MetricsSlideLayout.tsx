"use client";

import type { MetricsSlideData } from "@/types/layout-data";

export const layoutId = "metrics-slide";
export const layoutName = "指标卡片";
export const layoutDescription = "展示 2-4 个关键指标/KPI 数字，适合数据概览页";

export default function MetricsSlideLayout({ data }: { data: MetricsSlideData }) {
  return (
    <div className="flex flex-col h-full px-16 py-14">
      <h2 style={{ fontSize: 36, fontWeight: 700, lineHeight: 1.3 }} className="text-[var(--background-text,#111827)] mb-10">
        {data.title}
      </h2>
      <div className={`grid gap-8 flex-1 items-center ${
        data.metrics.length === 2 ? "grid-cols-2" :
        data.metrics.length === 3 ? "grid-cols-3" : "grid-cols-4"
      }`}>
        {data.metrics.map((metric, i) => (
          <div key={i} className="flex flex-col items-center text-center p-6 rounded-2xl bg-[var(--primary-color,#3b82f6)]/5">
            <span style={{ fontSize: 48, fontWeight: 800, lineHeight: 1.1 }} className="text-[var(--primary-color,#3b82f6)] mb-2">
              {metric.value}
            </span>
            <span style={{ fontSize: 18, fontWeight: 600 }} className="text-[var(--background-text,#111827)] mb-1">
              {metric.label}
            </span>
            {metric.description && (
              <span style={{ fontSize: 14 }} className="text-[var(--background-text,#111827)]/50">
                {metric.description}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

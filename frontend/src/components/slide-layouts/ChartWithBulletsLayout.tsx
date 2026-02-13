"use client";

import { BarChart3 } from "lucide-react";
import type { ChartWithBulletsData } from "@/types/layout-data";

export const layoutId = "chart-with-bullets";
export const layoutName = "图表+要点";
export const layoutDescription = "左侧图表右侧要点，适合数据分析+解读";

export default function ChartWithBulletsLayout({ data }: { data: ChartWithBulletsData }) {
  return (
    <div className="flex flex-col h-full px-16 py-14">
      <h2 style={{ fontSize: 36, fontWeight: 700, lineHeight: 1.3 }} className="text-[var(--background-text,#111827)] mb-8">
        {data.title}
      </h2>
      <div className="flex gap-10 flex-1">
        <div className="flex-1 rounded-2xl bg-gray-50 border border-gray-200 flex flex-col items-center justify-center">
          <BarChart3 className="w-16 h-16 text-gray-300 mb-3" />
          <span style={{ fontSize: 14 }} className="text-gray-400">{data.chart.chartType} 图表</span>
          <span style={{ fontSize: 12 }} className="text-gray-300 mt-1">{data.chart.labels.join(", ")}</span>
        </div>
        <div className="w-[40%] flex flex-col justify-center gap-5">
          {data.bullets.map((bullet, i) => (
            <div key={i} className="flex items-start gap-3">
              <div className="w-2 h-2 rounded-full bg-[var(--primary-color,#3b82f6)] mt-2 shrink-0" />
              <p style={{ fontSize: 18, lineHeight: 1.5 }} className="text-[var(--background-text,#111827)]/80">
                {bullet.text}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

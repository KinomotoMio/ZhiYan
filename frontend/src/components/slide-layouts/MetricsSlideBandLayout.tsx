"use client";

import type { MetricItem, MetricsSlideRuntimeData } from "@/types/layout-data";

export const layoutId = "metrics-slide-band";
export const layoutName = "指标卡片（横幅）";
export const layoutDescription = "带横向结论带的指标页，适合先讲判断再用关键数字补充证据。";

function MetricBandCard({ metric }: { metric: MetricItem }) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white px-6 py-6 shadow-sm">
      <div style={{ fontSize: 15, fontWeight: 600, lineHeight: 1.4 }} className="text-slate-500">
        {metric.label}
      </div>
      <div style={{ fontSize: 42, fontWeight: 800, lineHeight: 1.05 }} className="mt-3 text-[var(--primary-color,#3b82f6)]">
        {metric.value}
      </div>
      {metric.description ? (
        <div style={{ fontSize: 13, lineHeight: 1.6 }} className="mt-3 text-slate-600">
          {metric.description}
        </div>
      ) : null}
    </div>
  );
}

export default function MetricsSlideBandLayout({ data }: { data: MetricsSlideRuntimeData }) {
  return (
    <div className="flex h-full flex-col bg-[linear-gradient(180deg,var(--slide-bg-start,#ffffff)_0%,var(--slide-bg-end,#eff6ff)_100%)] px-16 py-14 text-[var(--background-text,#111827)]">
      <h2 style={{ fontSize: 36, fontWeight: 800, lineHeight: 1.2, letterSpacing: "-0.04em" }} className="mb-6">
        {data.title}
      </h2>
      <section className="mb-8 rounded-[32px] bg-slate-900 px-9 py-8 text-white shadow-lg shadow-slate-900/10">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-white/60">
          Executive Summary
        </div>
        <p style={{ fontSize: 32, fontWeight: 750, lineHeight: 1.2 }} className="mt-4 max-w-[920px]">
          {data.conclusion || data.title}
        </p>
        {data.conclusionBrief ? (
          <p style={{ fontSize: 16, lineHeight: 1.7 }} className="mt-4 max-w-[900px] text-white/70">
            {data.conclusionBrief}
          </p>
        ) : null}
      </section>
      <div className="grid flex-1 auto-rows-fr grid-cols-2 gap-6 xl:grid-cols-4">
        {data.metrics.map((metric, index) => (
          <MetricBandCard key={`${metric.label}-${index}`} metric={metric} />
        ))}
      </div>
    </div>
  );
}

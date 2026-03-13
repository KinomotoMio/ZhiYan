"use client";

import type { MetricItem, MetricsSlideRuntimeData } from "@/types/layout-data";

export const layoutId = "metrics-slide";
export const layoutName = "指标卡片";
export const layoutDescription = "支持 Executive Summary 结论先行的指标页，并兼容历史 metrics-only 数据。";

function getMetricColumns(count: number): string {
  if (count <= 1) return "grid-cols-1";
  if (count === 2) return "grid-cols-2";
  if (count === 3) return "grid-cols-3";
  return "grid-cols-4";
}

function MetricCard({ metric, compact }: { metric: MetricItem; compact: boolean }) {
  return (
    <div
      className={`flex flex-col rounded-2xl bg-[var(--primary-color,#3b82f6)]/5 ${
        compact ? "min-h-[168px] px-6 py-5" : "items-center p-6 text-center"
      }`}
    >
      <span
        style={{
          fontSize: compact ? 40 : 48,
          fontWeight: 800,
          lineHeight: 1.1,
        }}
        className="mb-2 text-[var(--primary-color,#3b82f6)]"
      >
        {metric.value}
      </span>
      <span
        style={{ fontSize: compact ? 17 : 18, fontWeight: 600, lineHeight: 1.35 }}
        className="mb-1 text-[var(--background-text,#111827)]"
      >
        {metric.label}
      </span>
      {metric.description && (
        <span
          style={{ fontSize: compact ? 13 : 14, lineHeight: 1.5 }}
          className="text-[var(--background-text,#111827)]/60"
        >
          {metric.description}
        </span>
      )}
    </div>
  );
}

export default function MetricsSlideLayout({ data }: { data: MetricsSlideRuntimeData }) {
  const hasExecutiveSummary = Boolean(
    data.conclusion?.trim() || data.conclusionBrief?.trim()
  );
  const metricColumns = getMetricColumns(data.metrics.length);

  return (
    <div className="flex h-full flex-col px-16 py-14">
      <h2
        style={{ fontSize: 36, fontWeight: 700, lineHeight: 1.3 }}
        className={`text-[var(--background-text,#111827)] ${hasExecutiveSummary ? "mb-6" : "mb-10"}`}
      >
        {data.title}
      </h2>
      {hasExecutiveSummary ? (
        <>
          <section className="mb-8 rounded-[28px] border border-[var(--primary-color,#3b82f6)]/15 bg-[linear-gradient(135deg,rgba(59,130,246,0.10),rgba(255,255,255,0.92))] px-10 py-8">
            {data.conclusion && (
              <p
                style={{ fontSize: 32, fontWeight: 700, lineHeight: 1.2 }}
                className="text-[var(--background-text,#111827)]"
              >
                {data.conclusion}
              </p>
            )}
            {data.conclusionBrief && (
              <p
                style={{ fontSize: 17, lineHeight: 1.6 }}
                className={`max-w-4xl text-[var(--background-text,#111827)]/70 ${
                  data.conclusion ? "mt-4" : "mt-0"
                }`}
              >
                {data.conclusionBrief}
              </p>
            )}
          </section>
          <div className={`grid flex-1 auto-rows-fr gap-6 ${metricColumns}`}>
            {data.metrics.map((metric, i) => (
              <MetricCard key={i} metric={metric} compact />
            ))}
          </div>
        </>
      ) : (
        <div className={`grid flex-1 items-center gap-8 ${metricColumns}`}>
          {data.metrics.map((metric, i) => (
            <MetricCard key={i} metric={metric} compact={false} />
          ))}
        </div>
      )}
    </div>
  );
}

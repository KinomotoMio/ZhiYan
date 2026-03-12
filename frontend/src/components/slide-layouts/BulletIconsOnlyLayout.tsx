"use client";

import type { BulletIconsOnlyData } from "@/types/layout-data";
import { LayoutIcon } from "./_shared";

export const layoutId = "bullet-icons-only";
export const layoutName = "纯图标网格";
export const layoutDescription = "4-8 个图标标签的两列能力矩阵，适合技术栈、特性一览";

export default function BulletIconsOnlyLayout({ data }: { data: BulletIconsOnlyData }) {
  const compact = data.items.length >= 7;

  return (
    <div className="flex h-full flex-col px-16 py-14">
      <h2
        style={{ fontSize: 36, fontWeight: 700, lineHeight: 1.3 }}
        className="mb-8 text-[var(--background-text,#111827)]"
      >
        {data.title}
      </h2>
      <div
        className="grid flex-1 min-h-0 content-center"
        style={{
          gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
          columnGap: compact ? 28 : 40,
          rowGap: compact ? 18 : 22,
        }}
      >
        {data.items.map((item, i) => (
          <div
            key={i}
            className="relative flex min-h-[92px] items-center overflow-hidden rounded-[28px] px-6 py-5"
            style={{ backgroundColor: "color-mix(in srgb, var(--background-text,#111827) 3%, white)" }}
          >
            <div
              className="absolute left-7 top-1/2 h-12 w-24 -translate-y-1/2 rounded-[16px]"
              style={{
                transform: "translateY(-50%) skewX(-22deg)",
                backgroundColor: "color-mix(in srgb, var(--primary-color,#3b82f6) 16%, transparent)",
              }}
              aria-hidden="true"
            />
            <div
              className="relative z-10 flex h-[72px] w-[72px] items-center justify-center rounded-[22px] bg-white shadow-[0_12px_32px_rgba(15,23,42,0.08)]"
              style={{
                border: "1px solid color-mix(in srgb, var(--primary-color,#3b82f6) 14%, transparent)",
                backgroundColor: "#fff",
              }}
            >
              <LayoutIcon query={item.icon.query} className="h-10 w-10 text-[var(--primary-color,#3b82f6)]" />
            </div>
            <div className="relative z-10 ml-6 min-w-0">
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 700,
                  letterSpacing: "0.24em",
                  color: "color-mix(in srgb, var(--background-text,#111827) 42%, transparent)",
                }}
                className="mb-1"
              >
                {String(i + 1).padStart(2, "0")}
              </div>
              <div
                style={{
                  fontSize: compact ? 21 : 24,
                  fontWeight: 700,
                  lineHeight: 1.08,
                  letterSpacing: "-0.04em",
                }}
                className="text-[var(--background-text,#111827)]"
              >
                <span
                  style={{
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                >
                  {item.label}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

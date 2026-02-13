"use client";

import type { CompareColumn, TwoColumnCompareData } from "@/types/layout-data";
import { LayoutIcon } from "./_shared";

export const layoutId = "two-column-compare";
export const layoutName = "双栏对比";
export const layoutDescription = "左右两栏对比内容，适合方案比较、优劣分析";

function normalizeColumn(raw: unknown, fallbackHeading: string): CompareColumn {
  const source = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const headingRaw =
    (typeof source.heading === "string" && source.heading.trim() && source.heading) ||
    (typeof source.title === "string" && source.title.trim() && source.title) ||
    fallbackHeading;

  const list = Array.isArray(source.items) ? source.items : [];
  const items = list
    .map((item) => {
      if (typeof item === "string") return item.trim();
      if (!item || typeof item !== "object") return "";
      const row = item as Record<string, unknown>;
      return (
        (typeof row.text === "string" && row.text.trim()) ||
        (typeof row.title === "string" && row.title.trim()) ||
        (typeof row.description === "string" && row.description.trim()) ||
        ""
      );
    })
    .filter((text) => text.length > 0);

  const icon =
    source.icon && typeof source.icon === "object"
      ? (source.icon as { query?: unknown })
      : null;
  const iconQuery =
    icon && typeof icon.query === "string" && icon.query.trim()
      ? icon.query.trim()
      : null;

  return {
    heading: headingRaw,
    items: items.length > 0 ? items : ["内容生成中"],
    icon: iconQuery ? { query: iconQuery } : null,
  };
}

export default function TwoColumnCompareLayout({ data }: { data: TwoColumnCompareData }) {
  const left = normalizeColumn(data.left, "要点 A");
  const right = normalizeColumn(data.right, "要点 B");
  const title =
    typeof data.title === "string" && data.title.trim()
      ? data.title
      : "对比分析";

  return (
    <div className="flex flex-col h-full px-16 py-14">
      <h2 style={{ fontSize: 36, fontWeight: 700, lineHeight: 1.3 }} className="text-[var(--background-text,#111827)] mb-8">
        {title}
      </h2>
      <div className="flex gap-8 flex-1">
        {[left, right].map((col, ci) => (
          <div key={ci} className="flex-1 rounded-2xl bg-[var(--primary-color,#3b82f6)]/5 p-8">
            <div className="flex items-center gap-3 mb-6">
              {col.icon?.query && (
                <LayoutIcon query={col.icon.query} className="w-6 h-6 text-[var(--primary-color,#3b82f6)]" />
              )}
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

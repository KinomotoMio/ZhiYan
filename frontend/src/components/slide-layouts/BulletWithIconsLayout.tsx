"use client";

import { getBulletWithIconsColumns } from "@/lib/layout-rules";
import type { BulletWithIconsData } from "@/types/layout-data";
import { LayoutIcon } from "./_shared";

export const layoutId = "bullet-with-icons";
export const layoutName = "图标要点";
export const layoutDescription = "带图标的 3-4 个要点，适合功能介绍、优势列举";

export default function BulletWithIconsLayout({ data }: { data: BulletWithIconsData }) {
  const columns = getBulletWithIconsColumns(data.items.length);
  const compact = columns === 4;

  return (
    <div className="flex h-full flex-col px-16 py-14">
      <h2
        style={{ fontSize: 36, fontWeight: 700, lineHeight: 1.3 }}
        className="mb-10 text-[var(--background-text,#111827)]"
      >
        {data.title}
      </h2>
      <div
        className="grid flex-1 min-h-0"
        style={{
          gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
          columnGap: compact ? 18 : 26,
        }}
      >
        {data.items.map((item, i) => (
          <div
            key={i}
            className="relative flex h-full min-h-0 flex-col pl-4"
          >
            <div
              className="absolute left-0 top-1/2 -translate-y-1/2"
              style={{
                width: 1,
                height: compact ? "46%" : "50%",
                backgroundColor: "color-mix(in srgb, var(--background-text,#111827) 12%, transparent)",
              }}
            />
            <div className="flex min-h-0 flex-1 flex-col justify-center py-2">
              <div
                className="mb-4 flex h-10 w-10 items-center justify-center rounded-full"
                style={{ backgroundColor: "color-mix(in srgb, var(--primary-color,#3b82f6) 12%, white)" }}
              >
                <LayoutIcon query={item.icon.query} className="h-5 w-5 text-[var(--primary-color,#3b82f6)]" />
              </div>
              <h3
                style={{ fontSize: compact ? 19 : 21, fontWeight: 700, lineHeight: 1.08, letterSpacing: "-0.04em" }}
                className="mb-2 min-w-0 text-[var(--primary-color,#3b82f6)]"
              >
                <span
                  style={{
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                >
                  <span
                    style={{
                      backgroundColor: "color-mix(in srgb, var(--primary-color,#3b82f6) 7%, white)",
                      borderRadius: 3,
                      padding: compact ? "0.04em 0.2em 0.1em" : "0.05em 0.22em 0.12em",
                      WebkitBoxDecorationBreak: "clone",
                      boxDecorationBreak: "clone",
                    }}
                  >
                    {item.title}
                  </span>
                </span>
              </h3>
              {!!item.description && (
                <p
                  style={{
                    fontSize: compact ? 11.5 : 12.5,
                    lineHeight: 1.42,
                    color: "color-mix(in srgb, var(--background-text,#111827) 72%, transparent)",
                  }}
                  className="max-w-[240px]"
                >
                  <span
                    style={{
                      display: "-webkit-box",
                      WebkitLineClamp: compact ? 4 : 5,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                    }}
                  >
                    {item.description}
                  </span>
                </p>
              )}

              <div
                style={{ fontSize: compact ? 52 : 60, fontWeight: 400, lineHeight: 0.92, letterSpacing: "-0.06em" }}
                className="pt-4 text-[var(--background-text,#111827)]"
              >
                {String(i + 1).padStart(2, "0")}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

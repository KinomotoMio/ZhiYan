"use client";

import { getBulletIconsOnlyLayoutTokens } from "@/lib/icon-card-layout-tokens";
import type { BulletIconsOnlyData } from "@/types/layout-data";
import { LayoutIcon } from "./_shared";

export const layoutId = "bullet-icons-only";
export const layoutName = "纯图标网格";
export const layoutDescription = "4-8 个图标标签的两列能力矩阵，适合技术栈、特性一览";

export default function BulletIconsOnlyLayout({ data }: { data: BulletIconsOnlyData }) {
  const tokens = getBulletIconsOnlyLayoutTokens(data.items.length);

  return (
    <div
      className="flex h-full flex-col"
      style={{ padding: `${tokens.outerPaddingY}px ${tokens.outerPaddingX}px` }}
    >
      <h2
        style={{
          fontSize: tokens.titleFontSize,
          fontWeight: 700,
          lineHeight: tokens.titleLineHeight,
          marginBottom: tokens.titleMarginBottom,
        }}
        className="text-[var(--background-text,#111827)]"
      >
        {data.title}
      </h2>
      <div
        className="grid flex-1 min-h-0 content-center"
        style={{
          gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
          columnGap: tokens.gridColumnGap,
          rowGap: tokens.gridRowGap,
        }}
      >
        {data.items.map((item, i) => (
          <div
            key={i}
            className="relative flex items-center overflow-hidden rounded-[28px]"
            style={{
              minHeight: tokens.cardMinHeight,
              padding: `${tokens.cardPaddingY}px ${tokens.cardPaddingX}px`,
              backgroundColor: "color-mix(in srgb, var(--background-text,#111827) 3%, white)",
            }}
          >
            <div
              className="absolute top-1/2 -translate-y-1/2 rounded-[16px]"
              style={{
                left: tokens.accentLeft,
                width: tokens.accentWidth,
                height: tokens.accentHeight,
                transform: "translateY(-50%) skewX(-22deg)",
                backgroundColor: "color-mix(in srgb, var(--primary-color,#3b82f6) 16%, transparent)",
              }}
              aria-hidden="true"
            />
            <div
              className="relative z-10 flex items-center justify-center bg-white shadow-[0_12px_32px_rgba(15,23,42,0.08)]"
              style={{
                width: tokens.iconAnchorSize,
                height: tokens.iconAnchorSize,
                borderRadius: tokens.iconAnchorRadius,
                border: "1px solid color-mix(in srgb, var(--primary-color,#3b82f6) 14%, transparent)",
                backgroundColor: "#fff",
              }}
            >
              <LayoutIcon
                query={item.icon.query}
                className="text-[var(--primary-color,#3b82f6)]"
                style={{
                  width: tokens.iconGlyphSize,
                  height: tokens.iconGlyphSize,
                }}
              />
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
                  fontSize: tokens.labelFontSize,
                  fontWeight: 700,
                  lineHeight: tokens.labelLineHeight,
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
                    paddingTop: tokens.labelSafetyPaddingTop,
                    paddingBottom: tokens.labelSafetyPaddingBottom,
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

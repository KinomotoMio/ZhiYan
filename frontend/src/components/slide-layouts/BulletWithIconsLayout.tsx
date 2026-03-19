"use client";

import { AlertCircle } from "lucide-react";

import { getBulletWithIconsLayoutTokens } from "@/lib/icon-card-layout-tokens";
import type { BulletWithIconsData } from "@/types/layout-data";

import { LayoutIcon } from "./_shared";

export const layoutId = "bullet-with-icons";
export const layoutName = "图标要点";
export const layoutDescription = "带图标的 3-4 个要点，适合功能介绍、优势列举";

export default function BulletWithIconsLayout({ data }: { data: BulletWithIconsData }) {
  const tokens = getBulletWithIconsLayoutTokens(data.items.length);

  if (data.status && data.items.length === 0) {
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
        <div className="flex flex-1 items-center justify-center">
          <div className="max-w-3xl rounded-3xl border border-amber-200 bg-amber-50 px-10 py-9 text-center shadow-sm">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-100 text-amber-600">
              <AlertCircle className="h-7 w-7" />
            </div>
            <h3
              style={{ fontSize: 24, fontWeight: 700, lineHeight: 1.3 }}
              className="text-[var(--background-text,#111827)]"
            >
              {data.status.title}
            </h3>
            <p
              style={{ fontSize: 17, lineHeight: 1.6 }}
              className="mt-3 text-[var(--background-text,#111827)]/70"
            >
              {data.status.message}
            </p>
          </div>
        </div>
      </div>
    );
  }

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
        className="grid flex-1 min-h-0"
        style={{
          gridTemplateColumns: `repeat(${tokens.columns}, minmax(0, 1fr))`,
          columnGap: tokens.gridColumnGap,
        }}
      >
        {data.items.map((item, i) => (
          <div
            key={i}
            className="relative flex h-full min-h-0 flex-col"
            style={{ paddingLeft: tokens.itemPaddingLeft }}
          >
            <div
              className="absolute left-0 top-1/2 -translate-y-1/2"
              style={{
                width: 1,
                height: tokens.dividerHeight,
                backgroundColor: "color-mix(in srgb, var(--background-text,#111827) 12%, transparent)",
              }}
            />
            <div
              className="flex min-h-0 flex-1 flex-col justify-center"
              style={{ paddingTop: tokens.itemPaddingY, paddingBottom: tokens.itemPaddingY }}
            >
              <div
                className="mb-4 flex items-center justify-center rounded-full"
                style={{
                  width: tokens.iconShellSize,
                  height: tokens.iconShellSize,
                  backgroundColor: "color-mix(in srgb, var(--primary-color,#3b82f6) 12%, white)",
                }}
              >
                <LayoutIcon
                  query={item.icon.query}
                  className="text-[var(--primary-color,#3b82f6)]"
                  style={{ width: tokens.iconGlyphSize, height: tokens.iconGlyphSize }}
                />
              </div>
              <h3
                style={{
                  fontSize: tokens.titleItemFontSize,
                  fontWeight: 700,
                  lineHeight: tokens.titleItemLineHeight,
                  letterSpacing: tokens.titleLetterSpacing,
                }}
                className="mb-2 min-w-0 text-[var(--primary-color,#3b82f6)]"
              >
                <span
                  style={{
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                    paddingTop: tokens.titleSafetyPaddingTop,
                    paddingBottom: tokens.titleSafetyPaddingBottom,
                  }}
                >
                  <span
                    style={{
                      backgroundColor: "color-mix(in srgb, var(--primary-color,#3b82f6) 7%, white)",
                      borderRadius: 3,
                      padding: `${tokens.titleHighlightPaddingTopEm}em ${tokens.titleHighlightPaddingXEm}em ${tokens.titleHighlightPaddingBottomEm}em`,
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
                    fontSize: tokens.descriptionFontSize,
                    lineHeight: tokens.descriptionLineHeight,
                    color: "color-mix(in srgb, var(--background-text,#111827) 72%, transparent)",
                  }}
                  className="max-w-[240px]"
                >
                  <span
                    style={{
                      display: "-webkit-box",
                      WebkitLineClamp: tokens.descriptionLineClamp,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                    }}
                  >
                    {item.description}
                  </span>
                </p>
              )}

              <div
                style={{
                  paddingTop: tokens.indexPaddingTop,
                  fontSize: tokens.indexFontSize,
                  fontWeight: 400,
                  lineHeight: tokens.indexLineHeight,
                  letterSpacing: "-0.06em",
                }}
                className="text-[var(--background-text,#111827)]"
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

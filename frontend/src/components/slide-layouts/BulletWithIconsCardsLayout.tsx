"use client";

import { getBulletWithIconsCardsLayoutTokens } from "@/lib/icon-card-layout-tokens";
import type { BulletWithIconsData } from "@/types/layout-data";

import { LayoutIcon } from "./_shared";

export const layoutId = "bullet-with-icons-cards";
export const layoutName = "图标要点（卡片）";
export const layoutDescription =
  "带图标的 3-4 个能力卡片，适合展示模块化功能、卖点和解决方案。";

export default function BulletWithIconsCardsLayout({ data }: { data: BulletWithIconsData }) {
  const tokens = getBulletWithIconsCardsLayoutTokens();

  return (
    <div
      className="flex h-full flex-col bg-[linear-gradient(180deg,var(--slide-bg-start,#ffffff)_0%,var(--slide-bg-end,#f8fafc)_100%)] text-[var(--background-text,#111827)]"
      style={{ padding: `${tokens.outerPaddingY}px ${tokens.outerPaddingX}px` }}
    >
      <h2
        style={{
          fontSize: tokens.titleFontSize,
          fontWeight: 800,
          lineHeight: tokens.titleLineHeight,
          letterSpacing: tokens.titleLetterSpacing,
          marginBottom: tokens.titleMarginBottom,
          maxWidth: tokens.titleMaxWidth,
        }}
      >
        {data.title}
      </h2>
      <div
        className="grid flex-1"
        style={{
          gridTemplateColumns: `repeat(${tokens.gridColumns}, minmax(0, 1fr))`,
          gap: tokens.gridGap,
        }}
      >
        {data.items.map((item, index) => (
          <article
            key={`${item.title}-${index}`}
            className="flex min-h-0 flex-col border border-slate-200 bg-white shadow-sm"
            style={{ borderRadius: tokens.cardRadius, padding: tokens.cardPadding }}
          >
            <div
              className="flex items-center justify-between gap-4"
              style={{ marginBottom: tokens.cardHeaderMarginBottom }}
            >
              <div
                className="flex items-center justify-center rounded-2xl bg-[color:color-mix(in_srgb,var(--primary-color,#3b82f6)_12%,white)] text-[var(--primary-color,#3b82f6)]"
                style={{ width: tokens.iconShellSize, height: tokens.iconShellSize }}
              >
                <LayoutIcon
                  query={item.icon.query}
                  style={{ width: tokens.iconGlyphSize, height: tokens.iconGlyphSize }}
                />
              </div>
              <div
                className="text-xs font-semibold uppercase text-slate-400"
                style={{ letterSpacing: tokens.indexLetterSpacing }}
              >
                {String(index + 1).padStart(2, "0")}
              </div>
            </div>
            <h3
              style={{
                fontSize: tokens.cardTitleFontSize,
                fontWeight: 700,
                lineHeight: tokens.cardTitleLineHeight,
                maxWidth: 360,
              }}
            >
              <span
                style={{
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                  paddingTop: tokens.cardTitleSafetyPaddingTop,
                  paddingBottom: tokens.cardTitleSafetyPaddingBottom,
                }}
              >
                {item.title}
              </span>
            </h3>
            <p
              className="text-slate-600"
              style={{
                marginTop: tokens.descriptionMarginTop,
                fontSize: tokens.descriptionFontSize,
                lineHeight: tokens.descriptionLineHeight,
              }}
            >
              {item.description}
            </p>
          </article>
        ))}
      </div>
    </div>
  );
}

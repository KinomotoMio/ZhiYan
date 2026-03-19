import { getBulletWithIconsColumns, isBulletIconsOnlyCompact } from "@/lib/layout-rules";

export interface BulletIconsOnlyLayoutTokens {
  compact: boolean;
  outerPaddingX: number;
  outerPaddingY: number;
  titleMarginBottom: number;
  titleFontSize: number;
  titleLineHeight: number;
  gridColumnGap: number;
  gridRowGap: number;
  cardMinHeight: number;
  cardPaddingX: number;
  cardPaddingY: number;
  accentWidth: number;
  accentHeight: number;
  accentLeft: number;
  iconAnchorSize: number;
  iconAnchorRadius: number;
  iconGlyphSize: number;
  labelFontSize: number;
  labelLineHeight: number;
  labelSafetyPaddingTop: number;
  labelSafetyPaddingBottom: number;
}

export interface BulletWithIconsLayoutTokens {
  columns: number;
  compact: boolean;
  outerPaddingX: number;
  outerPaddingY: number;
  titleMarginBottom: number;
  titleFontSize: number;
  titleLineHeight: number;
  titleLetterSpacing: string;
  gridColumnGap: number;
  itemPaddingLeft: number;
  itemPaddingY: number;
  dividerHeight: string;
  iconShellSize: number;
  iconGlyphSize: number;
  titleItemFontSize: number;
  titleItemLineHeight: number;
  titleSafetyPaddingTop: number;
  titleSafetyPaddingBottom: number;
  titleHighlightPaddingTopEm: number;
  titleHighlightPaddingXEm: number;
  titleHighlightPaddingBottomEm: number;
  descriptionFontSize: number;
  descriptionLineHeight: number;
  descriptionLineClamp: number;
  indexPaddingTop: number;
  indexFontSize: number;
  indexLineHeight: number;
}

export interface BulletWithIconsCardsLayoutTokens {
  outerPaddingX: number;
  outerPaddingY: number;
  titleMarginBottom: number;
  titleMaxWidth: number;
  titleFontSize: number;
  titleLineHeight: number;
  titleLetterSpacing: string;
  gridColumns: number;
  gridGap: number;
  cardRadius: number;
  cardPadding: number;
  cardHeaderMarginBottom: number;
  iconShellSize: number;
  iconGlyphSize: number;
  indexLetterSpacing: string;
  cardTitleFontSize: number;
  cardTitleLineHeight: number;
  cardTitleSafetyPaddingTop: number;
  cardTitleSafetyPaddingBottom: number;
  descriptionMarginTop: number;
  descriptionFontSize: number;
  descriptionLineHeight: number;
}

export function getBulletIconsOnlyLayoutTokens(itemCount: number): BulletIconsOnlyLayoutTokens {
  const compact = isBulletIconsOnlyCompact(itemCount);

  return {
    compact,
    outerPaddingX: 64,
    outerPaddingY: compact ? 48 : 56,
    titleMarginBottom: compact ? 24 : 32,
    titleFontSize: 36,
    titleLineHeight: 1.3,
    gridColumnGap: compact ? 28 : 40,
    gridRowGap: compact ? 16 : 22,
    cardMinHeight: compact ? 84 : 92,
    cardPaddingX: 24,
    cardPaddingY: compact ? 18 : 20,
    accentWidth: compact ? 88 : 96,
    accentHeight: compact ? 44 : 48,
    accentLeft: 28,
    iconAnchorSize: compact ? 68 : 72,
    iconAnchorRadius: compact ? 20 : 22,
    iconGlyphSize: compact ? 36 : 40,
    labelFontSize: compact ? 20 : 24,
    labelLineHeight: 1.12,
    labelSafetyPaddingTop: 2,
    labelSafetyPaddingBottom: 4,
  };
}

export function getBulletWithIconsLayoutTokens(itemCount: number): BulletWithIconsLayoutTokens {
  const columns = getBulletWithIconsColumns(itemCount);
  const compact = columns === 4;

  return {
    columns,
    compact,
    outerPaddingX: 64,
    outerPaddingY: 56,
    titleMarginBottom: 40,
    titleFontSize: 36,
    titleLineHeight: 1.3,
    titleLetterSpacing: "-0.04em",
    gridColumnGap: compact ? 18 : 26,
    itemPaddingLeft: 16,
    itemPaddingY: 8,
    dividerHeight: compact ? "46%" : "50%",
    iconShellSize: 40,
    iconGlyphSize: 20,
    titleItemFontSize: compact ? 19 : 21,
    titleItemLineHeight: 1.14,
    titleSafetyPaddingTop: 2,
    titleSafetyPaddingBottom: 4,
    titleHighlightPaddingTopEm: compact ? 0.06 : 0.07,
    titleHighlightPaddingXEm: compact ? 0.2 : 0.24,
    titleHighlightPaddingBottomEm: compact ? 0.14 : 0.16,
    descriptionFontSize: compact ? 11.5 : 12.5,
    descriptionLineHeight: 1.42,
    descriptionLineClamp: compact ? 4 : 5,
    indexPaddingTop: 16,
    indexFontSize: compact ? 52 : 60,
    indexLineHeight: 0.92,
  };
}

export function getBulletWithIconsCardsLayoutTokens(): BulletWithIconsCardsLayoutTokens {
  return {
    outerPaddingX: 64,
    outerPaddingY: 56,
    titleMarginBottom: 40,
    titleMaxWidth: 760,
    titleFontSize: 36,
    titleLineHeight: 1.2,
    titleLetterSpacing: "-0.04em",
    gridColumns: 2,
    gridGap: 24,
    cardRadius: 28,
    cardPadding: 28,
    cardHeaderMarginBottom: 24,
    iconShellSize: 48,
    iconGlyphSize: 24,
    indexLetterSpacing: "0.18em",
    cardTitleFontSize: 24,
    cardTitleLineHeight: 1.24,
    cardTitleSafetyPaddingTop: 2,
    cardTitleSafetyPaddingBottom: 4,
    descriptionMarginTop: 16,
    descriptionFontSize: 15,
    descriptionLineHeight: 1.7,
  };
}

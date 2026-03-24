/**
 * 模板注册中心 — layoutId → React 组件映射
 *
 * 前端根据 slide.layoutId 查找对应的 React 组件进行渲染。
 * 所有布局组件使用 CSS 变量接收主题色，容器负责缩放。
 */

import type { ComponentType } from "react";

import * as IntroSlide from "@/components/slide-layouts/IntroSlideLayout";
import * as IntroSlideLeft from "@/components/slide-layouts/IntroSlideLeftLayout";
import * as SectionHeader from "@/components/slide-layouts/SectionHeaderLayout";
import * as SectionHeaderSide from "@/components/slide-layouts/SectionHeaderSideLayout";
import * as OutlineSlide from "@/components/slide-layouts/OutlineSlideLayout";
import * as OutlineSlideRail from "@/components/slide-layouts/OutlineSlideRailLayout";
import * as BulletWithIcons from "@/components/slide-layouts/BulletWithIconsLayout";
import * as BulletWithIconsCards from "@/components/slide-layouts/BulletWithIconsCardsLayout";
import * as NumberedBullets from "@/components/slide-layouts/NumberedBulletsLayout";
import * as NumberedBulletsTrack from "@/components/slide-layouts/NumberedBulletsTrackLayout";
import * as MetricsSlide from "@/components/slide-layouts/MetricsSlideLayout";
import * as MetricsSlideBand from "@/components/slide-layouts/MetricsSlideBandLayout";
import * as MetricsWithImage from "@/components/slide-layouts/MetricsWithImageLayout";
import * as ChartWithBullets from "@/components/slide-layouts/ChartWithBulletsLayout";
import * as TableInfo from "@/components/slide-layouts/TableInfoLayout";
import * as TwoColumnCompare from "@/components/slide-layouts/TwoColumnCompareLayout";
import * as ImageAndDescription from "@/components/slide-layouts/ImageAndDescriptionLayout";
import * as Timeline from "@/components/slide-layouts/TimelineLayout";
import * as QuoteSlide from "@/components/slide-layouts/QuoteSlideLayout";
import * as QuoteBanner from "@/components/slide-layouts/QuoteBannerLayout";
import * as BulletIconsOnly from "@/components/slide-layouts/BulletIconsOnlyLayout";
import * as ChallengeOutcome from "@/components/slide-layouts/ChallengeOutcomeLayout";
import * as ThankYou from "@/components/slide-layouts/ThankYouLayout";
import * as ThankYouContact from "@/components/slide-layouts/ThankYouContactLayout";
import {
  getLayoutNotes,
  getLayoutTaxonomy,
  getVariantDefinition,
  type LayoutGroup,
  type LayoutDesignTraits,
  type LayoutSubGroup,
  type LayoutTemplateNotes,
  type LayoutVariantId,
} from "@/lib/layout-taxonomy";
import { getLayoutUsage, type LayoutUsageTag } from "@/lib/layout-usage";

export interface LayoutEntry {
  id: string;
  name: string;
  fileName: string;
  description: string;
  notes: LayoutTemplateNotes;
  group: LayoutGroup;
  subGroup: LayoutSubGroup;
  variantId: LayoutVariantId;
  variantLabel: string;
  variantDescription: string;
  designTraits: LayoutDesignTraits;
  isVariantDefault: boolean;
  usage: LayoutUsageTag[];
  component: ComponentType<{ data: Record<string, unknown> }>;
}

interface LayoutModule {
  layoutId: string;
  layoutName: string;
  layoutDescription: string;
  default: ComponentType<{ data: Record<string, unknown> }>;
}

interface RegisteredLayoutModule {
  fileName: string;
  module: LayoutModule;
}

const allModules: RegisteredLayoutModule[] = [
  { fileName: "IntroSlideLayout.tsx", module: IntroSlide as unknown as LayoutModule },
  { fileName: "IntroSlideLeftLayout.tsx", module: IntroSlideLeft as unknown as LayoutModule },
  { fileName: "SectionHeaderLayout.tsx", module: SectionHeader as unknown as LayoutModule },
  { fileName: "SectionHeaderSideLayout.tsx", module: SectionHeaderSide as unknown as LayoutModule },
  { fileName: "OutlineSlideLayout.tsx", module: OutlineSlide as unknown as LayoutModule },
  { fileName: "OutlineSlideRailLayout.tsx", module: OutlineSlideRail as unknown as LayoutModule },
  { fileName: "BulletWithIconsLayout.tsx", module: BulletWithIcons as unknown as LayoutModule },
  { fileName: "BulletWithIconsCardsLayout.tsx", module: BulletWithIconsCards as unknown as LayoutModule },
  { fileName: "NumberedBulletsLayout.tsx", module: NumberedBullets as unknown as LayoutModule },
  { fileName: "NumberedBulletsTrackLayout.tsx", module: NumberedBulletsTrack as unknown as LayoutModule },
  { fileName: "MetricsSlideLayout.tsx", module: MetricsSlide as unknown as LayoutModule },
  { fileName: "MetricsSlideBandLayout.tsx", module: MetricsSlideBand as unknown as LayoutModule },
  { fileName: "MetricsWithImageLayout.tsx", module: MetricsWithImage as unknown as LayoutModule },
  { fileName: "ChartWithBulletsLayout.tsx", module: ChartWithBullets as unknown as LayoutModule },
  { fileName: "TableInfoLayout.tsx", module: TableInfo as unknown as LayoutModule },
  { fileName: "TwoColumnCompareLayout.tsx", module: TwoColumnCompare as unknown as LayoutModule },
  { fileName: "ImageAndDescriptionLayout.tsx", module: ImageAndDescription as unknown as LayoutModule },
  { fileName: "TimelineLayout.tsx", module: Timeline as unknown as LayoutModule },
  { fileName: "QuoteSlideLayout.tsx", module: QuoteSlide as unknown as LayoutModule },
  { fileName: "QuoteBannerLayout.tsx", module: QuoteBanner as unknown as LayoutModule },
  { fileName: "BulletIconsOnlyLayout.tsx", module: BulletIconsOnly as unknown as LayoutModule },
  { fileName: "ChallengeOutcomeLayout.tsx", module: ChallengeOutcome as unknown as LayoutModule },
  { fileName: "ThankYouLayout.tsx", module: ThankYou as unknown as LayoutModule },
  { fileName: "ThankYouContactLayout.tsx", module: ThankYouContact as unknown as LayoutModule },
];

const _registry = new Map<string, LayoutEntry>();
let _initialized = false;

function ensureInitialized() {
  if (_initialized) return;
  _initialized = true;

  for (const { fileName, module: mod } of allModules) {
    if (!mod.layoutId || !mod.default) continue;
    const taxonomy = getLayoutTaxonomy(mod.layoutId);
    const notes = getLayoutNotes(mod.layoutId);
    if (!taxonomy || !notes) continue;
    const variant = getVariantDefinition(
      taxonomy.group,
      taxonomy.subGroup,
      taxonomy.variantId,
    );
    if (!variant) continue;
    _registry.set(mod.layoutId, {
      id: mod.layoutId,
      name: mod.layoutName || mod.layoutId,
      fileName,
      description: notes.purpose,
      notes,
      group: taxonomy.group,
      subGroup: taxonomy.subGroup,
      variantId: taxonomy.variantId,
      variantLabel: variant.label,
      variantDescription: variant.description,
      designTraits: variant.designTraits,
      isVariantDefault: taxonomy.isVariantDefault,
      usage: getLayoutUsage(mod.layoutId),
      component: mod.default,
    });
  }
}

/**
 * 获取布局组件
 */
export function getLayoutComponent(
  layoutId: string,
): ComponentType<{ data: Record<string, unknown> }> | null {
  ensureInitialized();
  return _registry.get(layoutId)?.component ?? null;
}

/**
 * 获取布局条目
 */
export function getLayout(layoutId: string): LayoutEntry | null {
  ensureInitialized();
  return _registry.get(layoutId) ?? null;
}

/**
 * 获取所有已注册布局
 */
export function getAllLayouts(): LayoutEntry[] {
  ensureInitialized();
  return Array.from(_registry.values());
}

/**
 * 检查是否存在某布局
 */
export function hasLayout(layoutId: string): boolean {
  ensureInitialized();
  return _registry.has(layoutId);
}

/**
 * 获取所有布局 ID
 */
export function getLayoutIds(): string[] {
  ensureInitialized();
  return Array.from(_registry.keys());
}

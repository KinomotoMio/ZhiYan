/**
 * 模板注册中心 — layoutId → React 组件映射
 *
 * 前端根据 slide.layoutId 查找对应的 React 组件进行渲染。
 * 所有布局组件使用 CSS 变量接收主题色，容器负责缩放。
 */

import type { ComponentType } from "react";

import * as IntroSlide from "@/components/slide-layouts/IntroSlideLayout";
import * as SectionHeader from "@/components/slide-layouts/SectionHeaderLayout";
import * as OutlineSlide from "@/components/slide-layouts/OutlineSlideLayout";
import * as BulletWithIcons from "@/components/slide-layouts/BulletWithIconsLayout";
import * as NumberedBullets from "@/components/slide-layouts/NumberedBulletsLayout";
import * as MetricsSlide from "@/components/slide-layouts/MetricsSlideLayout";
import * as MetricsWithImage from "@/components/slide-layouts/MetricsWithImageLayout";
import * as ChartWithBullets from "@/components/slide-layouts/ChartWithBulletsLayout";
import * as TableInfo from "@/components/slide-layouts/TableInfoLayout";
import * as TwoColumnCompare from "@/components/slide-layouts/TwoColumnCompareLayout";
import * as ImageAndDescription from "@/components/slide-layouts/ImageAndDescriptionLayout";
import * as Timeline from "@/components/slide-layouts/TimelineLayout";
import * as QuoteSlide from "@/components/slide-layouts/QuoteSlideLayout";
import * as BulletIconsOnly from "@/components/slide-layouts/BulletIconsOnlyLayout";
import * as ChallengeOutcome from "@/components/slide-layouts/ChallengeOutcomeLayout";
import * as ThankYou from "@/components/slide-layouts/ThankYouLayout";
import { getLayoutRole, type LayoutRole } from "@/lib/layout-role";
import { getLayoutUsage, type LayoutUsageTag } from "@/lib/layout-usage";
import { getLayoutVariant, type LayoutVariant } from "@/lib/layout-variant";

export interface LayoutEntry {
  id: string;
  name: string;
  description: string;
  group: LayoutRole;
  variant: LayoutVariant;
  usage: LayoutUsageTag[];
  component: ComponentType<{ data: Record<string, unknown> }>;
}

interface LayoutModule {
  layoutId: string;
  layoutName: string;
  layoutDescription: string;
  default: ComponentType<{ data: Record<string, unknown> }>;
}

const allModules: LayoutModule[] = [
  IntroSlide as unknown as LayoutModule,
  SectionHeader as unknown as LayoutModule,
  OutlineSlide as unknown as LayoutModule,
  BulletWithIcons as unknown as LayoutModule,
  NumberedBullets as unknown as LayoutModule,
  MetricsSlide as unknown as LayoutModule,
  MetricsWithImage as unknown as LayoutModule,
  ChartWithBullets as unknown as LayoutModule,
  TableInfo as unknown as LayoutModule,
  TwoColumnCompare as unknown as LayoutModule,
  ImageAndDescription as unknown as LayoutModule,
  Timeline as unknown as LayoutModule,
  QuoteSlide as unknown as LayoutModule,
  BulletIconsOnly as unknown as LayoutModule,
  ChallengeOutcome as unknown as LayoutModule,
  ThankYou as unknown as LayoutModule,
];

const _registry = new Map<string, LayoutEntry>();
let _initialized = false;

function ensureInitialized() {
  if (_initialized) return;
  _initialized = true;

  for (const mod of allModules) {
    if (!mod.layoutId || !mod.default) continue;
    _registry.set(mod.layoutId, {
      id: mod.layoutId,
      name: mod.layoutName || mod.layoutId,
      description: mod.layoutDescription || "",
      group: getLayoutRole(mod.layoutId),
      variant: getLayoutVariant(mod.layoutId),
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

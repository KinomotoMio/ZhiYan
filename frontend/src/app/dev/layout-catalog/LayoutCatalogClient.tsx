"use client";

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
import {
  compareLayoutRoles,
  type LayoutRole,
} from "@/lib/layout-role";
import {
  getLayoutGroupDescription,
  getLayoutGroupLabel,
  getLayoutSubGroupDescription,
  getLayoutSubGroupLabel,
  getLayoutSubGroupsForGroup,
  getLayoutVariantAxisDescription,
  getLayoutVariantAxisLabel,
  LAYOUT_GROUP_ORDER,
  type LayoutVariantObject,
} from "@/lib/layout-taxonomy";
import {
  getLayoutUsage,
  getUsageLabel,
  type LayoutUsageTag,
} from "@/lib/layout-usage";
import { compareLayoutNames } from "@/lib/sort";
import {
  getLayoutVariant,
  getLayoutVariantDescription,
  getLayoutVariantLabel,
  getLayoutVariantsForRole,
  type LayoutVariant,
} from "@/lib/layout-variant";
import { getLayout, type LayoutEntry as RegistryLayoutEntry } from "@/lib/template-registry";

type LayoutModule = {
  default: ComponentType<{ data: Record<string, unknown> }>;
  layoutId: string;
  layoutName: string;
  layoutDescription: string;
};

type CatalogEntry = {
  module: LayoutModule;
  fileName: string;
  schemaName: string;
  group: LayoutRole;
  subGroup: RegistryLayoutEntry["subGroup"];
  variant: LayoutVariantObject;
  runtimeVariant: LayoutVariant;
  usage: LayoutUsageTag[];
  keyFields: string[];
  data: Record<string, unknown>;
};

function getCatalogLayout(layoutId: string): RegistryLayoutEntry {
  const entry = getLayout(layoutId);
  if (!entry) {
    throw new Error(`Missing registry entry for layout ${layoutId}`);
  }
  return entry;
}

function svgDataUrl(stops: string[], label: string): string {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
      <defs>
        <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="${stops[0]}"/>
          <stop offset="100%" stop-color="${stops[1]}"/>
        </linearGradient>
      </defs>
      <rect width="1280" height="720" fill="url(#g)"/>
      <circle cx="1040" cy="160" r="140" fill="rgba(255,255,255,0.14)"/>
      <circle cx="180" cy="560" r="180" fill="rgba(255,255,255,0.12)"/>
      <text x="96" y="602" fill="white" font-family="Arial, sans-serif" font-size="56" font-weight="700">${label}</text>
    </svg>
  `;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

const photoA = svgDataUrl(["#1d4ed8", "#06b6d4"], "Product View");
const photoB = svgDataUrl(["#0f766e", "#65a30d"], "Dashboard");

const entries: CatalogEntry[] = [
  {
    module: IntroSlide as unknown as LayoutModule,
    fileName: "IntroSlideLayout.tsx",
    schemaName: "IntroSlideData",
    group: getCatalogLayout("intro-slide").group,
    subGroup: getCatalogLayout("intro-slide").subGroup,
    variant: getCatalogLayout("intro-slide").variant,
    runtimeVariant: getLayoutVariant("intro-slide"),
    usage: getLayoutUsage("intro-slide"),
    keyFields: ["title", "subtitle", "author?", "date?"],
    data: {
      title: "ZhiYan Layout Catalog",
      subtitle: "Preview every built-in layout with sample content.",
      author: "Codex",
      date: "2026-03-11",
    },
  },
  {
    module: OutlineSlide as unknown as LayoutModule,
    fileName: "OutlineSlideLayout.tsx",
    schemaName: "OutlineSlideData",
    group: getCatalogLayout("outline-slide").group,
    subGroup: getCatalogLayout("outline-slide").subGroup,
    variant: getCatalogLayout("outline-slide").variant,
    runtimeVariant: getLayoutVariant("outline-slide"),
    usage: getLayoutUsage("outline-slide"),
    keyFields: ["title", "subtitle?", "sections[4-6]"],
    data: {
      title: "Presentation Outline",
      subtitle:
        "A navigation page that frames the full report structure before the detailed sections begin.",
      sections: [
        {
          title: "Background",
          description: "Business context and project motivation",
        },
        {
          title: "Method",
          description: "Approach, data sources, and evaluation logic",
        },
        {
          title: "Findings",
          description: "Key observations and critical metrics",
        },
        {
          title: "Results",
          description: "Outcome summary and measurable impact",
        },
      ],
    },
  },
  {
    module: SectionHeader as unknown as LayoutModule,
    fileName: "SectionHeaderLayout.tsx",
    schemaName: "SectionHeaderData",
    group: getCatalogLayout("section-header").group,
    subGroup: getCatalogLayout("section-header").subGroup,
    variant: getCatalogLayout("section-header").variant,
    runtimeVariant: getLayoutVariant("section-header"),
    usage: getLayoutUsage("section-header"),
    keyFields: ["title", "subtitle?"],
    data: {
      title: "Platform Overview",
      subtitle: "A clean transition slide between major chapters.",
    },
  },
  {
    module: BulletWithIcons as unknown as LayoutModule,
    fileName: "BulletWithIconsLayout.tsx",
    schemaName: "BulletWithIconsData",
    group: getCatalogLayout("bullet-with-icons").group,
    subGroup: getCatalogLayout("bullet-with-icons").subGroup,
    variant: getCatalogLayout("bullet-with-icons").variant,
    runtimeVariant: getLayoutVariant("bullet-with-icons"),
    usage: getLayoutUsage("bullet-with-icons"),
    keyFields: ["title", "items[3-4]"],
    data: {
      title: "Why Teams Use This Layout",
      items: [
        {
          icon: { query: "sparkles" },
          title: "Scannable",
          description:
            "Each point gets a visual anchor and one concise explanation.",
        },
        {
          icon: { query: "blocks" },
          title: "Balanced",
          description:
            "Works well for three or four capabilities on one slide.",
        },
        {
          icon: { query: "shield-check" },
          title: "Reliable",
          description: "Predictable spacing keeps the page from feeling crowded.",
        },
      ],
    },
  },
  {
    module: ImageAndDescription as unknown as LayoutModule,
    fileName: "ImageAndDescriptionLayout.tsx",
    schemaName: "ImageAndDescriptionData",
    group: getCatalogLayout("image-and-description").group,
    subGroup: getCatalogLayout("image-and-description").subGroup,
    variant: getCatalogLayout("image-and-description").variant,
    runtimeVariant: getLayoutVariant("image-and-description"),
    usage: getLayoutUsage("image-and-description"),
    keyFields: ["title", "image", "description", "bullets?"],
    data: {
      title: "Feature Spotlight",
      image: { prompt: "hero product mockup", url: photoA, alt: "product preview" },
      description:
        "This layout works when one image should do most of the emotional work, with the text explaining why it matters.",
      bullets: [
        "Strong for demos and case studies",
        "Keeps the message focused",
        "Easy to theme with photography",
      ],
    },
  },
  {
    module: BulletIconsOnly as unknown as LayoutModule,
    fileName: "BulletIconsOnlyLayout.tsx",
    schemaName: "BulletIconsOnlyData",
    group: getCatalogLayout("bullet-icons-only").group,
    subGroup: getCatalogLayout("bullet-icons-only").subGroup,
    variant: getCatalogLayout("bullet-icons-only").variant,
    runtimeVariant: getLayoutVariant("bullet-icons-only"),
    usage: getLayoutUsage("bullet-icons-only"),
    keyFields: ["title", "items[4-8]"],
    data: {
      title: "Capability Grid",
      items: [
        { icon: { query: "database" }, label: "Source ingest" },
        { icon: { query: "message-square" }, label: "Chat edits" },
        { icon: { query: "image" }, label: "Asset prompts" },
        { icon: { query: "file-chart-column" }, label: "Export" },
        { icon: { query: "sparkles" }, label: "Themeing" },
        { icon: { query: "shield-check" }, label: "Verification" },
      ],
    },
  },
  {
    module: MetricsSlide as unknown as LayoutModule,
    fileName: "MetricsSlideLayout.tsx",
    schemaName: "MetricsSlideData",
    group: getCatalogLayout("metrics-slide").group,
    subGroup: getCatalogLayout("metrics-slide").subGroup,
    variant: getCatalogLayout("metrics-slide").variant,
    runtimeVariant: getLayoutVariant("metrics-slide"),
    usage: getLayoutUsage("metrics-slide"),
    keyFields: ["title", "metrics[2-4]"],
    data: {
      title: "Quarterly Snapshot",
      metrics: [
        { value: "92%", label: "Adoption", description: "active team usage" },
        { value: "14d", label: "Lead Time", description: "from brief to deck" },
        { value: "3.6x", label: "Reuse", description: "template leverage" },
      ],
    },
  },
  {
    module: MetricsWithImage as unknown as LayoutModule,
    fileName: "MetricsWithImageLayout.tsx",
    schemaName: "MetricsWithImageData",
    group: getCatalogLayout("metrics-with-image").group,
    subGroup: getCatalogLayout("metrics-with-image").subGroup,
    variant: getCatalogLayout("metrics-with-image").variant,
    runtimeVariant: getLayoutVariant("metrics-with-image"),
    usage: getLayoutUsage("metrics-with-image"),
    keyFields: ["title", "metrics[2-3]", "image"],
    data: {
      title: "Impact + Product Shot",
      metrics: [
        {
          value: "48%",
          label: "Faster review",
          description: "less manual cleanup",
        },
        {
          value: "11",
          label: "Teams onboarded",
          description: "within two sprints",
        },
        { value: "4.8/5", label: "Satisfaction", description: "pilot feedback" },
      ],
      image: {
        prompt: "analytics dashboard",
        url: photoB,
        alt: "dashboard preview",
      },
    },
  },
  {
    module: ChartWithBullets as unknown as LayoutModule,
    fileName: "ChartWithBulletsLayout.tsx",
    schemaName: "ChartWithBulletsData",
    group: getCatalogLayout("chart-with-bullets").group,
    subGroup: getCatalogLayout("chart-with-bullets").subGroup,
    variant: getCatalogLayout("chart-with-bullets").variant,
    runtimeVariant: getLayoutVariant("chart-with-bullets"),
    usage: getLayoutUsage("chart-with-bullets"),
    keyFields: ["title", "chart", "bullets[2-4]"],
    data: {
      title: "Trend + Commentary",
      chart: {
        chartType: "bar",
        labels: ["Q1", "Q2", "Q3", "Q4"],
        datasets: [{ label: "Growth", data: [12, 18, 24, 31] }],
      },
      bullets: [
        { text: "Usage climbs steadily after template standardization." },
        { text: "The largest jump happens once review loops are shortened." },
        { text: "Best used when one chart needs 2-3 plain-language takeaways." },
      ],
    },
  },
  {
    module: TableInfo as unknown as LayoutModule,
    fileName: "TableInfoLayout.tsx",
    schemaName: "TableInfoData",
    group: getCatalogLayout("table-info").group,
    subGroup: getCatalogLayout("table-info").subGroup,
    variant: getCatalogLayout("table-info").variant,
    runtimeVariant: getLayoutVariant("table-info"),
    usage: getLayoutUsage("table-info"),
    keyFields: ["title", "headers", "rows", "caption?"],
    data: {
      title: "Option Comparison",
      headers: ["Option", "Speed", "Control", "Best For"],
      rows: [
        ["Default", "Fast", "Low", "simple briefs"],
        ["Custom", "Medium", "High", "brand-heavy decks"],
        ["Hybrid", "Fast", "Medium", "most teams"],
      ],
      caption: "A compact matrix for structured comparisons.",
    },
  },
  {
    module: TwoColumnCompare as unknown as LayoutModule,
    fileName: "TwoColumnCompareLayout.tsx",
    schemaName: "TwoColumnCompareData",
    group: getCatalogLayout("two-column-compare").group,
    subGroup: getCatalogLayout("two-column-compare").subGroup,
    variant: getCatalogLayout("two-column-compare").variant,
    runtimeVariant: getLayoutVariant("two-column-compare"),
    usage: getLayoutUsage("two-column-compare"),
    keyFields: ["title", "left", "right"],
    data: {
      title: "Manual vs Assisted Workflow",
      left: {
        heading: "Manual",
        icon: { query: "pen-tool" },
        items: ["Slower setup", "Inconsistent page rhythm", "Harder to reuse"],
      },
      right: {
        heading: "Assisted",
        icon: { query: "bot" },
        items: [
          "Faster first draft",
          "Repeatable layout system",
          "Easier to refine",
        ],
      },
    },
  },
  {
    module: ChallengeOutcome as unknown as LayoutModule,
    fileName: "ChallengeOutcomeLayout.tsx",
    schemaName: "ChallengeOutcomeData",
    group: getCatalogLayout("challenge-outcome").group,
    subGroup: getCatalogLayout("challenge-outcome").subGroup,
    variant: getCatalogLayout("challenge-outcome").variant,
    runtimeVariant: getLayoutVariant("challenge-outcome"),
    usage: getLayoutUsage("challenge-outcome"),
    keyFields: ["title", "items[2-4]"],
    data: {
      title: "Problems and Fixes",
      items: [
        {
          challenge: "Slides feel visually inconsistent across authors.",
          outcome: "Use a constrained layout library with schema-guided content.",
        },
        {
          challenge: "Reviewers spend time fixing spacing and hierarchy.",
          outcome: "Push style decisions into reusable TSX layouts.",
        },
      ],
    },
  },
  {
    module: NumberedBullets as unknown as LayoutModule,
    fileName: "NumberedBulletsLayout.tsx",
    schemaName: "NumberedBulletsData",
    group: getCatalogLayout("numbered-bullets").group,
    subGroup: getCatalogLayout("numbered-bullets").subGroup,
    variant: getCatalogLayout("numbered-bullets").variant,
    runtimeVariant: getLayoutVariant("numbered-bullets"),
    usage: getLayoutUsage("numbered-bullets"),
    keyFields: ["title", "items[3-5]"],
    data: {
      title: "Rollout Plan",
      items: [
        {
          title: "Collect input",
          description:
            "Gather source docs, goals, and constraints from the team.",
        },
        {
          title: "Draft structure",
          description:
            "Turn raw material into a short narrative with a clear order.",
        },
        {
          title: "Polish visuals",
          description: "Pick a layout, tune wording, and verify readability.",
        },
      ],
    },
  },
  {
    module: Timeline as unknown as LayoutModule,
    fileName: "TimelineLayout.tsx",
    schemaName: "TimelineData",
    group: getCatalogLayout("timeline").group,
    subGroup: getCatalogLayout("timeline").subGroup,
    variant: getCatalogLayout("timeline").variant,
    runtimeVariant: getLayoutVariant("timeline"),
    usage: getLayoutUsage("timeline"),
    keyFields: ["title", "events[3-6]"],
    data: {
      title: "Delivery Timeline",
      events: [
        {
          date: "Week 1",
          title: "Research",
          description: "Audit current layouts and sample decks.",
        },
        {
          date: "Week 2",
          title: "Prototype",
          description: "Add new layout components and schemas.",
        },
        {
          date: "Week 3",
          title: "Validate",
          description: "Run generation checks and visual review.",
        },
        {
          date: "Week 4",
          title: "Ship",
          description: "Document patterns and hand off to the team.",
        },
      ],
    },
  },
  {
    module: QuoteSlide as unknown as LayoutModule,
    fileName: "QuoteSlideLayout.tsx",
    schemaName: "QuoteSlideData",
    group: getCatalogLayout("quote-slide").group,
    subGroup: getCatalogLayout("quote-slide").subGroup,
    variant: getCatalogLayout("quote-slide").variant,
    runtimeVariant: getLayoutVariant("quote-slide"),
    usage: getLayoutUsage("quote-slide"),
    keyFields: ["quote", "author?", "context?"],
    data: {
      quote:
        "A layout system is just a promise that content will land in a predictable, readable place.",
      author: "Design review note",
      context: "internal principle",
    },
  },
  {
    module: ThankYou as unknown as LayoutModule,
    fileName: "ThankYouLayout.tsx",
    schemaName: "ThankYouData",
    group: getCatalogLayout("thank-you").group,
    subGroup: getCatalogLayout("thank-you").subGroup,
    variant: getCatalogLayout("thank-you").variant,
    runtimeVariant: getLayoutVariant("thank-you"),
    usage: getLayoutUsage("thank-you"),
    keyFields: ["title", "subtitle?", "contact?"],
    data: {
      title: "Thanks",
      subtitle: "Questions, feedback, or layout ideas are welcome.",
      contact: "design-system@zhiyan.local",
    },
  },
];

const sortedEntries = [...entries].sort((left, right) => {
  const roleDelta = compareLayoutRoles(left.group, right.group);
  if (roleDelta !== 0) return roleDelta;
  const subGroupDelta = compareSubGroups(
    left.group,
    left.subGroup,
    right.subGroup,
    left.module.layoutId,
    right.module.layoutId,
  );
  if (subGroupDelta !== 0) return subGroupDelta;
  const variantDelta = compareVariantObjects(
    left.variant,
    right.variant,
    left.module.layoutId,
    right.module.layoutId,
  );
  if (variantDelta !== 0) return variantDelta;
  return compareLayoutNames(
    left.module.layoutName,
    right.module.layoutName,
    left.module.layoutId,
    right.module.layoutId,
  );
});

const narrativeVariants = getLayoutVariantsForRole("narrative");

function compareSubGroups(
  group: LayoutRole,
  left: RegistryLayoutEntry["subGroup"],
  right: RegistryLayoutEntry["subGroup"],
  leftId: string,
  rightId: string,
): number {
  const orderedSubGroups = getLayoutSubGroupsForGroup(group);
  const leftIndex = orderedSubGroups.indexOf(left);
  const rightIndex = orderedSubGroups.indexOf(right);

  if (leftIndex !== -1 || rightIndex !== -1) {
    if (leftIndex === -1) return 1;
    if (rightIndex === -1) return -1;
    if (leftIndex !== rightIndex) return leftIndex - rightIndex;
  }

  return compareLayoutNames(left, right, leftId, rightId);
}

function compareVariantObjects(
  left: LayoutVariantObject,
  right: LayoutVariantObject,
  leftId: string,
  rightId: string,
): number {
  const axes: Array<keyof LayoutVariantObject> = [
    "composition",
    "tone",
    "style",
    "density",
  ];

  for (const axis of axes) {
    const delta = compareLayoutNames(left[axis], right[axis], leftId, rightId);
    if (delta !== 0) return delta;
  }

  return 0;
}

function PreviewFrame({
  Component,
  data,
}: {
  Component: ComponentType<{ data: Record<string, unknown> }>;
  data: Record<string, unknown>;
}) {
  return (
    <div className="w-80 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div
        className="origin-top-left bg-[var(--background-color,#ffffff)]"
        style={{
          width: 1280,
          height: 720,
          transform: "scale(0.25)",
          transformOrigin: "top left",
          marginBottom: -540,
          ["--primary-color" as string]: "#2563eb",
          ["--primary-text" as string]: "#ffffff",
          ["--background-color" as string]: "#ffffff",
          ["--background-text" as string]: "#0f172a",
        }}
      >
        <Component data={data} />
      </div>
    </div>
  );
}

function UsageChips({ usage }: { usage: LayoutUsageTag[] }) {
  return (
    <div className="flex flex-wrap gap-2">
      {usage.map((tag) => (
        <span
          key={tag}
          className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700"
        >
          {getUsageLabel(tag)}
        </span>
      ))}
    </div>
  );
}

function RuntimeVariantBadge({
  role,
  variant,
}: {
  role: LayoutRole;
  variant: LayoutVariant;
}) {
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">
          Compatibility shim
        </span>
        <span className="rounded-full bg-violet-50 px-2.5 py-1 text-xs font-medium text-violet-700">
          {getLayoutVariantLabel(role, variant)}
        </span>
      </div>
      <code className="mt-2 block text-xs text-slate-500">{variant}</code>
      <p className="mt-2 text-sm leading-6 text-slate-600">
        {getLayoutVariantDescription(role, variant)}
      </p>
    </div>
  );
}

function SubGroupBadge({
  group,
  subGroup,
}: {
  group: LayoutRole;
  subGroup: RegistryLayoutEntry["subGroup"];
}) {
  return (
    <div>
      <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700">
        {getLayoutSubGroupLabel(group, subGroup)}
      </span>
      <code className="mt-2 block text-xs text-slate-500">{subGroup}</code>
      <p className="mt-2 text-sm leading-6 text-slate-700">
        {getLayoutSubGroupDescription(group, subGroup)}
      </p>
    </div>
  );
}

function VariantCard({
  variant,
}: {
  variant: LayoutVariantObject;
}) {
  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-700">
          Canonical variant
        </span>
        <span className="text-xs text-emerald-800">
          composition / tone / style / density
        </span>
      </div>
      <dl className="mt-3 grid gap-3 sm:grid-cols-2">
        <div>
          <dt className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">
            composition
          </dt>
          <dd className="mt-1 rounded bg-white px-2 py-1 text-sm text-slate-800">
            {getLayoutVariantAxisLabel("composition", variant.composition)}
            <code className="mt-1 block text-xs text-slate-500">{variant.composition}</code>
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">
            tone
          </dt>
          <dd className="mt-1 rounded bg-white px-2 py-1 text-sm text-slate-800">
            {getLayoutVariantAxisLabel("tone", variant.tone)}
            <code className="mt-1 block text-xs text-slate-500">{variant.tone}</code>
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">
            style
          </dt>
          <dd className="mt-1 rounded bg-white px-2 py-1 text-sm text-slate-800">
            {getLayoutVariantAxisLabel("style", variant.style)}
            <code className="mt-1 block text-xs text-slate-500">{variant.style}</code>
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">
            density
          </dt>
          <dd className="mt-1 rounded bg-white px-2 py-1 text-sm text-slate-800">
            {getLayoutVariantAxisLabel("density", variant.density)}
            <code className="mt-1 block text-xs text-slate-500">{variant.density}</code>
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-xs leading-5 text-emerald-900">
        {[
          getLayoutVariantAxisDescription("composition", variant.composition),
          getLayoutVariantAxisDescription("tone", variant.tone),
          getLayoutVariantAxisDescription("style", variant.style),
          getLayoutVariantAxisDescription("density", variant.density),
        ]
          .filter(Boolean)
          .join(" ")}
      </p>
    </div>
  );
}

export function LayoutCatalogClientPage() {
  return (
    <main className="min-h-screen bg-slate-50 px-6 py-8 text-slate-900">
      <div className="mx-auto max-w-[1880px]">
        <header className="mb-8">
          <p className="mb-2 text-sm font-medium uppercase tracking-[0.2em] text-slate-500">
            Local Catalog
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">
            Built-in slide layouts
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            This page renders every current TSX layout with sample data. Use it
            as a taxonomy-first review workspace: compare each template&apos;s
            page function, information structure, design variant, and current
            compatibility metadata in one place.
          </p>
        </header>

        <section className="mb-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="max-w-4xl">
            <h2 className="text-lg font-semibold text-slate-900">
              Taxonomy-first review workspace
            </h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              `group` defines the page&apos;s job in the deck, `sub-group`
              captures the information structure, and `variant` captures the
              design layer through `composition`, `tone`, `style`, and
              `density`. The old runtime `variant` string is still visible
              below, but only as a migration-time compatibility shim.
            </p>
          </div>
          <div className="mt-5 grid gap-4 lg:grid-cols-3">
            <article className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <h3 className="text-sm font-semibold text-slate-900">Group</h3>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                Page function in the overall deck skeleton. This is the first
                routing layer when teams compare layouts.
              </p>
            </article>
            <article className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <h3 className="text-sm font-semibold text-slate-900">Sub-group</h3>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                Structure layer inside one group. `narrative` is currently the
                only group with non-default sub-groups.
              </p>
            </article>
            <article className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <h3 className="text-sm font-semibold text-slate-900">Variant</h3>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                Design layer on top of `group + sub-group`, expressed as a
                four-field object. This is now the canonical source of truth.
              </p>
            </article>
          </div>
          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {LAYOUT_GROUP_ORDER.map((role) => (
              <article
                key={role}
                className="rounded-xl border border-slate-200 bg-slate-50 p-4"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
                    {getLayoutGroupLabel(role)}
                  </span>
                </div>
                <code className="mt-3 block text-xs text-slate-500">{role}</code>
                <p className="mt-2 text-sm leading-6 text-slate-700">
                  {getLayoutGroupDescription(role)}
                </p>
              </article>
            ))}
          </div>
        </section>

        <section className="mb-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="max-w-3xl">
            <h2 className="text-lg font-semibold text-slate-900">
              Compatibility runtime view
            </h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              The runtime `variant` string is still exposed so older callers can
              keep working. It is no longer the primary taxonomy model, and only
              `narrative` currently maps to non-default compatibility variants.
            </p>
          </div>
          <div className="mt-5 grid gap-4 xl:grid-cols-3">
            {narrativeVariants.map((variant) => (
              <article
                key={variant}
                className="rounded-xl border border-slate-200 bg-slate-50 p-4"
              >
                <RuntimeVariantBadge role="narrative" variant={variant} />
              </article>
            ))}
          </div>
        </section>

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-[2440px] table-fixed border-collapse">
            <thead className="bg-slate-100 text-left text-xs uppercase tracking-[0.16em] text-slate-500">
              <tr>
                <th className="w-[360px] px-5 py-4">Preview</th>
                <th className="w-[190px] px-5 py-4">Layout</th>
                <th className="w-[250px] px-5 py-4">TSX File</th>
                <th className="w-[210px] px-5 py-4">Schema</th>
                <th className="w-[140px] px-5 py-4">Group</th>
                <th className="w-[220px] px-5 py-4">Sub-group</th>
                <th className="w-[340px] px-5 py-4">Variant</th>
                <th className="w-[240px] px-5 py-4">Runtime Variant</th>
                <th className="w-[280px] px-5 py-4">Usage</th>
                <th className="px-5 py-4">Notes</th>
              </tr>
            </thead>
              <tbody>
                {sortedEntries.map((entry) => {
                  const Component = entry.module.default;
                  return (
                    <tr
                      key={entry.module.layoutId}
                      className="border-t border-slate-200 align-top"
                    >
                      <td className="px-5 py-5">
                        <PreviewFrame Component={Component} data={entry.data} />
                      </td>
                      <td className="px-5 py-5">
                        <div className="text-sm font-semibold text-slate-900">
                          {entry.module.layoutName}
                        </div>
                        <code className="mt-2 block rounded bg-slate-100 px-2 py-1 text-xs text-slate-700">
                          {entry.module.layoutId}
                        </code>
                      </td>
                      <td className="px-5 py-5">
                        <code className="block rounded bg-slate-100 px-2 py-1 text-xs text-slate-700">
                          frontend/src/components/slide-layouts/{entry.fileName}
                        </code>
                      </td>
                      <td className="px-5 py-5">
                        <div className="text-sm font-medium text-slate-900">
                          {entry.schemaName}
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {entry.keyFields.map((field) => (
                            <span
                              key={field}
                              className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600"
                            >
                              {field}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-5 py-5">
                        <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
                          {getLayoutGroupLabel(entry.group)}
                        </span>
                        <code className="mt-2 block text-xs text-slate-500">
                          {entry.group}
                        </code>
                      </td>
                      <td className="px-5 py-5">
                        <SubGroupBadge group={entry.group} subGroup={entry.subGroup} />
                      </td>
                      <td className="px-5 py-5">
                        <VariantCard variant={entry.variant} />
                      </td>
                      <td className="px-5 py-5">
                        <RuntimeVariantBadge role={entry.group} variant={entry.runtimeVariant} />
                      </td>
                      <td className="px-5 py-5">
                        <UsageChips usage={entry.usage} />
                      </td>
                      <td className="px-5 py-5">
                        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">
                          Current runtime notes source
                        </span>
                        <p className="text-sm leading-6 text-slate-700">
                          {entry.module.layoutDescription}
                        </p>
                        <p className="mt-2 text-xs leading-5 text-slate-500">
                          Taxonomy-driven notes contract and runtime integration land in `#75`.
                        </p>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </main>
  );
}

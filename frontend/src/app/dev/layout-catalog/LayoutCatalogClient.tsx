"use client";

import { Fragment, useState } from "react";
import type { ComponentType, ReactNode } from "react";

import layoutMetadataJson from "@/generated/layout-metadata.json";
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
import { getLayout, type LayoutEntry as RuntimeLayoutEntry } from "@/lib/template-registry";
import {
  compareLayoutRoles,
  getLayoutRole,
  getLayoutRoleDescription,
  getLayoutRoleLabel,
  LAYOUT_ROLE_ORDER,
  type LayoutRole,
} from "@/lib/layout-role";
import {
  getLayoutUsage,
  getUsageLabel,
  type LayoutUsageTag,
} from "@/lib/layout-usage";
import { compareLayoutNames } from "@/lib/sort";
import {
  compareLayoutVariants,
  getLayoutVariant,
  getLayoutVariantDescription,
  getLayoutVariantLabel,
  type LayoutVariant,
} from "@/lib/layout-variant";
import {
  getLayoutSubGroupDescription,
  getLayoutSubGroupLabel,
  getLayoutVariantAxisDescription,
  getLayoutVariantAxisLabel,
  type LayoutSubGroup,
} from "@/lib/layout-taxonomy";

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
  variant: LayoutVariant;
  usage: LayoutUsageTag[];
  notes: RuntimeLayoutEntry["notes"];
  keyFields: string[];
  data: Record<string, unknown>;
};

type CatalogFilter = "all" | LayoutRole;

function getRuntimeLayoutNotes(layoutId: string): RuntimeLayoutEntry["notes"] {
  const layout = getLayout(layoutId);
  if (!layout) {
    throw new Error(`Unknown runtime layout entry: ${layoutId}`);
  }
  return layout.notes;
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
    group: getLayoutRole("intro-slide"),
    variant: getLayoutVariant("intro-slide"),
    usage: getLayoutUsage("intro-slide"),
    notes: getRuntimeLayoutNotes("intro-slide"),
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
    group: getLayoutRole("outline-slide"),
    variant: getLayoutVariant("outline-slide"),
    usage: getLayoutUsage("outline-slide"),
    notes: getRuntimeLayoutNotes("outline-slide"),
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
    group: getLayoutRole("section-header"),
    variant: getLayoutVariant("section-header"),
    usage: getLayoutUsage("section-header"),
    notes: getRuntimeLayoutNotes("section-header"),
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
    group: getLayoutRole("bullet-with-icons"),
    variant: getLayoutVariant("bullet-with-icons"),
    usage: getLayoutUsage("bullet-with-icons"),
    notes: getRuntimeLayoutNotes("bullet-with-icons"),
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
    group: getLayoutRole("image-and-description"),
    variant: getLayoutVariant("image-and-description"),
    usage: getLayoutUsage("image-and-description"),
    notes: getRuntimeLayoutNotes("image-and-description"),
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
    group: getLayoutRole("bullet-icons-only"),
    variant: getLayoutVariant("bullet-icons-only"),
    usage: getLayoutUsage("bullet-icons-only"),
    notes: getRuntimeLayoutNotes("bullet-icons-only"),
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
    group: getLayoutRole("metrics-slide"),
    variant: getLayoutVariant("metrics-slide"),
    usage: getLayoutUsage("metrics-slide"),
    notes: getRuntimeLayoutNotes("metrics-slide"),
    keyFields: ["title", "conclusion", "conclusionBrief", "metrics[2-4]"],
    data: {
      title: "Quarterly Snapshot",
      conclusion: "Enterprise adoption is no longer the bottleneck.",
      conclusionBrief:
        "Coverage expanded across the org, so the next constraint is shortening review latency and increasing reuse in late-stage polish.",
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
    group: getLayoutRole("metrics-with-image"),
    variant: getLayoutVariant("metrics-with-image"),
    usage: getLayoutUsage("metrics-with-image"),
    notes: getRuntimeLayoutNotes("metrics-with-image"),
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
    group: getLayoutRole("chart-with-bullets"),
    variant: getLayoutVariant("chart-with-bullets"),
    usage: getLayoutUsage("chart-with-bullets"),
    notes: getRuntimeLayoutNotes("chart-with-bullets"),
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
    group: getLayoutRole("table-info"),
    variant: getLayoutVariant("table-info"),
    usage: getLayoutUsage("table-info"),
    notes: getRuntimeLayoutNotes("table-info"),
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
    group: getLayoutRole("two-column-compare"),
    variant: getLayoutVariant("two-column-compare"),
    usage: getLayoutUsage("two-column-compare"),
    notes: getRuntimeLayoutNotes("two-column-compare"),
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
    group: getLayoutRole("challenge-outcome"),
    variant: getLayoutVariant("challenge-outcome"),
    usage: getLayoutUsage("challenge-outcome"),
    notes: getRuntimeLayoutNotes("challenge-outcome"),
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
    group: getLayoutRole("numbered-bullets"),
    variant: getLayoutVariant("numbered-bullets"),
    usage: getLayoutUsage("numbered-bullets"),
    notes: getRuntimeLayoutNotes("numbered-bullets"),
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
    group: getLayoutRole("timeline"),
    variant: getLayoutVariant("timeline"),
    usage: getLayoutUsage("timeline"),
    notes: getRuntimeLayoutNotes("timeline"),
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
    group: getLayoutRole("quote-slide"),
    variant: getLayoutVariant("quote-slide"),
    usage: getLayoutUsage("quote-slide"),
    notes: getRuntimeLayoutNotes("quote-slide"),
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
    group: getLayoutRole("thank-you"),
    variant: getLayoutVariant("thank-you"),
    usage: getLayoutUsage("thank-you"),
    notes: getRuntimeLayoutNotes("thank-you"),
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
  const variantDelta = compareLayoutVariants(
    left.group,
    left.variant,
    right.variant,
  );
  if (variantDelta !== 0) return variantDelta;
  return compareLayoutNames(
    left.module.layoutName,
    right.module.layoutName,
    left.module.layoutId,
    right.module.layoutId,
  );
});

const variantAxes = layoutMetadataJson.variantAxes;

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

function MetaBlock({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <section>
      <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
        {label}
      </h3>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function VariantBadge({
  role,
  variant,
}: {
  role: LayoutRole;
  variant: LayoutVariant;
}) {
  return (
    <div>
      <span className="rounded-full bg-violet-50 px-2.5 py-1 text-xs font-medium text-violet-700">
        {getLayoutVariantLabel(role, variant)}
      </span>
      <code className="mt-2 block text-xs text-slate-500">{variant}</code>
      <p className="mt-2 text-sm leading-6 text-slate-700">
        {getLayoutVariantDescription(role, variant)}
      </p>
    </div>
  );
}

const NOTES_SLOT_LABELS: Array<{
  key: keyof RuntimeLayoutEntry["notes"];
  label: string;
}> = [
  { key: "purpose", label: "Purpose" },
  { key: "structure_signal", label: "Structure" },
  { key: "design_signal", label: "Design" },
  { key: "use_when", label: "Use when" },
  { key: "avoid_when", label: "Avoid when" },
  { key: "usage_bias", label: "Usage bias" },
];

function NotesCard({ notes }: { notes: RuntimeLayoutEntry["notes"] }) {
  return (
    <div className="rounded-xl border border-sky-200 bg-sky-50/60 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-sky-100 px-2.5 py-1 text-xs font-medium text-sky-700">
          Runtime notes
        </span>
        <span className="text-xs text-sky-800">
          shared metadata six-slot contract
        </span>
      </div>
      <dl className="mt-3 space-y-3">
        {NOTES_SLOT_LABELS.map(({ key, label }) => (
          <div key={key}>
            <dt className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-700">
              {label}
            </dt>
            <dd className="mt-1 text-sm leading-6 text-slate-700">
              {notes[key]}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function TogglePill({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "rounded-full bg-slate-900 px-3 py-1.5 text-xs font-medium text-white"
          : "rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-200"
      }
    >
      {children}
    </button>
  );
}

export function LayoutCatalogClientPage() {
  const [activeFilter, setActiveFilter] = useState<CatalogFilter>("all");
  const [expandedLayoutId, setExpandedLayoutId] = useState<string | null>(null);

  const visibleEntries = sortedEntries.filter(
    (entry) => activeFilter === "all" || entry.group === activeFilter,
  );

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
            This page renders every built-in TSX layout with sample data so you
            can compare previews, inspect file locations, and review the schema
            fields each template expects. The taxonomy reference below is kept
            as a compact glossary, while the main table stays focused on the
            template directory itself.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <TogglePill
              active={activeFilter === "all"}
              onClick={() => setActiveFilter("all")}
            >
              All layouts
            </TogglePill>
            {LAYOUT_ROLE_ORDER.map((role) => (
              <TogglePill
                key={role}
                active={activeFilter === role}
                onClick={() => setActiveFilter(role)}
              >
                {getLayoutRoleLabel(role)}
              </TogglePill>
            ))}
          </div>
        </header>

        <section className="mb-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="max-w-3xl">
            <h2 className="text-lg font-semibold text-slate-900">
              Taxonomy reference
            </h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              This quick reference lists the current `group`, `sub-group`, and
              compatibility `variant` vocabulary used by the built-in layouts.
            </p>
          </div>
          <div className="mt-5 grid gap-4 xl:grid-cols-3">
            <article className="rounded-xl border border-slate-200 bg-slate-50/70 p-5">
              <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-500">
                Group
              </h3>
              <div className="mt-4 space-y-4">
                {LAYOUT_ROLE_ORDER.map((role) => (
                  <div key={role} className="rounded-lg border border-slate-200 bg-white p-4">
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
                        {getLayoutRoleLabel(role)}
                      </span>
                      <code className="text-xs text-slate-500">{role}</code>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-slate-700">
                      {getLayoutRoleDescription(role)}
                    </p>
                  </div>
                ))}
              </div>
            </article>
            <article className="rounded-xl border border-slate-200 bg-slate-50/70 p-5">
              <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-500">
                Sub-group
              </h3>
              <div className="mt-4 space-y-4">
                {LAYOUT_ROLE_ORDER.map((role) => (
                  <div key={role} className="rounded-lg border border-slate-200 bg-white p-4">
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
                        {getLayoutRoleLabel(role)}
                      </span>
                      <code className="text-xs text-slate-500">{role}</code>
                    </div>
                    <div className="mt-3 space-y-3">
                      {Object.keys(layoutMetadataJson.subGroupsByGroup[role]).map((subGroup) => (
                        <div
                          key={`${role}-${subGroup}`}
                          className="rounded-lg border border-slate-100 bg-slate-50 p-3"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-semibold text-slate-900">
                              {getLayoutSubGroupLabel(role, subGroup as LayoutSubGroup)}
                            </span>
                            <code className="text-xs text-slate-500">{subGroup}</code>
                          </div>
                          <p className="mt-2 text-sm leading-6 text-slate-700">
                            {getLayoutSubGroupDescription(role, subGroup as LayoutSubGroup)}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </article>
            <article className="rounded-xl border border-slate-200 bg-slate-50/70 p-5">
              <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-500">
                Variant axes
              </h3>
              <div className="mt-4 space-y-4">
                {Object.entries(variantAxes).map(([axis, values]) => (
                  <div key={axis} className="rounded-lg border border-slate-200 bg-white p-4">
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-violet-50 px-2.5 py-1 text-xs font-medium uppercase tracking-[0.08em] text-violet-700">
                        {axis}
                      </span>
                    </div>
                    <div className="mt-3 space-y-3">
                      {Object.keys(values).map((value) => (
                        <div
                          key={`${axis}-${value}`}
                          className="rounded-lg border border-slate-100 bg-slate-50 p-3"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-semibold text-slate-900">
                              {getLayoutVariantAxisLabel(
                                axis as keyof typeof variantAxes,
                                value,
                              )}
                            </span>
                            <code className="text-xs text-slate-500">{value}</code>
                          </div>
                          <p className="mt-2 text-sm leading-6 text-slate-700">
                            {getLayoutVariantAxisDescription(
                              axis as keyof typeof variantAxes,
                              value,
                            )}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </article>
          </div>
        </section>

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-[1480px] table-fixed border-collapse">
              <thead className="bg-slate-100 text-left text-xs uppercase tracking-[0.16em] text-slate-500">
                <tr>
                  <th className="w-[360px] px-5 py-4">Preview</th>
                  <th className="w-[220px] px-5 py-4">Layout</th>
                  <th className="w-[160px] px-5 py-4">Group</th>
                  <th className="w-[260px] px-5 py-4">Runtime Variant</th>
                  <th className="w-[250px] px-5 py-4">Usage</th>
                  <th className="px-5 py-4">Details</th>
                </tr>
              </thead>
              <tbody>
                {visibleEntries.map((entry) => {
                  const isExpanded = expandedLayoutId === entry.module.layoutId;
                  const Component = entry.module.default;

                  return (
                    <Fragment key={entry.module.layoutId}>
                      <tr
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
                          <code className="mt-3 block rounded bg-slate-50 px-2 py-2 text-xs text-slate-600 ring-1 ring-slate-200">
                            frontend/src/components/slide-layouts/{entry.fileName}
                          </code>
                        </td>
                        <td className="px-5 py-5">
                          <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
                            {getLayoutRoleLabel(entry.group)}
                          </span>
                          <code className="mt-2 block text-xs text-slate-500">
                            {entry.group}
                          </code>
                        </td>
                        <td className="px-5 py-5">
                          <VariantBadge role={entry.group} variant={entry.variant} />
                        </td>
                        <td className="px-5 py-5">
                          <UsageChips usage={entry.usage} />
                        </td>
                        <td className="px-5 py-5">
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedLayoutId((current) =>
                                current === entry.module.layoutId
                                  ? null
                                  : entry.module.layoutId,
                              )
                            }
                            className="rounded-full bg-slate-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-slate-700"
                          >
                            {isExpanded ? "Hide details" : "Show details"}
                          </button>
                          <p className="mt-3 text-sm leading-6 text-slate-600">
                            {entry.notes.purpose}
                          </p>
                        </td>
                      </tr>
                      {isExpanded ? (
                        <tr className="border-t border-slate-100 bg-slate-50/60">
                          <td colSpan={6} className="px-5 py-5">
                            <div className="grid gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
                              <MetaBlock label="Schema">
                                <div className="rounded-xl border border-slate-200 bg-white p-4">
                                  <div className="text-sm font-semibold text-slate-900">
                                    {entry.schemaName}
                                  </div>
                                  <div className="mt-3 flex flex-wrap gap-2">
                                    {entry.keyFields.map((field) => (
                                      <span
                                        key={field}
                                        className="rounded-full bg-slate-50 px-2.5 py-1 text-xs text-slate-600 ring-1 ring-slate-200"
                                      >
                                        {field}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              </MetaBlock>
                              <MetaBlock label="Notes">
                                <NotesCard notes={entry.notes} />
                              </MetaBlock>
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
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
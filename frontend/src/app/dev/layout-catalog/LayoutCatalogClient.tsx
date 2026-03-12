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
import { compareLayoutRoles, getLayoutRole, type LayoutRole } from "@/lib/layout-role";
import { formatLayoutNote } from "@/lib/layout-note";
import {
  getLayoutUsage,
  getUsageLabel,
  type LayoutUsageTag,
} from "@/lib/layout-usage";

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
  usage: LayoutUsageTag[];
  keyFields: string[];
  data: Record<string, unknown>;
};

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
    group: getLayoutRole("outline-slide"),
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
    group: getLayoutRole("section-header"),
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
    group: getLayoutRole("bullet-with-icons"),
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
    group: getLayoutRole("image-and-description"),
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
    group: getLayoutRole("bullet-icons-only"),
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
    group: getLayoutRole("metrics-slide"),
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
    group: getLayoutRole("metrics-with-image"),
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
    group: getLayoutRole("chart-with-bullets"),
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
    group: getLayoutRole("table-info"),
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
    group: getLayoutRole("two-column-compare"),
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
    group: getLayoutRole("challenge-outcome"),
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
    group: getLayoutRole("numbered-bullets"),
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
    group: getLayoutRole("timeline"),
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
    group: getLayoutRole("quote-slide"),
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
    group: getLayoutRole("thank-you"),
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
  return left.module.layoutName.localeCompare(right.module.layoutName);
});

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
            This page renders every current TSX layout with sample data. Treat it
            as the fastest way to compare structure, inspect file names, and
            decide where to add or refine notes.
          </p>
        </header>

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full table-fixed border-collapse">
            <thead className="bg-slate-100 text-left text-xs uppercase tracking-[0.16em] text-slate-500">
              <tr>
                <th className="w-[360px] px-5 py-4">Preview</th>
                <th className="w-[190px] px-5 py-4">Layout</th>
                <th className="w-[250px] px-5 py-4">TSX File</th>
                <th className="w-[210px] px-5 py-4">Schema</th>
                <th className="w-[120px] px-5 py-4">Group</th>
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
                        {entry.group}
                      </span>
                    </td>
                    <td className="px-5 py-5">
                      <UsageChips usage={entry.usage} />
                    </td>
                    <td className="px-5 py-5">
                      <p className="text-sm leading-6 text-slate-700">
                        {formatLayoutNote(
                          entry.module.layoutId,
                          entry.module.layoutDescription,
                        )}
                      </p>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}

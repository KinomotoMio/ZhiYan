"use client";

import type { OutlineSectionItem, OutlineSlideData } from "@/types/layout-data";

export const layoutId = "outline-slide-rail";
export const layoutName = "目录导航页（导轨）";
export const layoutDescription = "展示整体汇报框架的导轨式目录页，强调章节推进顺序。";

const OUTLINE_RAIL_SINGLE_COLUMN_MAX = 3;

function splitSections(sections: OutlineSectionItem[]) {
  if (sections.length <= OUTLINE_RAIL_SINGLE_COLUMN_MAX) {
    return [sections, [] as OutlineSectionItem[]];
  }

  const midpoint = Math.ceil(sections.length / 2);
  return [sections.slice(0, midpoint), sections.slice(midpoint)];
}

function RailColumn({
  sections,
  startIndex,
  dense,
}: {
  sections: OutlineSectionItem[];
  startIndex: number;
  dense: boolean;
}) {
  if (sections.length === 0) {
    return null;
  }

  return (
    <div
      className="relative grid min-h-0 gap-5"
      style={{ gridTemplateRows: `repeat(${sections.length}, minmax(0, 1fr))` }}
    >
      <div className="absolute left-[22px] top-3 bottom-3 w-px bg-slate-200" />
      {sections.map((section, index) => (
        <article key={`${section.title}-${startIndex + index}`} className="relative flex min-h-0 gap-5">
          <div className="relative z-10 flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[var(--primary-color,#3b82f6)] text-sm font-bold text-white shadow-sm">
            {String(startIndex + index + 1).padStart(2, "0")}
          </div>
          <div
            className={`min-w-0 rounded-2xl border border-slate-100 bg-slate-50 ${dense ? "px-4 py-3" : "px-5 py-4"}`}
          >
            <h3 style={{ fontSize: dense ? 20 : 23, fontWeight: 700, lineHeight: 1.2 }}>
              {section.title}
            </h3>
            {section.description ? (
              <p
                style={{ fontSize: dense ? 13 : 14, lineHeight: 1.6 }}
                className="mt-2 text-slate-600"
              >
                {section.description}
              </p>
            ) : null}
          </div>
        </article>
      ))}
    </div>
  );
}

export default function OutlineSlideRailLayout({ data }: { data: OutlineSlideData }) {
  const [leftColumn, rightColumn] = splitSections(data.sections);
  const isMultiColumn = rightColumn.length > 0;

  return (
    <div className="flex h-full bg-[linear-gradient(160deg,var(--slide-bg-start,#ffffff)_0%,var(--slide-bg-end,#f8fafc)_100%)] px-16 py-14 text-[var(--background-text,#111827)]">
      <div className="flex w-full gap-12">
        <section className="w-[38%] shrink-0">
          <div className="mb-5 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--primary-color,#3b82f6)]">
            Chapter Rail
          </div>
          <h2 style={{ fontSize: 42, fontWeight: 800, lineHeight: 1.08, letterSpacing: "-0.05em" }}>
            {data.title}
          </h2>
          {data.subtitle ? (
            <p style={{ fontSize: 17, lineHeight: 1.65 }} className="mt-5 text-slate-600">
              {data.subtitle}
            </p>
          ) : null}
        </section>

        <section className="flex-1 rounded-[32px] border border-slate-200 bg-white p-8 shadow-sm">
          <div className={`h-full min-h-0 ${isMultiColumn ? "grid grid-cols-2 gap-6" : ""}`}>
            <RailColumn sections={leftColumn} startIndex={0} dense={isMultiColumn} />
            {isMultiColumn ? (
              <RailColumn sections={rightColumn} startIndex={leftColumn.length} dense={isMultiColumn} />
            ) : null}
          </div>
        </section>
      </div>
    </div>
  );
}

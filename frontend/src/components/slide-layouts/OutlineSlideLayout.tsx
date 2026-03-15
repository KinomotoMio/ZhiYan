"use client";

import type { OutlineSectionItem, OutlineSlideData } from "@/types/layout-data";

export const layoutId = "outline-slide";
export const layoutName = "目录导航页";
export const layoutDescription = "展示整体汇报框架的目录页，使用 4-6 个章节清单呈现内容结构。";

function splitSections(sections: OutlineSectionItem[]) {
  const midpoint = Math.ceil(sections.length / 2);
  return [sections.slice(0, midpoint), sections.slice(midpoint)] as const;
}

export default function OutlineSlideLayout({ data }: { data: OutlineSlideData }) {
  const [leftColumn, rightColumn] = splitSections(data.sections);
  const columns = [leftColumn, rightColumn].filter((column) => column.length > 0);

  return (
    <div className="flex h-full flex-col px-16 py-14 text-[var(--background-text,#111827)]">
      <div className="flex items-end gap-10">
        <div className="max-w-[560px]">
          <div className="mb-5 h-1.5 w-16 rounded-full bg-[var(--primary-color,#3b82f6)]" />
          <h2
            style={{ fontSize: 42, fontWeight: 700, lineHeight: 1.12, letterSpacing: "-0.045em" }}
            className="mb-4"
          >
            {data.title}
          </h2>
          {data.subtitle && (
            <p
              style={{ fontSize: 17, lineHeight: 1.6 }}
              className="max-w-[520px] text-[color:color-mix(in_srgb,var(--background-text,#111827)_60%,transparent)]"
            >
              {data.subtitle}
            </p>
          )}
        </div>
        <div className="mb-3 h-px flex-1 bg-[color:color-mix(in_srgb,var(--background-text,#111827)_12%,transparent)]" />
      </div>

      <div className="mt-12 grid flex-1 grid-cols-2 gap-x-14">
        {columns.map((column, columnIndex) => (
          <div
            key={columnIndex}
            className="grid min-h-0 gap-y-6"
            style={{ gridTemplateRows: `repeat(${column.length}, minmax(0, 1fr))` }}
          >
            {column.map((section, index) => {
              const sectionIndex = columnIndex === 0 ? index : leftColumn.length + index;
              return (
                <article
                  key={`${section.title}-${sectionIndex}`}
                  className="border-t border-black/10 pt-5"
                >
                  <div className="flex gap-5">
                    <div className="w-12 shrink-0 pt-1">
                      <div
                        style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.18em" }}
                        className="text-[var(--primary-color,#3b82f6)]"
                      >
                        {String(sectionIndex + 1).padStart(2, "0")}
                      </div>
                    </div>
                    <div className="min-w-0">
                      <h3
                        style={{
                          fontSize: 28,
                          fontWeight: 600,
                          lineHeight: 1.05,
                          letterSpacing: "-0.04em",
                        }}
                      >
                        {section.title}
                      </h3>
                      {section.description && (
                        <p
                          style={{ fontSize: 15, lineHeight: 1.6 }}
                          className="mt-3 max-w-[420px] text-[color:color-mix(in_srgb,var(--background-text,#111827)_58%,transparent)]"
                        >
                          {section.description}
                        </p>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

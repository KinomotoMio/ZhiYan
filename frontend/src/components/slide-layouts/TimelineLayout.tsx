"use client";

import type { TimelineData } from "@/types/layout-data";

export const layoutId = "timeline";
export const layoutName = "时间轴";
export const layoutDescription = "时间线/里程碑展示，适合发展历程、项目进度";

export default function TimelineLayout({ data }: { data: TimelineData }) {
  return (
    <div className="flex flex-col h-full px-16 py-14">
      <h2 style={{ fontSize: 36, fontWeight: 700, lineHeight: 1.3 }} className="text-[var(--background-text,#111827)] mb-10">
        {data.title}
      </h2>
      <div className="flex-1 flex items-center">
        <div className="relative flex items-start justify-between w-full">
          {/* Connecting line */}
          <div className="absolute top-5 left-5 right-5 h-0.5 bg-[var(--primary-color,#3b82f6)]/20" />
          {data.events.map((event, i) => (
            <div key={i} className="relative flex flex-col items-center text-center" style={{ width: `${100 / data.events.length}%` }}>
              <div className="w-10 h-10 rounded-full bg-[var(--primary-color,#3b82f6)] flex items-center justify-center z-10 mb-4">
                <span style={{ fontSize: 14, fontWeight: 700 }} className="text-[var(--primary-text,#ffffff)]">
                  {i + 1}
                </span>
              </div>
              <span style={{ fontSize: 14, fontWeight: 700 }} className="text-[var(--primary-color,#3b82f6)] mb-2">
                {event.date}
              </span>
              <h3 style={{ fontSize: 17, fontWeight: 600 }} className="text-[var(--background-text,#111827)] mb-1 px-2">
                {event.title}
              </h3>
              {event.description && (
                <p style={{ fontSize: 13, lineHeight: 1.4 }} className="text-[var(--background-text,#111827)]/50 px-3 max-w-48">
                  {event.description}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

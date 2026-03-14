"use client";

import type { ThankYouData } from "@/types/layout-data";

export const layoutId = "thank-you-contact";
export const layoutName = "致谢页（联系方式）";
export const layoutDescription = "结束页，左侧致谢、右侧联系方式卡片，适合希望观众继续联系的收尾场景。";

export default function ThankYouContactLayout({ data }: { data: ThankYouData }) {
  return (
    <div className="flex h-full items-center bg-[linear-gradient(160deg,var(--slide-bg-start,#ffffff)_0%,var(--slide-bg-end,#f8fafc)_100%)] px-16 py-14 text-[var(--background-text,#111827)]">
      <div className="grid w-full grid-cols-[minmax(0,1fr)_360px] gap-10">
        <section className="flex flex-col justify-center">
          <div className="mb-6 h-1.5 w-20 rounded-full bg-[var(--primary-color,#3b82f6)]" />
          <h1 style={{ fontSize: 54, fontWeight: 800, lineHeight: 1.08, letterSpacing: "-0.05em" }}>
            {data.title}
          </h1>
          {data.subtitle ? (
            <p style={{ fontSize: 22, lineHeight: 1.65 }} className="mt-6 max-w-[620px] text-slate-600">
              {data.subtitle}
            </p>
          ) : null}
        </section>

        <aside className="rounded-[32px] border border-slate-200 bg-white px-8 py-8 shadow-sm">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--primary-color,#3b82f6)]">
            Keep In Touch
          </div>
          <div style={{ fontSize: 26, fontWeight: 700, lineHeight: 1.2 }} className="mt-5">
            Let&apos;s continue the conversation.
          </div>
          <div style={{ fontSize: 15, lineHeight: 1.7 }} className="mt-5 text-slate-600">
            {data.contact || "contact@zhiyan.ai"}
          </div>
        </aside>
      </div>
    </div>
  );
}

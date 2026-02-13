"use client";

import type { ThankYouData } from "@/types/layout-data";

export const layoutId = "thank-you";
export const layoutName = "致谢页";
export const layoutDescription = "结束页，致谢+联系方式";

export default function ThankYouLayout({ data }: { data: ThankYouData }) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-24 text-center">
      <div className="w-16 h-1 rounded-full bg-[var(--primary-color,#3b82f6)] mb-10" />
      <h1 style={{ fontSize: 56, fontWeight: 800, lineHeight: 1.2 }} className="text-[var(--background-text,#111827)] mb-6">
        {data.title}
      </h1>
      {data.subtitle && (
        <p style={{ fontSize: 22 }} className="text-[var(--background-text,#111827)]/50 mb-4 max-w-[600px]">
          {data.subtitle}
        </p>
      )}
      {data.contact && (
        <p style={{ fontSize: 16 }} className="text-[var(--primary-color,#3b82f6)]">
          {data.contact}
        </p>
      )}
    </div>
  );
}

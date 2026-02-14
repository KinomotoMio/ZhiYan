"use client";

import Image from "next/image";
import { ImageIcon } from "lucide-react";
import type { MetricsWithImageData } from "@/types/layout-data";

export const layoutId = "metrics-with-image";
export const layoutName = "指标+配图";
export const layoutDescription = "指标卡片+右侧图片，适合带视觉的数据展示";

export default function MetricsWithImageLayout({ data }: { data: MetricsWithImageData }) {
  return (
    <div className="flex h-full">
      <div className="flex flex-col flex-1 px-14 py-14">
        <h2 style={{ fontSize: 36, fontWeight: 700, lineHeight: 1.3 }} className="text-[var(--background-text,#111827)] mb-10">
          {data.title}
        </h2>
        <div className="flex flex-col gap-6 flex-1 justify-center">
          {data.metrics.map((metric, i) => (
            <div key={i} className="flex items-center gap-4 p-5 rounded-xl bg-[var(--primary-color,#3b82f6)]/5">
              <span style={{ fontSize: 40, fontWeight: 800 }} className="text-[var(--primary-color,#3b82f6)] shrink-0 w-32 text-center">
                {metric.value}
              </span>
              <div>
                <span style={{ fontSize: 18, fontWeight: 600 }} className="text-[var(--background-text,#111827)] block">
                  {metric.label}
                </span>
                {metric.description && (
                  <span style={{ fontSize: 14 }} className="text-[var(--background-text,#111827)]/50">
                    {metric.description}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="w-[45%] shrink-0 bg-gray-100 flex flex-col items-center justify-center">
        {data.image.url ? (
          <div className="relative h-full w-full">
            <Image
              src={data.image.url}
              alt={data.image.alt || ""}
              fill
              unoptimized
              sizes="45vw"
              className="object-cover"
            />
          </div>
        ) : (
          <div className="flex flex-col items-center text-gray-400">
            <ImageIcon className="w-12 h-12 mb-2" />
            <span style={{ fontSize: 14 }} className="text-center px-6">{data.image.prompt}</span>
          </div>
        )}
      </div>
    </div>
  );
}

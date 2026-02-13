"use client";

import type { ImageAndDescriptionData } from "@/types/layout-data";
import { ImagePlaceholder } from "./_shared";

export const layoutId = "image-and-description";
export const layoutName = "图文混排";
export const layoutDescription = "图片+描述文字，适合产品展示、案例说明";

export default function ImageAndDescriptionLayout({ data }: { data: ImageAndDescriptionData }) {
  return (
    <div className="flex h-full">
      <div className="w-[48%] shrink-0 overflow-hidden rounded-r-3xl">
        <ImagePlaceholder prompt={data.image.prompt} url={data.image.url} alt={data.image.alt} />
      </div>
      <div className="flex-1 flex flex-col justify-center px-14 py-14">
        <h2 style={{ fontSize: 36, fontWeight: 700, lineHeight: 1.3 }} className="text-[var(--background-text,#111827)] mb-6">
          {data.title}
        </h2>
        <p style={{ fontSize: 18, lineHeight: 1.7 }} className="text-[var(--background-text,#111827)]/70 mb-6">
          {data.description}
        </p>
        {data.bullets && data.bullets.length > 0 && (
          <div className="flex flex-col gap-3">
            {data.bullets.map((b, i) => (
              <div key={i} className="flex items-start gap-3">
                <div className="w-2 h-2 rounded-full bg-[var(--primary-color,#3b82f6)] mt-2 shrink-0" />
                <span style={{ fontSize: 16 }} className="text-[var(--background-text,#111827)]/60">{b}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

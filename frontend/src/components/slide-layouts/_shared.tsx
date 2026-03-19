"use client";

import Image from "next/image";
import type { CSSProperties } from "react";
import { createElement } from "react";
import { Eye } from "lucide-react";
import { getImagePlaceholderCopy } from "@/lib/image-source";
import { getLayoutIconNode } from "@/lib/layout-icons";
import type { ImageRef } from "@/types/layout-data";

export function LayoutIcon({
  query,
  className,
  style,
}: {
  query: string;
  className?: string;
  style?: CSSProperties;
}) {
  const iconNode = getLayoutIconNode(query);

  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
      style={style}
    >
      {iconNode.map(([tag, attrs], index) =>
        createElement(tag, {
          ...attrs,
          key: `${tag}-${index}`,
        })
      )}
    </svg>
  );
}

export function ImagePlaceholder({ image, sizes = "100vw" }: { image: ImageRef; sizes?: string }) {
  if (image.url) {
    return (
      <div className="relative h-full w-full">
        <Image
          src={image.url}
          alt={image.alt || image.prompt || "Image"}
          fill
          unoptimized
          sizes={sizes}
          className="object-cover"
        />
      </div>
    );
  }

  const placeholder = getImagePlaceholderCopy(image);
  return (
    <div className="w-full h-full bg-gray-100 flex flex-col items-center justify-center text-gray-400 px-4 text-center">
      <Eye className="w-10 h-10 mb-2 opacity-50" />
      <span style={{ fontSize: 13 }} className="opacity-70 font-medium">{placeholder.title}</span>
      {placeholder.detail ? (
        <span style={{ fontSize: 12 }} className="opacity-60 mt-1 max-w-[18rem]">{placeholder.detail}</span>
      ) : null}
    </div>
  );
}

"use client";

import Image from "next/image";
import { createElement } from "react";
import { Eye } from "lucide-react";
import { getLayoutIconNode } from "@/lib/layout-icons";

export function LayoutIcon({ query, className }: { query: string; className?: string }) {
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

export function ImagePlaceholder({ prompt, alt, url }: { prompt: string; alt?: string; url?: string | null }) {
  if (url) {
    return (
      <div className="relative h-full w-full">
        <Image
          src={url}
          alt={alt || prompt}
          fill
          unoptimized
          sizes="100vw"
          className="object-cover"
        />
      </div>
    );
  }
  return (
    <div className="w-full h-full bg-gray-100 flex flex-col items-center justify-center text-gray-400">
      <Eye className="w-10 h-10 mb-2 opacity-50" />
      <span style={{ fontSize: 13 }} className="text-center px-4 opacity-60">{prompt}</span>
    </div>
  );
}

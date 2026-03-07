"use client";

import Image from "next/image";
import { Eye } from "lucide-react";
import { getLayoutIconComponent } from "@/lib/layout-icons";

export function LayoutIcon({ query, className }: { query: string; className?: string }) {
  const Icon = getLayoutIconComponent(query);
  return <Icon className={className} />;
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

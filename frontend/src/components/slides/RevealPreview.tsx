"use client";

import { useEffect, useRef } from "react";
import type { Presentation } from "@/types/slide";
import { presentationToRevealHTML } from "@/lib/slide-to-reveal";

interface RevealPreviewProps {
  presentation: Presentation;
  startSlide?: number;
  className?: string;
}

export default function RevealPreview({
  presentation,
  startSlide = 0,
  className = "",
}: RevealPreviewProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    if (!iframeRef.current) return;
    const html = presentationToRevealHTML(presentation);
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    iframeRef.current.src = url;
    return () => URL.revokeObjectURL(url);
  }, [presentation, startSlide]);

  return (
    <iframe
      ref={iframeRef}
      className={`w-full h-full border-0 ${className}`}
      title="演示文稿预览"
      sandbox="allow-scripts allow-same-origin"
    />
  );
}

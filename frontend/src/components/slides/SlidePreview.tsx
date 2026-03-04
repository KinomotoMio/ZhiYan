"use client";

import { useRef, useState, useEffect } from "react";
import { ImageIcon, BarChart3 } from "lucide-react";
import type { Slide, Component as SlideComponent } from "@/types/slide";
import { getLayoutComponent } from "@/lib/template-registry";
import { normalizeLayoutData } from "@/lib/layout-data-normalizer";
import LayoutErrorFallback from "@/components/slides/LayoutErrorFallback";

// ---------- 旧版 Component 渲染器（向后兼容） ----------

function RenderComponent({
  comp,
  scale,
}: {
  comp: SlideComponent;
  scale: number;
}) {
  const posStyle: React.CSSProperties = {
    position: "absolute",
    left: `${comp.position.x}%`,
    top: `${comp.position.y}%`,
    width: `${comp.position.width}%`,
    height: `${comp.position.height}%`,
  };

  const textStyle: React.CSSProperties = {
    fontSize: comp.style?.fontSize
      ? `${comp.style.fontSize * scale}px`
      : undefined,
    fontWeight: comp.style?.fontWeight as React.CSSProperties["fontWeight"],
    color: comp.style?.color,
    textAlign: comp.style?.textAlign as React.CSSProperties["textAlign"],
    opacity: comp.style?.opacity,
    lineHeight: 1.4,
  };

  switch (comp.type) {
    case "text": {
      const lines = (comp.content || "").split("\n");
      return (
        <div style={{ ...posStyle, ...textStyle, overflow: "hidden" }}>
          {lines.map((line, i) => {
            const unorderedMatch = line.match(/^([•\-*])\s+(.*)/);
            if (unorderedMatch) {
              return (
                <div key={i} className="flex gap-1" style={{ paddingLeft: `${4 * scale}px` }}>
                  <span className="shrink-0">•</span>
                  <span>{unorderedMatch[2]}</span>
                </div>
              );
            }
            const orderedMatch = line.match(/^(\d+)[.)]\s+(.*)/);
            if (orderedMatch) {
              return (
                <div key={i} className="flex gap-1" style={{ paddingLeft: `${4 * scale}px` }}>
                  <span className="shrink-0">{orderedMatch[1]}.</span>
                  <span>{orderedMatch[2]}</span>
                </div>
              );
            }
            const nestedMatch = line.match(/^(\s{2,}|\t+)([•\-*]|\d+[.)])\s+(.*)/);
            if (nestedMatch) {
              return (
                <div key={i} className="flex gap-1" style={{ paddingLeft: `${12 * scale}px` }}>
                  <span className="shrink-0">
                    {nestedMatch[2].match(/\d/) ? `${nestedMatch[2].replace(/[.)]/, "")}.` : "◦"}
                  </span>
                  <span>{nestedMatch[3]}</span>
                </div>
              );
            }
            return (
              <div key={i}>{line || "\u00A0"}</div>
            );
          })}
        </div>
      );
    }
    case "image":
      return (
        <div
          style={{ ...posStyle, backgroundColor: "#f3f4f6" }}
          className="flex flex-col items-center justify-center text-muted-foreground rounded"
        >
          <ImageIcon style={{ width: `${20 * scale}px`, height: `${20 * scale}px` }} className="opacity-40" />
          <span style={{ fontSize: `${10 * scale}px`, marginTop: `${2 * scale}px` }} className="opacity-40">
            {comp.content || "图片"}
          </span>
        </div>
      );
    case "chart":
      return (
        <div
          style={{ ...posStyle, backgroundColor: "#f9fafb", borderWidth: 1, borderStyle: "dashed", borderColor: "#d1d5db" }}
          className="flex flex-col items-center justify-center text-muted-foreground rounded"
        >
          <BarChart3 style={{ width: `${20 * scale}px`, height: `${20 * scale}px` }} className="opacity-40" />
          <span style={{ fontSize: `${10 * scale}px`, marginTop: `${2 * scale}px` }} className="opacity-40">
            {comp.content || "图表"}
          </span>
        </div>
      );
    default:
      return <div style={posStyle} />;
  }
}

// ---------- Skeleton 加载态渲染器 ----------

function RenderSkeletonSlide({ slide }: { slide: Slide }) {
  const title = (slide.contentData as Record<string, unknown>)?.title as string | undefined;
  return (
    <div
      style={{ width: 1280, height: 720, transformOrigin: "top left" }}
      className="bg-white flex flex-col items-center justify-center p-16"
    >
      {title && (
        <h2 className="text-4xl font-bold text-gray-800 mb-8 text-center">{title}</h2>
      )}
      <div className="w-full max-w-3xl space-y-5">
        <div className="h-5 bg-gray-200 rounded-md animate-pulse w-full" />
        <div className="h-5 bg-gray-200 rounded-md animate-pulse w-5/6" />
        <div className="h-5 bg-gray-200 rounded-md animate-pulse w-4/6" />
        <div className="h-5 bg-gray-200 rounded-md animate-pulse w-full" />
        <div className="h-5 bg-gray-200 rounded-md animate-pulse w-3/5" />
      </div>
    </div>
  );
}

// ---------- 新版 Layout 渲染器 ----------

function RenderLayoutSlide({ slide }: { slide: Slide }) {
  const layoutId = slide.layoutId || slide.layoutType;
  if (!layoutId) {
    return <LayoutErrorFallback layoutId="unknown" reason="缺少 layoutId" />;
  }

  const LayoutComponent = getLayoutComponent(layoutId);
  if (!LayoutComponent) {
    return <LayoutErrorFallback layoutId={layoutId} reason="未注册的布局组件" />;
  }

  if (!slide.contentData || typeof slide.contentData !== "object") {
    return <LayoutErrorFallback layoutId={layoutId} reason="缺少 contentData" />;
  }

  const normalized = normalizeLayoutData(
    layoutId,
    slide.contentData as Record<string, unknown>
  );
  if (!normalized.recoverable) {
    return <LayoutErrorFallback layoutId={layoutId} reason={normalized.reason} />;
  }

  return (
    <div
      style={{
        width: 1280,
        height: 720,
        transformOrigin: "top left",
      }}
      className="bg-[var(--background-color,#ffffff)]"
    >
      {/* eslint-disable-next-line react-hooks/static-components */}
      <LayoutComponent data={normalized.data} />
    </div>
  );
}

// ---------- SlidePreview 主组件 ----------

interface SlidePreviewProps {
  slide: Slide;
  className?: string;
  onClick?: () => void;
  isActive?: boolean;
}

export default function SlidePreview({
  slide,
  className = "",
  onClick,
  isActive,
}: SlidePreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.5);

  // 判断是否为 skeleton 加载态
  const isSkeleton = !!(slide.contentData as Record<string, unknown> | undefined)?._loading;
  // 判断是否使用新版 layout 渲染
  const useNewLayout = !isSkeleton && !!(slide.layoutId && slide.contentData);

  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const containerWidth = entry.contentRect.width;
        if (useNewLayout || isSkeleton) {
          setScale(containerWidth / 1280);
        } else {
          setScale(containerWidth / 960);
        }
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [useNewLayout, isSkeleton]);

  return (
    <div
      ref={containerRef}
      onClick={onClick}
      className={`relative bg-white border rounded-lg overflow-hidden cursor-pointer transition-shadow ${
        isActive ? "ring-2 ring-primary shadow-lg" : "hover:shadow-md"
      } ${className}`}
      style={{ aspectRatio: "16 / 9" }}
    >
      {isSkeleton ? (
        <div
          style={{
            transform: `scale(${scale})`,
            transformOrigin: "top left",
            width: 1280,
            height: 720,
          }}
        >
          <RenderSkeletonSlide slide={slide} />
        </div>
      ) : useNewLayout ? (
        <div
          style={{
            transform: `scale(${scale})`,
            transformOrigin: "top left",
            width: 1280,
            height: 720,
          }}
        >
          <RenderLayoutSlide slide={slide} />
        </div>
      ) : (
        (slide.components ?? []).map((comp) => (
          <RenderComponent key={comp.id} comp={comp} scale={scale} />
        ))
      )}
    </div>
  );
}

"use client";

import { useRef, useState, useEffect } from "react";
import { ImageIcon, BarChart3 } from "lucide-react";
import type { Slide, Component as SlideComponent } from "@/types/slide";

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
            // 无序列表：• - * 开头
            const unorderedMatch = line.match(/^([•\-*])\s+(.*)/);
            if (unorderedMatch) {
              return (
                <div key={i} className="flex gap-1" style={{ paddingLeft: `${4 * scale}px` }}>
                  <span className="shrink-0">•</span>
                  <span>{unorderedMatch[2]}</span>
                </div>
              );
            }
            // 有序列表：1. 2. 等
            const orderedMatch = line.match(/^(\d+)[.)]\s+(.*)/);
            if (orderedMatch) {
              return (
                <div key={i} className="flex gap-1" style={{ paddingLeft: `${4 * scale}px` }}>
                  <span className="shrink-0">{orderedMatch[1]}.</span>
                  <span>{orderedMatch[2]}</span>
                </div>
              );
            }
            // 嵌套列表（以空格/tab 开头 + 列表符号）
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

  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        // 基于标准 PPT 宽度 960px 计算缩放比
        const containerWidth = entry.contentRect.width;
        setScale(containerWidth / 960);
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={containerRef}
      onClick={onClick}
      className={`relative bg-white border rounded-lg overflow-hidden cursor-pointer transition-shadow ${
        isActive ? "ring-2 ring-primary shadow-lg" : "hover:shadow-md"
      } ${className}`}
      style={{ aspectRatio: "16 / 9" }}
    >
      {slide.components.map((comp) => (
        <RenderComponent key={comp.id} comp={comp} scale={scale} />
      ))}
    </div>
  );
}

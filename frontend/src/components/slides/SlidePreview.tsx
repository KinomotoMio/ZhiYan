"use client";

import type { Slide, Component as SlideComponent } from "@/types/slide";

function RenderComponent({ comp }: { comp: SlideComponent }) {
  const posStyle: React.CSSProperties = {
    position: "absolute",
    left: `${comp.position.x}%`,
    top: `${comp.position.y}%`,
    width: `${comp.position.width}%`,
    height: `${comp.position.height}%`,
  };

  const textStyle: React.CSSProperties = {
    fontSize: comp.style?.fontSize ? `${comp.style.fontSize * 0.5}px` : undefined,
    fontWeight: comp.style?.fontWeight as React.CSSProperties["fontWeight"],
    color: comp.style?.color,
    textAlign: comp.style?.textAlign as React.CSSProperties["textAlign"],
    opacity: comp.style?.opacity,
  };

  switch (comp.type) {
    case "text": {
      const lines = (comp.content || "").split("\n");
      return (
        <div style={{ ...posStyle, ...textStyle, overflow: "hidden" }}>
          {lines.map((line, i) => {
            if (line.startsWith("• ") || line.startsWith("- ")) {
              return (
                <div key={i} className="flex gap-1">
                  <span>•</span>
                  <span>{line.slice(2)}</span>
                </div>
              );
            }
            return <div key={i}>{line}</div>;
          })}
        </div>
      );
    }
    case "image":
      return (
        <div
          style={{ ...posStyle, backgroundColor: "#f0f0f0" }}
          className="flex items-center justify-center text-muted-foreground text-xs"
        >
          [图片]
        </div>
      );
    case "chart":
      return (
        <div
          style={{ ...posStyle, backgroundColor: "#f8f8f8" }}
          className="flex items-center justify-center text-muted-foreground text-xs border border-dashed"
        >
          [图表]
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
  return (
    <div
      onClick={onClick}
      className={`relative bg-white border rounded-lg overflow-hidden cursor-pointer transition-shadow ${
        isActive ? "ring-2 ring-primary shadow-lg" : "hover:shadow-md"
      } ${className}`}
      style={{ aspectRatio: "16 / 9" }}
    >
      {slide.components.map((comp) => (
        <RenderComponent key={comp.id} comp={comp} />
      ))}
    </div>
  );
}

"use client";

import type { CSSProperties, ReactNode } from "react";
import type { SceneBackground } from "@/types/slide";
import { getSceneBackgroundRenderModel, type StyleMap } from "@/lib/scene-background-renderer";

function asStyle(style: StyleMap): CSSProperties {
  return style as CSSProperties;
}

interface SceneBackgroundFrameProps {
  background?: SceneBackground | null;
  children: ReactNode;
}

export default function SceneBackgroundFrame({
  background,
  children,
}: SceneBackgroundFrameProps) {
  const renderModel = getSceneBackgroundRenderModel(background);

  if (!renderModel) {
    return (
      <div
        style={{ width: "100%", height: "100%", backgroundColor: "var(--background-color,#ffffff)" }}
      >
        {children}
      </div>
    );
  }

  return (
    <div {...renderModel.attributes} style={asStyle(renderModel.frameStyle)}>
      {renderModel.layers.map((layer) => (
        <div key={layer.key} aria-hidden="true" style={asStyle(layer.style)} />
      ))}
      <div style={asStyle(renderModel.contentStyle)}>{children}</div>
    </div>
  );
}

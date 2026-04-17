"use client";

import { useEffect, useRef, useState } from "react";

import type { CentiDeckArtifactPayload } from "@/lib/api";
import { getLatestSessionPresentationCentiDeckArtifact } from "@/lib/api";
import {
  CentiDeckRuntime,
  loadAllCentiDeckModules,
  type CentiDeckRuntimeMode,
} from "@/lib/centi-deck";

interface CentiDeckPreviewProps {
  sessionId?: string | null;
  /** Pre-fetched artifact — when provided, skips network fetch. Used by fix-preview. */
  artifactOverride?: CentiDeckArtifactPayload | null;
  startSlide?: number;
  onSlideChange?: (slideIndex: number) => void;
  mode?: CentiDeckRuntimeMode;
  className?: string;
}

type LoadState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; artifact: CentiDeckArtifactPayload }
  | { status: "empty" }
  | { status: "error"; message: string };

export default function CentiDeckPreview({
  sessionId = null,
  artifactOverride = null,
  startSlide = 0,
  onSlideChange,
  mode = "interactive",
  className = "",
}: CentiDeckPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const runtimeRef = useRef<CentiDeckRuntime | null>(null);
  const [state, setState] = useState<LoadState>({ status: "idle" });

  // Fetch or adopt artifact
  useEffect(() => {
    if (artifactOverride) {
      setState({ status: "ready", artifact: artifactOverride });
      return;
    }
    if (!sessionId) {
      setState({ status: "empty" });
      return;
    }
    let cancelled = false;
    setState({ status: "loading" });
    getLatestSessionPresentationCentiDeckArtifact(sessionId)
      .then((artifact) => {
        if (cancelled) return;
        if (!artifact) {
          setState({ status: "empty" });
          return;
        }
        setState({ status: "ready", artifact });
      })
      .catch((error: Error) => {
        if (cancelled) return;
        setState({ status: "error", message: error.message || "加载失败" });
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, artifactOverride]);

  // Mount runtime when artifact becomes ready
  useEffect(() => {
    if (state.status !== "ready" || !containerRef.current) return;
    const container = containerRef.current;
    const runtime = new CentiDeckRuntime();
    runtimeRef.current = runtime;
    let cancelled = false;

    loadAllCentiDeckModules(state.artifact.slides)
      .then((loaded) => {
        if (cancelled) return;
        runtime.mount(
          container,
          { slides: loaded, theme: state.artifact.theme ?? null },
          {
            mode,
            startSlide,
            onSlideChange: (idx) => {
              onSlideChange?.(idx);
            },
          }
        );
      })
      .catch((error: Error) => {
        if (cancelled) return;
        setState({ status: "error", message: error.message || "模块加载失败" });
      });

    return () => {
      cancelled = true;
      runtime.unmount();
      if (runtimeRef.current === runtime) {
        runtimeRef.current = null;
      }
    };
    // We intentionally exclude startSlide/onSlideChange from deps so that only
    // artifact changes cause remount. External slide control is handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.status === "ready" ? state.artifact : null, mode]);

  // React to external startSlide changes
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) return;
    if (runtime.activeIndex === startSlide) return;
    runtime.goTo(startSlide);
  }, [startSlide]);

  if (state.status === "loading" || state.status === "idle") {
    return (
      <div
        className={`flex h-full w-full items-center justify-center text-sm text-slate-400 ${className}`}
      >
        正在加载演示稿…
      </div>
    );
  }
  if (state.status === "empty") {
    return (
      <div
        className={`flex h-full w-full items-center justify-center text-sm text-slate-400 ${className}`}
      >
        尚未生成演示稿
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div
        className={`flex h-full w-full items-center justify-center text-sm text-rose-400 ${className}`}
      >
        加载失败：{state.message}
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`relative h-full w-full overflow-hidden ${className}`}
      data-preview-mode={mode}
    />
  );
}

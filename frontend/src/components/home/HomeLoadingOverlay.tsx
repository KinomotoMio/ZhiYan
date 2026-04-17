"use client";

import type { CSSProperties } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

type LoaderStage = "visible" | "exit" | "hidden";

const EXIT_DURATION_MS = 720;

const overlayStyle: CSSProperties = {
  background:
    "radial-gradient(circle at 20% 18%, rgba(255, 255, 255, 0.92), transparent 34%), radial-gradient(circle at 78% 16%, rgba(0, 75, 132, 0.1), transparent 24%), linear-gradient(145deg, rgba(247, 249, 252, 0.97) 0%, rgba(240, 243, 248, 0.97) 48%, rgba(230, 237, 246, 0.94) 100%)",
};

const backdropStyle: CSSProperties = {
  backdropFilter: "blur(24px)",
  WebkitBackdropFilter: "blur(24px)",
};

const meshStyle: CSSProperties = {
  background:
    "linear-gradient(115deg, rgba(15, 23, 42, 0.022) 0%, rgba(15, 23, 42, 0) 35%, rgba(0, 75, 132, 0.08) 100%), repeating-linear-gradient(90deg, rgba(148, 163, 184, 0.09) 0, rgba(148, 163, 184, 0.09) 1px, transparent 1px, transparent 92px), repeating-linear-gradient(180deg, rgba(148, 163, 184, 0.06) 0, rgba(148, 163, 184, 0.06) 1px, transparent 1px, transparent 92px)",
  maskImage: "radial-gradient(circle at center, black 42%, transparent 88%)",
  WebkitMaskImage: "radial-gradient(circle at center, black 42%, transparent 88%)",
  animation: "zy-home-loader-mesh 8s ease-in-out infinite",
};

const eyebrowStyle: CSSProperties = {
  border: "1px solid rgba(148, 163, 184, 0.26)",
  background: "rgba(255, 255, 255, 0.46)",
  padding: "0.45rem 0.9rem",
  borderRadius: "999px",
  fontSize: "0.69rem",
  lineHeight: 1,
  letterSpacing: "0.3em",
  color: "rgba(71, 85, 105, 0.82)",
  backdropFilter: "blur(14px)",
  WebkitBackdropFilter: "blur(14px)",
  animation:
    "zy-home-loader-caption 700ms cubic-bezier(0.22, 0.86, 0.24, 1) 160ms both",
};

const titleCnStyle: CSSProperties = {
  fontSize: "clamp(3.7rem, 12vw, 5.8rem)",
  lineHeight: 0.92,
  letterSpacing: "0.22em",
  textIndent: "0.22em",
  fontWeight: 600,
  color: "rgba(15, 23, 42, 0.94)",
  animation:
    "zy-home-loader-title 1s cubic-bezier(0.16, 1, 0.3, 1) 180ms both",
};

const titleEnStyle: CSSProperties = {
  fontSize: "clamp(0.76rem, 1.6vw, 0.94rem)",
  lineHeight: 1.2,
  letterSpacing: "0.72em",
  textIndent: "0.72em",
  color: "rgba(71, 85, 105, 0.72)",
  animation:
    "zy-home-loader-title 1s cubic-bezier(0.16, 1, 0.3, 1) 260ms both",
};

const lineStyle: CSSProperties = {
  height: "1px",
  background: "rgba(148, 163, 184, 0.24)",
};

const lineCoreStyle: CSSProperties = {
  display: "block",
  width: "42%",
  height: "100%",
  background:
    "linear-gradient(90deg, rgba(255, 255, 255, 0) 0%, rgba(0, 75, 132, 0.14) 18%, rgba(255, 255, 255, 1) 50%, rgba(210, 11, 23, 0.2) 82%, rgba(255, 255, 255, 0) 100%)",
  boxShadow:
    "0 0 18px rgba(0, 75, 132, 0.18), 0 0 28px rgba(255, 255, 255, 0.65)",
  animation:
    "zy-home-loader-line 2.3s cubic-bezier(0.22, 0.86, 0.24, 1) infinite",
};

const captionStyle: CSSProperties = {
  fontSize: "0.9rem",
  lineHeight: 1.75,
  letterSpacing: "0.08em",
  color: "rgba(71, 85, 105, 0.9)",
  whiteSpace: "nowrap",
  animation:
    "zy-home-loader-caption 850ms cubic-bezier(0.22, 0.86, 0.24, 1) 360ms both",
};

function buildRibbonStyle(
  background: string,
  marginLeft: string,
  marginTop: string,
  animationDelay?: string
): CSSProperties {
  return {
    position: "absolute",
    left: "50%",
    top: "50%",
    width: "min(62rem, 92vw)",
    height: "10rem",
    borderRadius: "999px",
    filter: "blur(18px)",
    transformOrigin: "center",
    opacity: 0,
    mixBlendMode: "screen",
    background,
    marginLeft,
    marginTop,
    animation:
      "zy-home-loader-ribbon 2.6s cubic-bezier(0.22, 0.86, 0.24, 1) infinite",
    animationDelay,
  };
}

function buildOrbStyle(
  background: string,
  position: Partial<CSSProperties>,
  animationDelay?: string
): CSSProperties {
  return {
    position: "absolute",
    width: "24rem",
    height: "24rem",
    borderRadius: "999px",
    filter: "blur(68px)",
    opacity: 0.28,
    background,
    animation: "zy-home-loader-orb 6.8s ease-in-out infinite",
    animationDelay,
    ...position,
  };
}

const ribbonOneStyle = buildRibbonStyle(
  "linear-gradient(90deg, rgba(210, 11, 23, 0) 0%, rgba(210, 11, 23, 0.22) 20%, rgba(255, 255, 255, 0.86) 50%, rgba(0, 75, 132, 0.24) 78%, rgba(0, 75, 132, 0) 100%)",
  "-54vw",
  "-12rem"
);

const ribbonTwoStyle = buildRibbonStyle(
  "linear-gradient(90deg, rgba(255, 255, 255, 0) 0%, rgba(0, 75, 132, 0.16) 18%, rgba(255, 255, 255, 0.88) 52%, rgba(210, 11, 23, 0.14) 82%, rgba(210, 11, 23, 0) 100%)",
  "-46vw",
  "1rem",
  "0.42s"
);

const ribbonThreeStyle = buildRibbonStyle(
  "linear-gradient(90deg, rgba(0, 75, 132, 0) 0%, rgba(0, 75, 132, 0.12) 24%, rgba(255, 255, 255, 0.8) 50%, rgba(210, 11, 23, 0.16) 72%, rgba(210, 11, 23, 0) 100%)",
  "-51vw",
  "10rem",
  "0.84s"
);

const orbLeftStyle = buildOrbStyle("rgba(210, 11, 23, 0.24)", {
  left: "-5rem",
  top: "20%",
});

const orbRightStyle = buildOrbStyle(
  "rgba(0, 75, 132, 0.24)",
  {
    right: "-6rem",
    bottom: "14%",
  },
  "1.4s"
);

export default function HomeLoadingOverlay({
  loading,
  onStageChange,
}: {
  loading: boolean;
  onStageChange?: (stage: LoaderStage) => void;
}) {
  const [stage, setStage] = useState<LoaderStage>("visible");

  const loadingRef = useRef(loading);
  const minElapsedRef = useRef(false);
  const exitedRef = useRef(false);
  const exitTimerRef = useRef<number | null>(null);

  const exitLoader = useCallback(() => {
    if (exitedRef.current) return;
    exitedRef.current = true;
    setStage("exit");
    onStageChange?.("exit");

    exitTimerRef.current = window.setTimeout(() => {
      setStage("hidden");
      onStageChange?.("hidden");
    }, EXIT_DURATION_MS);
  }, [onStageChange]);

  const maybeExit = useCallback(() => {
    if (!loadingRef.current && minElapsedRef.current) {
      exitLoader();
    }
  }, [exitLoader]);

  useEffect(() => {
    loadingRef.current = loading;

    const checkTimer = window.setTimeout(() => {
      maybeExit();
    }, 0);

    return () => {
      window.clearTimeout(checkTimer);
    };
  }, [loading, maybeExit]);

  useEffect(() => {
    onStageChange?.("visible");

    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const reducedMotion = media.matches;
    const minDuration = reducedMotion ? 220 : 1850;
    const forceExit = reducedMotion ? 700 : 3600;

    const minTimer = window.setTimeout(() => {
      minElapsedRef.current = true;
      maybeExit();
    }, minDuration);

    const forceTimer = window.setTimeout(() => {
      exitLoader();
    }, forceExit);

    return () => {
      window.clearTimeout(minTimer);
      window.clearTimeout(forceTimer);
      if (exitTimerRef.current !== null) {
        window.clearTimeout(exitTimerRef.current);
      }
    };
  }, [exitLoader, maybeExit, onStageChange]);

  if (stage === "hidden") {
    return null;
  }

  return (
    <div
      aria-hidden="true"
      className={cn(
        "zy-home-loader pointer-events-none fixed inset-0 z-[90] overflow-hidden transition-[opacity,filter,transform] duration-[720ms] ease-[cubic-bezier(0.16,1,0.3,1)]",
        stage === "exit"
          ? "opacity-0 blur-sm saturate-[1.08] scale-[1.02]"
          : "opacity-100 blur-0 scale-100"
      )}
      style={overlayStyle}
    >
      <div className="absolute inset-0" style={backdropStyle} />
      <div className="absolute inset-0 opacity-70" style={meshStyle} />
      <div aria-hidden="true" style={ribbonOneStyle} />
      <div aria-hidden="true" style={ribbonTwoStyle} />
      <div aria-hidden="true" style={ribbonThreeStyle} />
      <div aria-hidden="true" style={orbLeftStyle} />
      <div aria-hidden="true" style={orbRightStyle} />

      <div className="relative z-10 flex h-full items-center justify-center px-6">
        <div
          className="flex w-full flex-col items-center text-center"
          style={{ maxWidth: "32rem" }}
        >
          <span style={eyebrowStyle}>
            AI PRESENTATION INTELLIGENCE
          </span>
          <div className="mt-6 flex flex-col items-center gap-2">
            <p style={titleCnStyle}>知演</p>
            <p style={titleEnStyle}>ZHIYAN</p>
          </div>
          <div
            className="mt-7 w-full overflow-hidden rounded-full"
            style={{ ...lineStyle, maxWidth: "24rem" }}
          >
            <span style={lineCoreStyle} />
          </div>
          <p className="mt-5" style={captionStyle}>
            让知识沿着流动的结构，凝成更清晰的演示表达。
          </p>
        </div>
      </div>
    </div>
  );
}

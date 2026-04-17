"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

type LoaderStage = "visible" | "exit" | "hidden";

const EXIT_DURATION_MS = 720;

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
    >
      <div className="zy-home-loader__backdrop absolute inset-0" />
      <div className="zy-home-loader__mesh absolute inset-0 opacity-70" />
      <div className="zy-home-loader__ribbon zy-home-loader__ribbon--one" />
      <div className="zy-home-loader__ribbon zy-home-loader__ribbon--two" />
      <div className="zy-home-loader__ribbon zy-home-loader__ribbon--three" />
      <div className="zy-home-loader__orb zy-home-loader__orb--left" />
      <div className="zy-home-loader__orb zy-home-loader__orb--right" />

      <div className="relative z-10 flex h-full items-center justify-center px-6">
        <div className="flex w-full max-w-[32rem] flex-col items-center text-center">
          <span className="zy-home-loader__eyebrow">
            AI PRESENTATION INTELLIGENCE
          </span>
          <div className="mt-6 flex flex-col items-center gap-2">
            <p className="zy-home-loader__title-cn">知演</p>
            <p className="zy-home-loader__title-en">ZHIYAN</p>
          </div>
          <div className="zy-home-loader__line mt-7 w-full max-w-[24rem] overflow-hidden rounded-full">
            <span className="zy-home-loader__line-core" />
          </div>
          <p className="zy-home-loader__caption mt-5 whitespace-nowrap">
            让知识沿着流动的结构，凝成更清晰的演示表达。
          </p>
        </div>
      </div>
    </div>
  );
}

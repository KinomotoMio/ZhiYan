"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import CentiDeckPreview from "@/components/editor/CentiDeckPreview";
import { getSessionEditorPath } from "@/lib/routes";
import { useCentiDeckRoomSync } from "@/lib/use-centi-deck-room-sync";

export default function SessionPresenterPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = typeof params?.sessionId === "string" ? params.sessionId : "";
  const [slideIndex, setSlideIndex] = useState(0);
  const [slideCount, setSlideCount] = useState(0);

  useCentiDeckRoomSync({
    sessionId: sessionId || null,
    slideIndex,
    onRemoteSlideIndex: (remoteIndex) => setSlideIndex(remoteIndex),
    originLabel: "presenter",
  });

  const goNext = useCallback(() => {
    setSlideIndex((current) => {
      if (slideCount <= 0) return current + 1;
      return Math.min(current + 1, slideCount - 1);
    });
  }, [slideCount]);

  const goPrev = useCallback(() => {
    setSlideIndex((current) => Math.max(0, current - 1));
  }, []);

  const handleKey = useCallback(
    (event: KeyboardEvent) => {
      if (
        event.key === "ArrowRight" ||
        event.key === "ArrowDown" ||
        event.key === "PageDown" ||
        event.key === " "
      ) {
        event.preventDefault();
        goNext();
      } else if (
        event.key === "ArrowLeft" ||
        event.key === "ArrowUp" ||
        event.key === "PageUp"
      ) {
        event.preventDefault();
        goPrev();
      }
    },
    [goNext, goPrev]
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [handleKey]);

  // Swipe support for touch devices.
  useEffect(() => {
    let startX = 0;
    let startY = 0;
    const onTouchStart = (event: TouchEvent) => {
      startX = event.touches[0].clientX;
      startY = event.touches[0].clientY;
    };
    const onTouchEnd = (event: TouchEvent) => {
      const dx = event.changedTouches[0].clientX - startX;
      const dy = event.changedTouches[0].clientY - startY;
      if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 50) {
        if (dx < 0) goNext();
        else goPrev();
      }
    };
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchend", onTouchEnd);
    return () => {
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchend", onTouchEnd);
    };
  }, [goNext, goPrev]);

  if (!sessionId) {
    return (
      <div className="flex h-screen items-center justify-center bg-black text-white">
        未指定 session
      </div>
    );
  }

  const atStart = slideIndex <= 0;
  const atEnd = slideCount > 0 && slideIndex >= slideCount - 1;

  return (
    <div className="relative flex h-screen flex-col bg-black">
      <div className="absolute inset-0">
        <CentiDeckPreview
          sessionId={sessionId}
          startSlide={slideIndex}
          onSlideChange={setSlideIndex}
          onReady={({ slideCount: nextCount }) => setSlideCount(nextCount)}
          mode="presenter"
        />
      </div>

      <div className="pointer-events-none absolute right-4 top-4 z-10 flex items-center gap-2">
        <Link
          href={getSessionEditorPath(sessionId)}
          className="pointer-events-auto rounded-full border border-white/20 bg-black/60 px-3 py-1 text-xs text-white backdrop-blur hover:bg-white/10"
        >
          退出演示
        </Link>
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-6 z-10 flex items-center justify-center gap-3">
        <button
          type="button"
          onClick={goPrev}
          disabled={atStart}
          className="pointer-events-auto inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/20 bg-black/60 text-white backdrop-blur transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="上一页"
        >
          ‹
        </button>
        <div className="pointer-events-auto min-w-[5.5rem] rounded-full border border-white/20 bg-black/60 px-4 py-1.5 text-center text-xs font-medium text-white backdrop-blur">
          {slideCount > 0 ? `${slideIndex + 1} / ${slideCount}` : "—"}
        </div>
        <button
          type="button"
          onClick={goNext}
          disabled={atEnd}
          className="pointer-events-auto inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/20 bg-black/60 text-white backdrop-blur transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="下一页"
        >
          ›
        </button>
      </div>
    </div>
  );
}

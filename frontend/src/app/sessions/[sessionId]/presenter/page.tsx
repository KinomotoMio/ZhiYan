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

  useCentiDeckRoomSync({
    sessionId: sessionId || null,
    slideIndex,
    onRemoteSlideIndex: (remoteIndex) => setSlideIndex(remoteIndex),
    originLabel: "presenter",
  });

  const handleKey = useCallback((event: KeyboardEvent) => {
    if (event.key === "ArrowRight" || event.key === "PageDown" || event.key === " ") {
      event.preventDefault();
      setSlideIndex((current) => current + 1);
    } else if (event.key === "ArrowLeft" || event.key === "PageUp") {
      event.preventDefault();
      setSlideIndex((current) => Math.max(0, current - 1));
    }
  }, []);

  useEffect(() => {
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [handleKey]);

  if (!sessionId) {
    return (
      <div className="flex h-screen items-center justify-center bg-black text-white">
        未指定 session
      </div>
    );
  }

  return (
    <div className="relative flex h-screen flex-col bg-black">
      <div className="absolute inset-0">
        <CentiDeckPreview
          sessionId={sessionId}
          startSlide={slideIndex}
          onSlideChange={setSlideIndex}
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
    </div>
  );
}

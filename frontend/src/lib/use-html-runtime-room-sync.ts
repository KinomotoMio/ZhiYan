"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { getHtmlRuntimeRoomId } from "@/lib/routes";

export type HtmlRuntimeRoomStatus = "idle" | "unsupported" | "connected";

interface HtmlRuntimeRoomMessage {
  type: "html-runtime-room-state";
  roomId: string;
  sourceId: string;
  slideIndex: number;
}

function isRoomMessage(value: unknown): value is HtmlRuntimeRoomMessage {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<HtmlRuntimeRoomMessage>;
  return (
    candidate.type === "html-runtime-room-state" &&
    typeof candidate.roomId === "string" &&
    typeof candidate.sourceId === "string" &&
    typeof candidate.slideIndex === "number" &&
    Number.isFinite(candidate.slideIndex)
  );
}

function createSourceId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `html-room-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`;
}

interface UseHtmlRuntimeRoomSyncOptions {
  sessionId: string | null;
  room?: string | null;
  slideIndex: number;
  onRemoteSlideChange?: (slideIndex: number) => void;
  enabled?: boolean;
}

interface UseHtmlRuntimeRoomSyncResult {
  roomId: string | null;
  status: HtmlRuntimeRoomStatus;
}

export function useHtmlRuntimeRoomSync({
  sessionId,
  room = null,
  slideIndex,
  onRemoteSlideChange,
  enabled = true,
}: UseHtmlRuntimeRoomSyncOptions): UseHtmlRuntimeRoomSyncResult {
  const roomId = useMemo(
    () => (sessionId ? getHtmlRuntimeRoomId(sessionId, room) : null),
    [room, sessionId]
  );
  const [status, setStatus] = useState<HtmlRuntimeRoomStatus>("idle");
  const channelRef = useRef<BroadcastChannel | null>(null);
  const sourceIdRef = useRef<string>(createSourceId());
  const currentSlideRef = useRef(slideIndex);

  useEffect(() => {
    currentSlideRef.current = slideIndex;
  }, [slideIndex]);

  useEffect(() => {
    if (!enabled || !roomId) {
      setStatus("idle");
      return;
    }
    if (typeof BroadcastChannel === "undefined") {
      setStatus("unsupported");
      return;
    }

    const channel = new BroadcastChannel(`html-runtime-room:${roomId}`);
    channelRef.current = channel;
    setStatus("connected");
    channel.onmessage = (event) => {
      if (!isRoomMessage(event.data)) return;
      if (event.data.roomId !== roomId) return;
      if (event.data.sourceId === sourceIdRef.current) return;
      const nextSlide = Math.max(0, Math.trunc(event.data.slideIndex));
      if (nextSlide === currentSlideRef.current) return;
      currentSlideRef.current = nextSlide;
      onRemoteSlideChange?.(nextSlide);
    };

    return () => {
      channel.close();
      if (channelRef.current === channel) {
        channelRef.current = null;
      }
      setStatus("idle");
    };
  }, [enabled, onRemoteSlideChange, roomId]);

  useEffect(() => {
    if (!enabled || !roomId || !channelRef.current) return;
    channelRef.current.postMessage({
      type: "html-runtime-room-state",
      roomId,
      sourceId: sourceIdRef.current,
      slideIndex: Math.max(0, Math.trunc(slideIndex)),
    } satisfies HtmlRuntimeRoomMessage);
  }, [enabled, roomId, slideIndex]);

  return { roomId, status };
}

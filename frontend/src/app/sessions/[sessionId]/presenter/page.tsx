"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import HtmlRuntimePreview from "@/components/slides/HtmlRuntimePreview";
import {
  getLatestSessionPresentation,
  getLatestSessionPresentationHtmlRender,
  type HtmlRuntimeRenderPayload,
} from "@/lib/api";
import { getHtmlRuntimeRoomId, getSessionEditorPath } from "@/lib/routes";
import { useHtmlRuntimeRoomSync } from "@/lib/use-html-runtime-room-sync";

function normalizeSlideIndex(value: string | null, slideCount: number): number {
  const parsed = Number.parseInt(String(value || "1"), 10);
  if (!Number.isFinite(parsed)) return 0;
  const zeroBased = Math.max(0, parsed - 1);
  if (slideCount <= 0) return zeroBased;
  return Math.min(zeroBased, slideCount - 1);
}

function roomStatusLabel(status: "idle" | "unsupported" | "connected"): string {
  if (status === "connected") return "房间同步已连接";
  if (status === "unsupported") return "当前浏览器不支持房间同步";
  return "房间同步未启用";
}

export default function SessionPresenterPage() {
  const params = useParams<{ sessionId: string }>();
  const searchParams = useSearchParams();
  const sessionId = typeof params?.sessionId === "string" ? params.sessionId : "";
  const requestedRoom = searchParams.get("room");
  const requestedSlide = searchParams.get("slide");

  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [title, setTitle] = useState("HTML Presenter");
  const [htmlRender, setHtmlRender] = useState<HtmlRuntimeRenderPayload | null>(null);
  const [slideIndex, setSlideIndex] = useState(0);
  const [overlayVisible, setOverlayVisible] = useState(true);
  const [drilldownOpen, setDrilldownOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      if (!sessionId) {
        setErrorMessage("缺少会话 ID，无法打开 Presenter。");
        setLoading(false);
        return;
      }
      setLoading(true);
      setErrorMessage(null);
      try {
        const latest = await getLatestSessionPresentation(sessionId);
        if (!latest || latest.output_mode !== "html") {
          throw new Error("当前会话不是 HTML Runtime 演示稿。");
        }
        const render = await getLatestSessionPresentationHtmlRender(sessionId);
        if (!render?.documentHtml) {
          throw new Error("HTML Runtime render payload 尚未就绪。");
        }
        if (cancelled) return;
        setTitle(render.title || latest.presentation?.title || "HTML Presenter");
        setHtmlRender(render);
        setSlideIndex(normalizeSlideIndex(requestedSlide, render.slideCount || 0));
      } catch (error) {
        if (cancelled) return;
        setHtmlRender(null);
        setErrorMessage(error instanceof Error ? error.message : "打开 Presenter 失败。");
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [requestedSlide, sessionId]);

  const resolvedRoomId = useMemo(
    () => (sessionId ? getHtmlRuntimeRoomId(sessionId, requestedRoom) : null),
    [requestedRoom, sessionId]
  );
  const { status: roomStatus } = useHtmlRuntimeRoomSync({
    sessionId,
    room: requestedRoom,
    slideIndex,
    onRemoteSlideChange: setSlideIndex,
    enabled: Boolean(htmlRender?.documentHtml),
  });

  const slideCount = htmlRender?.slideCount ?? 0;
  const canDrilldown = Boolean(htmlRender?.presenterCapabilities?.drilldowns);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-black text-sm text-white/80">
        正在加载 Presenter...
      </div>
    );
  }

  if (errorMessage || !htmlRender?.documentHtml) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4 bg-black px-6 text-center text-white">
        <div className="text-xl font-semibold">无法打开 Presenter</div>
        <div className="max-w-xl text-sm text-white/70">{errorMessage || "缺少可播放内容。"}</div>
        <Link
          href={getSessionEditorPath(sessionId)}
          className="rounded-full border border-white/20 px-4 py-2 text-sm text-white transition hover:bg-white/10"
        >
          返回编辑器
        </Link>
      </div>
    );
  }

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-black text-white">
      {overlayVisible ? (
        <div className="absolute inset-x-0 top-0 z-20 bg-gradient-to-b from-black/80 via-black/50 to-transparent px-6 py-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-2">
              <Link
                href={getSessionEditorPath(sessionId, { slide: slideIndex + 1 })}
                className="inline-flex items-center rounded-full border border-white/20 px-3 py-1.5 text-xs font-medium text-white/80 transition hover:bg-white/10 hover:text-white"
              >
                返回编辑器
              </Link>
              <div>
                <div className="text-lg font-semibold">{title}</div>
                <div className="mt-1 text-xs text-white/65">
                  第 {Math.min(slideIndex + 1, Math.max(slideCount, 1))} / {Math.max(slideCount, 1)} 页
                </div>
              </div>
              <div className="text-xs text-white/55">
                {roomStatusLabel(roomStatus)}
                {resolvedRoomId ? ` · ${resolvedRoomId}` : ""}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setSlideIndex((current) => Math.max(0, current - 1))}
                disabled={slideIndex <= 0}
                className="rounded-full border border-white/20 px-4 py-2 text-sm text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
              >
                上一页
              </button>
              <button
                type="button"
                onClick={() => setSlideIndex((current) => Math.min(Math.max(slideCount - 1, 0), current + 1))}
                disabled={slideIndex >= slideCount - 1}
                className="rounded-full border border-white/20 px-4 py-2 text-sm text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
              >
                下一页
              </button>
              <button
                type="button"
                onClick={() => setDrilldownOpen((current) => !current)}
                disabled={!canDrilldown}
                className="rounded-full border border-white/20 px-4 py-2 text-sm text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {drilldownOpen ? "关闭 Drilldown" : "Drilldown"}
              </button>
              <button
                type="button"
                onClick={() => setOverlayVisible(false)}
                className="rounded-full border border-white/20 px-4 py-2 text-sm text-white transition hover:bg-white/10"
              >
                隐藏控件
              </button>
            </div>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOverlayVisible(true)}
          className="absolute left-6 top-6 z-20 rounded-full border border-white/20 bg-black/45 px-4 py-2 text-sm text-white transition hover:bg-black/60"
        >
          显示控件
        </button>
      )}
      {drilldownOpen && (
        <div className="absolute right-6 top-24 z-20 max-w-xs rounded-2xl border border-white/10 bg-black/70 p-4 text-sm text-white/80 shadow-2xl backdrop-blur">
          当前 runtime payload 未声明可用的 drilldown 交互，这里只保留开关状态，不做前端推导。
        </div>
      )}
      <HtmlRuntimePreview
        renderPayload={htmlRender}
        startSlide={slideIndex}
        onSlideChange={setSlideIndex}
        className="h-full w-full bg-black"
      />
    </div>
  );
}

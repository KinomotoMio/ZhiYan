"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { getPublicShareHtml, getPublicSharePlayback, type PublicSharePlayback } from "@/lib/api";
import RevealPreview from "@/components/slides/RevealPreview";

interface PublicSharePlayerProps {
  token: string;
}

interface PublicSharePlayerViewProps {
  loading?: boolean;
  errorMessage?: string | null;
  playback?: PublicSharePlayback | null;
  htmlContent?: string | null;
}

function FullscreenMessage({
  title,
  description,
  loading = false,
}: {
  title: string;
  description: string;
  loading?: boolean;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-center text-white">
      <div className="max-w-xl space-y-4">
        <div className="flex items-center justify-center gap-3">
          {loading ? <Loader2 className="h-5 w-5 animate-spin text-cyan-300" /> : null}
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        </div>
        <p className="text-sm leading-6 text-slate-300">{description}</p>
      </div>
    </div>
  );
}

export function PublicSharePlayerView({
  loading = false,
  errorMessage = null,
  playback = null,
  htmlContent = null,
}: PublicSharePlayerViewProps) {
  if (loading) {
    return (
      <FullscreenMessage
        title="正在加载演示"
        description="请稍等，正在准备这份公开分享的播放内容。"
        loading
      />
    );
  }

  if (errorMessage) {
    return (
      <FullscreenMessage
        title="无法打开分享链接"
        description={errorMessage}
      />
    );
  }

  if (!playback) {
    return (
      <FullscreenMessage
        title="暂无可播放内容"
        description="这条分享链接目前还没有可展示的演示稿。"
      />
    );
  }

  const isHtmlMode = playback.outputMode === "html";
  const canRender = isHtmlMode ? Boolean(htmlContent) : Boolean(playback.presentation);

  if (!canRender) {
    return (
      <FullscreenMessage
        title="暂无可播放内容"
        description="这条分享链接目前还没有可展示的演示稿。"
      />
    );
  }

  return (
    <div className="relative h-screen overflow-hidden bg-black">
      <div className="pointer-events-none absolute top-0 left-0 right-0 z-10 bg-gradient-to-b from-black/55 to-transparent px-6 py-5">
        <p className="text-sm font-medium tracking-[0.18em] text-cyan-200/90 uppercase">Shared Demo</p>
        <h1 className="mt-2 text-xl font-semibold text-white">{playback.title}</h1>
      </div>
      <RevealPreview
        presentation={isHtmlMode ? null : playback.presentation}
        htmlContent={isHtmlMode ? htmlContent : null}
      />
    </div>
  );
}

export default function PublicSharePlayer({ token }: PublicSharePlayerProps) {
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [playback, setPlayback] = useState<PublicSharePlayback | null>(null);
  const [htmlContent, setHtmlContent] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      setLoading(true);
      setErrorMessage(null);
      try {
        const nextPlayback = await getPublicSharePlayback(token);
        if (cancelled) return;
        setPlayback(nextPlayback);

        if (nextPlayback.outputMode === "html") {
          const nextHtml = await getPublicShareHtml(token);
          if (cancelled) return;
          setHtmlContent(nextHtml);
        } else {
          setHtmlContent(null);
        }
      } catch (error) {
        if (cancelled) return;
        setPlayback(null);
        setHtmlContent(null);
        setErrorMessage(
          error instanceof Error ? error.message : "分享链接无效、已失效，或当前暂无可播放内容。"
        );
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
  }, [token]);

  return (
    <PublicSharePlayerView
      loading={loading}
      errorMessage={errorMessage}
      playback={playback}
      htmlContent={htmlContent}
    />
  );
}

"use client";

import { useRef, useState, useEffect } from "react";
import type { Slide } from "@/types/slide";
import { Skeleton } from "@/components/ui/skeleton";
import SlidePreview from "./SlidePreview";
import HtmlRuntimePreview from "./HtmlRuntimePreview";
import type { HtmlRuntimeRenderPayload } from "@/lib/api";
import type { IssueDecisionStatus } from "@/lib/verification-issues";

interface SlideIssueMeta {
  hard: number;
  advisory: number;
  total: number;
  decision: IssueDecisionStatus;
}

interface SlideThumbnailProps {
  slide: Slide;
  index: number;
  isActive: boolean;
  onClick: () => void;
  htmlRender?: HtmlRuntimeRenderPayload | null;
  htmlDocument?: string | null;
  htmlStartSlide?: number;
  issueMeta?: SlideIssueMeta;
  onIssueClick?: () => void;
  forceVisible?: boolean;
}

export default function SlideThumbnail({
  slide,
  index,
  isActive,
  onClick,
  htmlRender = null,
  htmlDocument,
  htmlStartSlide,
  issueMeta,
  onIssueClick,
  forceVisible = false,
}: SlideThumbnailProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "100px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const hasIssue = Boolean(issueMeta && issueMeta.total > 0);
  const visible = forceVisible || isVisible;
  const statusColor =
    issueMeta && issueMeta.hard > 0
      ? "bg-red-500"
      : "bg-amber-500";
  const isHandled = issueMeta && issueMeta.decision !== "pending";

  return (
    <div className="flex w-full min-w-0 gap-2 items-start" ref={ref}>
      <div className="flex flex-col items-center gap-1 w-4 shrink-0">
        <span className="text-xs text-muted-foreground mt-1">
          {index + 1}
        </span>
        {hasIssue && issueMeta && onIssueClick && (
          <button
            type="button"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onIssueClick();
            }}
            className={`relative flex min-h-5 min-w-5 items-center justify-center rounded-full border border-white px-1 text-[10px] font-semibold text-white shadow ${
              statusColor
            } ${isHandled ? "opacity-50" : "opacity-100"}`}
            title={`hard ${issueMeta.hard} / advisory ${issueMeta.advisory}`}
          >
            {issueMeta.total}
            {isHandled && (
              <span className="absolute -bottom-0.5 -right-0.5 h-1.5 w-1.5 rounded-full border border-white bg-slate-700" />
            )}
          </button>
        )}
      </div>
      <div className="relative min-w-0 flex-1">
        {visible ? (
          htmlRender || htmlDocument ? (
            <div
              onClick={onClick}
              className={`relative aspect-[16/9] cursor-pointer overflow-hidden rounded-lg border bg-white transition-shadow ${
                isActive ? "ring-2 ring-primary shadow-lg" : "hover:shadow-md"
              }`}
            >
              <div className="absolute inset-0">
                <HtmlRuntimePreview
                  renderPayload={htmlRender}
                  documentHtml={htmlDocument}
                  startSlide={htmlStartSlide ?? index}
                  thumbnailMode
                  className="pointer-events-none"
                />
              </div>
            </div>
          ) : (
            <SlidePreview
              slide={slide}
              onClick={onClick}
              isActive={isActive}
              className="w-full"
            />
          )
        ) : (
          <Skeleton className="w-full aspect-[16/9] rounded" />
        )}
      </div>
    </div>
  );
}

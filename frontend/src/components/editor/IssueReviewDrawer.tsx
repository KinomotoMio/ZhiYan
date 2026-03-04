"use client";

import { X, Loader2 } from "lucide-react";
import SlidePreview from "@/components/slides/SlidePreview";
import type { Slide } from "@/types/slide";
import type {
  IssueDecisionStatus,
  SlideIssueGroup,
} from "@/lib/verification-issues";

interface IssueReviewDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  slides: Slide[];
  groupedIssues: Map<string, SlideIssueGroup>;
  issueDecisionBySlideId: Record<string, IssueDecisionStatus>;
  focusSlideId: string | null;
  onFocusSlide: (slideId: string) => void;
  fixPreviewBySlideId: Map<string, Slide>;
  selectedFixPreviewSlideIds: string[];
  waitingFixReview: boolean;
  previewingFix: boolean;
  applyingFix: boolean;
  skippingFix: boolean;
  onGeneratePreview: (slideId: string) => void;
  onToggleApplySlide: (slideId: string) => void;
  onApplySelected: () => void;
  onSkipAll: () => void;
  onDiscardPreview: () => void;
  onMarkHandled: (slideId: string) => void;
}

const DECISION_LABEL: Record<IssueDecisionStatus, string> = {
  pending: "待处理",
  applied: "已应用",
  skipped: "已跳过",
  discarded: "已丢弃",
};

function decisionStyle(status: IssueDecisionStatus): string {
  if (status === "applied") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (status === "skipped") return "bg-slate-100 text-slate-600 border-slate-200";
  if (status === "discarded") return "bg-zinc-100 text-zinc-600 border-zinc-200";
  return "bg-amber-50 text-amber-700 border-amber-200";
}

export default function IssueReviewDrawer({
  open,
  onOpenChange,
  slides,
  groupedIssues,
  issueDecisionBySlideId,
  focusSlideId,
  onFocusSlide,
  fixPreviewBySlideId,
  selectedFixPreviewSlideIds,
  waitingFixReview,
  previewingFix,
  applyingFix,
  skippingFix,
  onGeneratePreview,
  onToggleApplySlide,
  onApplySelected,
  onSkipAll,
  onDiscardPreview,
  onMarkHandled,
}: IssueReviewDrawerProps) {
  const orderedSlideIds = slides
    .map((slide) => slide.slideId)
    .filter((slideId) => groupedIssues.has(slideId));

  const activeSlideId = focusSlideId && groupedIssues.has(focusSlideId)
    ? focusSlideId
    : orderedSlideIds[0] ?? null;
  const activeGroup = activeSlideId ? groupedIssues.get(activeSlideId) ?? null : null;
  const activeSlide = activeSlideId
    ? slides.find((slide) => slide.slideId === activeSlideId) ?? null
    : null;
  const activePreview = activeSlideId
    ? fixPreviewBySlideId.get(activeSlideId)
    : undefined;

  let hardCount = 0;
  let advisoryCount = 0;
  for (const group of groupedIssues.values()) {
    hardCount += group.hard;
    advisoryCount += group.advisory;
  }

  return (
    <div className={`fixed inset-0 z-40 ${open ? "pointer-events-auto" : "pointer-events-none"}`}>
      <div
        className={`absolute inset-0 bg-slate-900/20 transition-opacity duration-200 ${
          open ? "opacity-100" : "opacity-0"
        }`}
        onClick={() => onOpenChange(false)}
      />
      <aside
        className={`absolute right-0 top-0 h-full w-[420px] max-w-[92vw] border-l border-slate-200 bg-white shadow-2xl transition-transform duration-200 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex h-12 items-center justify-between border-b border-slate-200 px-4">
          <div className="text-sm font-medium">校验问题</div>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex h-[calc(100%-3rem)] flex-col">
          <div className="border-b border-slate-200 px-4 py-3 text-xs text-slate-600">
            hard {hardCount}，advisory {advisoryCount}
          </div>

          <div className="border-b border-slate-200 px-2 py-2">
            <div className="flex max-h-28 flex-wrap gap-2 overflow-y-auto">
              {orderedSlideIds.map((slideId) => {
                const group = groupedIssues.get(slideId);
                if (!group) return null;
                const status = issueDecisionBySlideId[slideId] ?? "pending";
                const isActive = slideId === activeSlideId;
                return (
                  <button
                    key={slideId}
                    type="button"
                    onClick={() => onFocusSlide(slideId)}
                    className={`rounded border px-2 py-1 text-xs ${
                      isActive
                        ? "border-cyan-500 bg-cyan-50 text-cyan-700"
                        : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                    }`}
                  >
                    {slideId} · H{group.hard}/A{group.advisory} · {DECISION_LABEL[status]}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-3">
            {activeGroup && activeSlide ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium">{activeSlideId}</div>
                  <span
                    className={`rounded border px-2 py-0.5 text-xs ${
                      decisionStyle(issueDecisionBySlideId[activeSlideId] ?? "pending")
                    }`}
                  >
                    {DECISION_LABEL[issueDecisionBySlideId[activeSlideId] ?? "pending"]}
                  </span>
                </div>

                <div className="space-y-2">
                  {activeGroup.issues.map((issue, idx) => (
                    <div
                      key={`${issue.slideId}-${idx}`}
                      className="rounded border border-slate-200 bg-slate-50 p-2"
                    >
                      <div className="mb-1 flex items-center gap-2 text-xs">
                        <span
                          className={`rounded px-1.5 py-0.5 ${
                            issue.tier === "hard"
                              ? "bg-red-100 text-red-700"
                              : "bg-amber-100 text-amber-700"
                          }`}
                        >
                          {issue.tier}
                        </span>
                        <span className="text-slate-500">{issue.category}</span>
                      </div>
                      <p className="text-xs text-slate-700">{issue.message}</p>
                      {issue.suggestion && (
                        <p className="mt-1 text-xs text-slate-500">建议：{issue.suggestion}</p>
                      )}
                    </div>
                  ))}
                </div>

                {activePreview && (
                  <div className="space-y-2">
                    <p className="text-xs text-slate-500">当前页 vs 修复候选</p>
                    <div className="grid grid-cols-2 gap-2">
                      <SlidePreview slide={activeSlide} className="w-full" />
                      <SlidePreview
                        slide={activePreview}
                        className="w-full ring-2 ring-cyan-400/60"
                      />
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-slate-500">当前没有可展示的问题页面。</p>
            )}
          </div>

          <div className="space-y-2 border-t border-slate-200 p-3">
            {activeSlideId && waitingFixReview && (
              <button
                type="button"
                onClick={() => onGeneratePreview(activeSlideId)}
                disabled={previewingFix || applyingFix || skippingFix}
                className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-xs hover:bg-slate-50 disabled:opacity-50"
              >
                {previewingFix && <Loader2 className="mr-1 inline h-3 w-3 animate-spin" />}
                生成该页修复建议
              </button>
            )}
            {activeSlideId && fixPreviewBySlideId.has(activeSlideId) && (
              <button
                type="button"
                onClick={() => onToggleApplySlide(activeSlideId)}
                className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-xs hover:bg-slate-50"
              >
                {selectedFixPreviewSlideIds.includes(activeSlideId)
                  ? "移出应用列表"
                  : "加入应用列表"}
              </button>
            )}
            {activeSlideId && (
              <button
                type="button"
                onClick={() => onMarkHandled(activeSlideId)}
                className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-xs hover:bg-slate-50"
              >
                标记为已处理（不修改）
              </button>
            )}
            {selectedFixPreviewSlideIds.length > 0 && (
              <button
                type="button"
                onClick={onApplySelected}
                disabled={applyingFix || previewingFix || skippingFix}
                className="w-full rounded bg-cyan-600 px-3 py-2 text-xs text-white hover:bg-cyan-500 disabled:opacity-50"
              >
                {applyingFix && <Loader2 className="mr-1 inline h-3 w-3 animate-spin" />}
                按页应用（{selectedFixPreviewSlideIds.length}）
              </button>
            )}
            {fixPreviewBySlideId.size > 0 && (
              <button
                type="button"
                onClick={onDiscardPreview}
                className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-xs hover:bg-slate-50"
              >
                全部丢弃候选
              </button>
            )}
            {waitingFixReview && (
              <button
                type="button"
                onClick={onSkipAll}
                disabled={skippingFix || previewingFix || applyingFix}
                className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-xs hover:bg-slate-50 disabled:opacity-50"
              >
                {skippingFix && <Loader2 className="mr-1 inline h-3 w-3 animate-spin" />}
                完成当前版本
              </button>
            )}
          </div>
        </div>
      </aside>
    </div>
  );
}

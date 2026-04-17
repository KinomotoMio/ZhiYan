"use client";

import { X, Loader2 } from "lucide-react";
import SlidevPreview from "@/components/slides/SlidevPreview";
import type { SlidevFixPreviewState } from "@/lib/api";
import type {
  IssueDecisionStatus,
  SlideIssueGroup,
} from "@/lib/verification-issues";

interface IssueReviewDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isSlidevMode: boolean;
  slidevMetaSlides: Array<Record<string, unknown>>;
  slidevBuildUrl: string | null;
  groupedIssues: Map<string, SlideIssueGroup>;
  issueDecisionBySlideId: Record<string, IssueDecisionStatus>;
  focusSlideId: string | null;
  onFocusSlide: (slideId: string) => void;
  fixPreviewSlidev: SlidevFixPreviewState | null;
  fixPreviewSourceIds: string[];
  waitingFixReview: boolean;
  previewingFix: boolean;
  applyingFix: boolean;
  skippingFix: boolean;
  onGeneratePreview: (slideId: string) => void;
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
  isSlidevMode,
  slidevMetaSlides,
  slidevBuildUrl,
  groupedIssues,
  issueDecisionBySlideId,
  focusSlideId,
  onFocusSlide,
  fixPreviewSlidev,
  fixPreviewSourceIds,
  waitingFixReview,
  previewingFix,
  applyingFix,
  skippingFix,
  onGeneratePreview,
  onApplySelected,
  onSkipAll,
  onDiscardPreview,
  onMarkHandled,
}: IssueReviewDrawerProps) {
  const orderedSlideIds = isSlidevMode
    ? slidevMetaSlides
        .map((slide) => String(slide.slide_id ?? ""))
        .filter((slideId) => slideId && groupedIssues.has(slideId))
    : Array.from(groupedIssues.keys());

  const activeSlideId = focusSlideId && groupedIssues.has(focusSlideId)
    ? focusSlideId
    : orderedSlideIds[0] ?? null;
  const activeGroup = activeSlideId ? groupedIssues.get(activeSlideId) ?? null : null;
  const activeSlideMeta = isSlidevMode && activeSlideId
    ? slidevMetaSlides.find((slide) => String(slide.slide_id ?? "") === activeSlideId) ?? null
    : null;
  const activeSlideIndex = activeSlideId && isSlidevMode
    ? slidevMetaSlides.findIndex((slide) => String(slide.slide_id ?? "") === activeSlideId)
    : -1;

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
            {activeGroup && activeSlideId ? (
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

                {isSlidevMode ? (
                  <div className="space-y-2">
                    <p className="text-xs text-slate-500">
                      {activeSlideMeta
                        ? `${String(activeSlideMeta.title ?? activeSlideId)} · 第 ${activeSlideIndex + 1} 页`
                        : "当前问题页"}
                    </p>
                    {slidevBuildUrl && activeSlideIndex >= 0 ? (
                      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
                        <div className="aspect-video w-full">
                          <SlidevPreview
                            src={slidevBuildUrl}
                            startSlide={activeSlideIndex}
                          />
                        </div>
                      </div>
                    ) : (
                      <div className="rounded border border-slate-200 bg-slate-50 p-3 text-xs leading-6 text-slate-600">
                        当前版本缺少可用的 Slidev build，暂时只展示问题信息。
                      </div>
                    )}
                    {fixPreviewSlidev && activeSlideIndex >= 0 && (
                      <div className="space-y-2">
                        <p className="text-xs text-slate-500">修复预览（真实 Slidev build）</p>
                        <div className="overflow-hidden rounded-lg border border-cyan-200 bg-white">
                          <div className="aspect-video w-full">
                            <SlidevPreview
                              src={fixPreviewSlidev.preview_url}
                              startSlide={activeSlideIndex}
                            />
                          </div>
                        </div>
                        <div className="rounded border border-cyan-200 bg-cyan-50 px-3 py-2 text-xs leading-6 text-cyan-800">
                          当前预览会以整份 deck 形式应用，涉及 {fixPreviewSourceIds.length} 个问题页。
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">本模式的修复扫描即将上线。</p>
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
            {isSlidevMode && fixPreviewSlidev && fixPreviewSourceIds.length > 0 && (
              <div className="rounded border border-cyan-200 bg-cyan-50 px-3 py-2 text-xs leading-6 text-cyan-800">
                当前 deck 修复预览将以整份 Slidev artifact 应用，不再做结构化 page diff。
              </div>
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
            {isSlidevMode && fixPreviewSlidev && fixPreviewSourceIds.length > 0 && (
              <button
                type="button"
                onClick={onApplySelected}
                disabled={applyingFix || previewingFix || skippingFix}
                className="w-full rounded bg-cyan-600 px-3 py-2 text-xs text-white hover:bg-cyan-500 disabled:opacity-50"
              >
                {applyingFix && <Loader2 className="mr-1 inline h-3 w-3 animate-spin" />}
                {`确认并应用当前 deck 预览（${fixPreviewSourceIds.length}）`}
              </button>
            )}
            {fixPreviewSlidev && (
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

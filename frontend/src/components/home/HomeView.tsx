"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  FilePlus2,
  FileText,
  FolderOpenDot,
  Library,
  Presentation,
  Sparkles,
} from "lucide-react";
import {
  createSession,
  getCurrentWorkspace,
  getLatestSessionPresentation,
  getLatestSessionPresentationHtml,
  getLatestSessionPresentationSlidev,
  listSessions,
  listWorkspaceSources,
  removeSession,
  updateSession,
  type PresentationOutputMode,
  type SessionSummary,
  type SlidevDeckResponse,
} from "@/lib/api";
import RecentResultCarousel from "@/components/home/RecentResultCarousel";
import SlidevPreview from "@/components/slides/SlidevPreview";
import SessionListDialog from "@/components/home/SessionListDialog";
import UserMenu from "@/components/settings/UserMenu";
import { useSettingsStatus } from "@/hooks/useSettingsStatus";
import { useAppStore } from "@/lib/store";
import { getSessionEditorPath } from "@/lib/routes";
import type { Presentation as PresentationModel } from "@/types/slide";

const DESKTOP_BREAKPOINT = 1280;
const MOBILE_PREVIEW_COUNT = 2;
const MIN_PREVIEW_COUNT = 1;
const MAX_PREVIEW_COUNT = 3;
const PREVIEW_ITEM_GAP_PX = 6;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function distributePreviewRows({
  totalRows,
  resultTotal,
  draftTotal,
}: {
  totalRows: number;
  resultTotal: number;
  draftTotal: number;
}): { resultCount: number; draftCount: number } {
  const hasResult = resultTotal > 0;
  const hasDraft = draftTotal > 0;

  if (!hasResult && !hasDraft) {
    return { resultCount: MIN_PREVIEW_COUNT, draftCount: MIN_PREVIEW_COUNT };
  }

  let resultCount = hasResult ? MIN_PREVIEW_COUNT : 0;
  let draftCount = hasDraft ? MIN_PREVIEW_COUNT : 0;
  let remaining = Math.max(0, totalRows - resultCount - draftCount);

  while (remaining > 0) {
    const resultCanGrow =
      hasResult &&
      resultCount < MAX_PREVIEW_COUNT &&
      resultCount < Math.min(resultTotal, MAX_PREVIEW_COUNT);
    const draftCanGrow =
      hasDraft &&
      draftCount < MAX_PREVIEW_COUNT &&
      draftCount < Math.min(draftTotal, MAX_PREVIEW_COUNT);

    if (!resultCanGrow && !draftCanGrow) break;

    if (resultCanGrow && !draftCanGrow) {
      resultCount += 1;
      remaining -= 1;
      continue;
    }

    if (draftCanGrow && !resultCanGrow) {
      draftCount += 1;
      remaining -= 1;
      continue;
    }

    const resultRemaining = Math.max(0, resultTotal - resultCount);
    const draftRemaining = Math.max(0, draftTotal - draftCount);

    if (draftRemaining >= resultRemaining) {
      draftCount += 1;
    } else {
      resultCount += 1;
    }
    remaining -= 1;
  }

  return { resultCount, draftCount };
}

function formatUpdatedAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function HomeView() {
  const router = useRouter();
  const setCurrentSessionId = useAppStore((store) => store.setCurrentSessionId);
  const setWorkspaceId = useAppStore((store) => store.setWorkspaceId);

  const leftCardRef = useRef<HTMLElement | null>(null);
  const fixedAreaRef = useRef<HTMLDivElement | null>(null);
  const listAreaRef = useRef<HTMLDivElement | null>(null);
  const resultSectionRef = useRef<HTMLElement | null>(null);
  const resultSectionHeaderRef = useRef<HTMLDivElement | null>(null);
  const draftSectionRef = useRef<HTMLElement | null>(null);
  const draftSectionHeaderRef = useRef<HTMLDivElement | null>(null);
  const itemProbeRef = useRef<HTMLDivElement | null>(null);

  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [workspaceSourceCount, setWorkspaceSourceCount] = useState(0);
  const [latestResultPresentation, setLatestResultPresentation] =
    useState<PresentationModel | null>(null);
  const [latestResultOutputMode, setLatestResultOutputMode] =
    useState<PresentationOutputMode>("structured");
  const [latestResultHtml, setLatestResultHtml] = useState<string | null>(null);
  const [latestResultSlidev, setLatestResultSlidev] =
    useState<SlidevDeckResponse | null>(null);
  const [previewSlideIndex, setPreviewSlideIndex] = useState(0);
  const [isPreviewHovered, setIsPreviewHovered] = useState(false);
  const [resultPreviewCount, setResultPreviewCount] =
    useState(MOBILE_PREVIEW_COUNT);
  const [draftPreviewCount, setDraftPreviewCount] =
    useState(MOBILE_PREVIEW_COUNT);
  const [isResultDialogOpen, setIsResultDialogOpen] = useState(false);
  const [isDraftDialogOpen, setIsDraftDialogOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  const { status: settingsStatus, message: settingsMessage } = useSettingsStatus();

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      setLoading(true);
      try {
        const workspace = await getCurrentWorkspace();
        setWorkspaceId(workspace.id);

        const [sessionItems, sourceItems] = await Promise.all([
          listSessions({ limit: 100, offset: 0 }),
          listWorkspaceSources({ limit: 500, offset: 0 }),
        ]);
        if (cancelled) return;

        setSessions(sessionItems);
        setWorkspaceSourceCount(sourceItems.length);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    run().catch((err) => {
      console.error("home bootstrap failed", err);
      if (!cancelled) setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [setWorkspaceId]);

  const resultSessions = useMemo(
    () => sessions.filter((item) => item.has_presentation),
    [sessions]
  );
  const draftSessions = useMemo(
    () => sessions.filter((item) => !item.has_presentation),
    [sessions]
  );

  useEffect(() => {
    const computePreviewCount = () => {
      if (typeof window === "undefined") return;

      if (window.innerWidth < DESKTOP_BREAKPOINT) {
        setResultPreviewCount(MOBILE_PREVIEW_COUNT);
        setDraftPreviewCount(MOBILE_PREVIEW_COUNT);
        return;
      }

      const listAreaEl = listAreaRef.current;
      const resultSectionEl = resultSectionRef.current;
      const draftSectionEl = draftSectionRef.current;
      const resultHeaderEl = resultSectionHeaderRef.current;
      const draftHeaderEl = draftSectionHeaderRef.current;
      const probeEl = itemProbeRef.current;
      if (
        !listAreaEl ||
        !resultSectionEl ||
        !draftSectionEl ||
        !resultHeaderEl ||
        !draftHeaderEl ||
        !probeEl
      ) {
        setResultPreviewCount(MOBILE_PREVIEW_COUNT);
        setDraftPreviewCount(MOBILE_PREVIEW_COUNT);
        return;
      }

      const listAreaHeight = listAreaEl.clientHeight;
      const resultSectionStyles = window.getComputedStyle(resultSectionEl);
      const draftSectionStyles = window.getComputedStyle(draftSectionEl);
      const listAreaStyles = window.getComputedStyle(listAreaEl);
      const listAreaGap = Number.parseFloat(listAreaStyles.rowGap || "0");
      const resultSectionPadding =
        Number.parseFloat(resultSectionStyles.paddingTop || "0") +
        Number.parseFloat(resultSectionStyles.paddingBottom || "0");
      const draftSectionPadding =
        Number.parseFloat(draftSectionStyles.paddingTop || "0") +
        Number.parseFloat(draftSectionStyles.paddingBottom || "0");
      const resultHeaderHeight = resultHeaderEl.offsetHeight;
      const draftHeaderHeight = draftHeaderEl.offsetHeight;
      const rowHeight = probeEl.offsetHeight || 62;

      const rowsAvailableHeight = Math.max(
        0,
        listAreaHeight -
          listAreaGap -
          resultSectionPadding -
          draftSectionPadding -
          resultHeaderHeight -
          draftHeaderHeight
      );
      const fitRows = Math.floor(
        (rowsAvailableHeight + PREVIEW_ITEM_GAP_PX) /
          (rowHeight + PREVIEW_ITEM_GAP_PX)
      );

      const hasResult = resultSessions.length > 0;
      const hasDraft = draftSessions.length > 0;
      const minRows = hasResult && hasDraft ? 2 : hasResult || hasDraft ? 1 : 0;
      const maxRows =
        Math.min(resultSessions.length, MAX_PREVIEW_COUNT) +
        Math.min(draftSessions.length, MAX_PREVIEW_COUNT);
      const totalRows = clamp(fitRows || minRows, minRows, Math.max(minRows, maxRows));

      const { resultCount, draftCount } = distributePreviewRows({
        totalRows,
        resultTotal: resultSessions.length,
        draftTotal: draftSessions.length,
      });

      setResultPreviewCount((current) =>
        current === resultCount ? current : resultCount
      );
      setDraftPreviewCount((current) =>
        current === draftCount ? current : draftCount
      );
    };

    const rafId = window.requestAnimationFrame(computePreviewCount);
    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(computePreviewCount)
        : null;

    if (observer) {
      if (leftCardRef.current) observer.observe(leftCardRef.current);
      if (fixedAreaRef.current) observer.observe(fixedAreaRef.current);
      if (listAreaRef.current) observer.observe(listAreaRef.current);
      if (resultSectionRef.current) observer.observe(resultSectionRef.current);
      if (draftSectionRef.current) observer.observe(draftSectionRef.current);
      if (resultSectionHeaderRef.current) observer.observe(resultSectionHeaderRef.current);
      if (draftSectionHeaderRef.current) observer.observe(draftSectionHeaderRef.current);
      if (itemProbeRef.current) observer.observe(itemProbeRef.current);
    }

    window.addEventListener("resize", computePreviewCount);
    return () => {
      window.cancelAnimationFrame(rafId);
      observer?.disconnect();
      window.removeEventListener("resize", computePreviewCount);
    };
  }, [loading, settingsStatus, settingsMessage, resultSessions.length, draftSessions.length]);

  const resultPreviewSessions = useMemo(
    () => resultSessions.slice(0, resultPreviewCount),
    [resultPreviewCount, resultSessions]
  );
  const draftPreviewSessions = useMemo(
    () => draftSessions.slice(0, draftPreviewCount),
    [draftPreviewCount, draftSessions]
  );

  const resultSectionGrow = resultSessions.length
    ? Math.max(MIN_PREVIEW_COUNT, resultPreviewCount)
    : MIN_PREVIEW_COUNT;
  const draftSectionGrow = draftSessions.length
    ? Math.max(MIN_PREVIEW_COUNT, draftPreviewCount)
    : MIN_PREVIEW_COUNT;

  const latestResultSession = resultSessions[0] ?? null;
  const hasResultSessions = resultSessions.length > 0;

  useEffect(() => {
    let cancelled = false;

    if (!latestResultSession) {
      setLatestResultPresentation(null);
      setLatestResultOutputMode("structured");
      setLatestResultHtml(null);
      setLatestResultSlidev(null);
      setPreviewSlideIndex(0);
      setIsPreviewHovered(false);
      return () => {
        cancelled = true;
      };
    }

    setLatestResultPresentation(null);
    setLatestResultOutputMode("structured");
    setLatestResultHtml(null);
    setLatestResultSlidev(null);
    setPreviewSlideIndex(0);
    setIsPreviewHovered(false);

    const run = async () => {
      const latest = await getLatestSessionPresentation(latestResultSession.id);
      const outputMode = latest?.output_mode ?? "structured";
      const [html, slidev] = await Promise.all([
        outputMode === "html"
          ? getLatestSessionPresentationHtml(latestResultSession.id)
          : null,
        outputMode === "slidev"
          ? getLatestSessionPresentationSlidev(latestResultSession.id)
          : null,
      ]);
      if (cancelled) return;
      setLatestResultPresentation(latest?.presentation ?? null);
      setLatestResultOutputMode(outputMode);
      setLatestResultHtml(html);
      setLatestResultSlidev(slidev);
      setPreviewSlideIndex(0);
      setIsPreviewHovered(false);
    };

    run().catch((err) => {
      console.warn("load latest presentation preview failed", err);
    });

    return () => {
      cancelled = true;
    };
  }, [latestResultSession]);

  const handleNewPpt = async () => {
    const created = await createSession("未命名会话");
    setCurrentSessionId(created.id);
    router.push(`/create?session=${encodeURIComponent(created.id)}`);
  };

  const handleOpenSession = (
    session: SessionSummary,
    options?: { slide?: number }
  ) => {
    setCurrentSessionId(session.id);
    if (session.has_presentation) {
      if (options?.slide) {
        router.push(getSessionEditorPath(session.id, { slide: options.slide }));
        return;
      }
      router.push(getSessionEditorPath(session.id));
      return;
    }
    router.push(`/create?session=${encodeURIComponent(session.id)}`);
  };

  const refreshSessionList = useCallback(async () => {
    const items = await listSessions({ limit: 100, offset: 0 });
    setSessions(items);
  }, []);

  const handleCreateSessionFromDialog = useCallback(async () => {
    const created = await createSession("未命名会话");
    setCurrentSessionId(created.id);
    router.push(`/create?session=${encodeURIComponent(created.id)}`);
  }, [router, setCurrentSessionId]);

  const handleRenameSession = useCallback(
    async (id: string, newTitle: string) => {
      await updateSession(id, { title: newTitle });
      await refreshSessionList();
    },
    [refreshSessionList]
  );

  const handleDeleteSession = useCallback(
    async (id: string) => {
      await removeSession(id);
      await refreshSessionList();
    },
    [refreshSessionList]
  );

  const handleTogglePinSession = useCallback(
    async (id: string, isPinned: boolean) => {
      await updateSession(id, { is_pinned: isPinned });
      await refreshSessionList();
    },
    [refreshSessionList]
  );

  const handleBatchDeleteSessions = useCallback(
    async (ids: string[]) => {
      await Promise.all(ids.map((id) => removeSession(id)));
      await refreshSessionList();
    },
    [refreshSessionList]
  );

  const handlePrimaryAction = () => {
    if (latestResultSession) {
      handleOpenSession(latestResultSession);
      return;
    }
    void handleNewPpt();
  };

  const getResultTitle = (session: SessionSummary) => session.title || "未命名会话";

  const getResultMeta = (session: SessionSummary) =>
    `更新时间：${formatUpdatedAt(session.updated_at)}`;

  const getDraftTitle = (session: SessionSummary) => session.title || "未命名会话";

  const getDraftMeta = (session: SessionSummary) =>
    `更新时间：${formatUpdatedAt(session.updated_at)}`;

  return (
    <div className="zy-bg-home min-h-screen xl:h-screen xl:overflow-hidden">
      <main className="relative mx-auto h-full w-full max-w-none px-4 py-8 md:px-6 xl:px-6 xl:py-5">
        <div className="pointer-events-none absolute -top-16 right-8 h-52 w-52 rounded-full bg-[rgba(var(--zy-brand-blue),0.18)] blur-3xl" />
        <div className="pointer-events-none absolute top-24 -left-14 h-40 w-40 rounded-full bg-[rgba(var(--zy-brand-red),0.16)] blur-3xl" />

        <section className="grid h-full gap-6 animate-in fade-in slide-in-from-bottom-2 duration-200 xl:grid-cols-[minmax(320px,0.92fr)_minmax(0,1.38fr)] xl:items-stretch">
          <article
            ref={leftCardRef}
            className="relative flex h-full min-w-0 flex-col overflow-hidden rounded-3xl border border-white/60 bg-card/80 p-6 shadow-[0_20px_60px_-40px_rgba(15,23,42,0.5)] backdrop-blur-xl xl:p-7"
          >
            <div ref={fixedAreaRef} className="shrink-0">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-600">欢迎回来</p>
                  <h1 className="mt-1 text-3xl font-semibold tracking-tight text-slate-900">
                    知演 ZhiYan
                  </h1>
                  <p className="mt-2 text-sm text-slate-600">
                    知识变演示，更懂演示的 AI PPT 智能体
                  </p>
                </div>
                <UserMenu compact />
              </div>

              {settingsStatus === "unconfigured" && settingsMessage ? (
                <p className="mt-3 text-xs text-amber-700">{settingsMessage}</p>
              ) : null}

              <div className="mt-5 grid gap-2 sm:grid-cols-3">
                <button
                  onClick={handlePrimaryAction}
                  className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white transition-all duration-200 hover:-translate-y-0.5 hover:bg-slate-800 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/70"
                >
                  {hasResultSessions ? (
                    <ArrowRight className="h-4 w-4" />
                  ) : (
                    <Sparkles className="h-4 w-4" />
                  )}
                  {hasResultSessions ? "继续最近成果" : "开始新建演示稿"}
                </button>
                <button
                  onClick={() => {
                    void handleNewPpt();
                  }}
                  className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white/70 px-4 text-sm font-medium text-slate-700 transition-all duration-200 hover:-translate-y-0.5 hover:bg-white hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
                >
                  <FilePlus2 className="h-4 w-4" />
                  新建演示稿
                </button>
                <button
                  onClick={() => router.push("/assets")}
                  className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white/70 px-4 text-sm font-medium text-slate-700 transition-all duration-200 hover:-translate-y-0.5 hover:bg-white hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
                >
                  <Library className="h-4 w-4" />
                  素材库管理
                </button>
              </div>

              <div className="mt-5 grid grid-cols-3 gap-2">
                <article className="flex items-center justify-between rounded-xl border border-white/80 bg-white/75 px-3 py-2.5">
                  <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                    <Presentation className="h-4 w-4 text-rose-600" />
                    已生成文稿
                  </div>
                  <p className="text-xl font-semibold text-slate-900">
                    {resultSessions.length}
                  </p>
                </article>
                <article className="flex items-center justify-between rounded-xl border border-white/80 bg-white/75 px-3 py-2.5">
                  <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                    <FolderOpenDot className="h-4 w-4 text-blue-700" />
                    待完善草稿
                  </div>
                  <p className="text-xl font-semibold text-slate-900">
                    {draftSessions.length}
                  </p>
                </article>
                <article className="flex items-center justify-between rounded-xl border border-white/80 bg-white/75 px-3 py-2.5">
                  <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                    <Library className="h-4 w-4 text-amber-600" />
                    素材库条目
                  </div>
                  <p className="text-xl font-semibold text-slate-900">
                    {workspaceSourceCount}
                  </p>
                </article>
              </div>
            </div>

            <div ref={listAreaRef} className="mt-4 flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
              <section
                ref={resultSectionRef}
                style={{ flexGrow: resultSectionGrow }}
                className="flex min-h-0 basis-0 flex-col rounded-2xl border border-white/80 bg-white/75 p-3"
              >
                <div
                  ref={resultSectionHeaderRef}
                  className="mb-2 flex items-center justify-between"
                >
                  <h2 className="text-sm font-semibold text-slate-800">最近生成文稿</h2>
                  <button
                    onClick={() => setIsResultDialogOpen(true)}
                    className="text-xs text-slate-500 transition-colors hover:text-slate-900"
                  >
                    查看全部
                  </button>
                </div>

                {loading ? (
                  <p className="py-3 text-sm text-slate-500">加载中...</p>
                ) : resultPreviewSessions.length === 0 ? (
                  <p className="py-3 text-sm text-slate-500">还没有已生成文稿</p>
                ) : (
                  <div className="min-h-0 flex-1 space-y-1.5 overflow-hidden">
                    {resultPreviewSessions.map((session) => (
                      <button
                        key={session.id}
                        onClick={() => handleOpenSession(session)}
                        className="flex w-full items-center justify-between rounded-lg border border-slate-200 bg-white/80 px-3 py-2.5 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-slate-300 hover:bg-white hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-slate-900">
                            {getResultTitle(session)}
                          </p>
                          <p className="truncate text-xs text-slate-500">
                            更新时间：{formatUpdatedAt(session.updated_at)}
                          </p>
                        </div>
                        <ArrowRight className="h-4 w-4 shrink-0 text-slate-400" />
                      </button>
                    ))}
                  </div>
                )}
              </section>

              <section
                ref={draftSectionRef}
                style={{ flexGrow: draftSectionGrow }}
                className="flex min-h-0 basis-0 flex-col rounded-2xl border border-white/80 bg-white/75 p-3"
              >
                <div
                  ref={draftSectionHeaderRef}
                  className="mb-2 flex items-center justify-between"
                >
                  <h2 className="text-sm font-semibold text-slate-800">继续中的草稿</h2>
                  <button
                    onClick={() => setIsDraftDialogOpen(true)}
                    className="text-xs text-slate-500 transition-colors hover:text-slate-900"
                  >
                    去工作台
                  </button>
                </div>

                {loading ? (
                  <p className="py-3 text-sm text-slate-500">加载中...</p>
                ) : draftPreviewSessions.length === 0 ? (
                  <p className="py-3 text-sm text-slate-500">暂无草稿会话</p>
                ) : (
                  <div className="min-h-0 flex-1 space-y-1.5 overflow-hidden">
                    {draftPreviewSessions.map((session) => (
                      <button
                        key={session.id}
                        onClick={() => handleOpenSession(session)}
                        className="flex w-full items-center justify-between rounded-lg border border-slate-200 bg-white/80 px-3 py-2.5 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-slate-300 hover:bg-white hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-slate-900">
                            {getDraftTitle(session)}
                          </p>
                          <p className="truncate text-xs text-slate-500">
                            更新时间：{formatUpdatedAt(session.updated_at)}
                          </p>
                        </div>
                        <ArrowRight className="h-4 w-4 shrink-0 text-slate-400" />
                      </button>
                    ))}
                  </div>
                )}
              </section>
            </div>

            <div className="pointer-events-none absolute left-0 top-0 -z-10 w-full opacity-0">
              <div
                ref={itemProbeRef}
                className="rounded-lg border border-slate-200 bg-white/80 px-3 py-2.5"
              >
                <p className="text-sm font-semibold leading-5">示例标题</p>
                <p className="mt-0.5 text-xs leading-4">更新时间：00/00 00:00</p>
              </div>
            </div>
          </article>

          <aside className="flex h-full min-h-[460px] min-w-0 flex-col rounded-3xl border border-[rgba(var(--zy-brand-blue),0.12)] bg-[linear-gradient(135deg,rgba(255,255,255,0.92),rgba(var(--zy-brand-red),0.045),rgba(var(--zy-brand-blue),0.10))] p-5 shadow-[0_20px_45px_-35px_rgba(0,75,132,0.35)] xl:min-h-0">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-700">
              <FileText className="h-4 w-4 text-blue-700" />
              最近成果预览
            </div>
            {loading ? (
              <p className="py-7 text-sm text-slate-500">加载最近成果...</p>
            ) : latestResultSession ? (
              <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
                <p className="truncate text-base font-semibold text-slate-900">
                  {latestResultSession.title || "未命名会话"}
                </p>
                <p className="text-xs leading-5 text-slate-600">
                  更新时间：{formatUpdatedAt(latestResultSession.updated_at)}
                </p>
                {latestResultOutputMode === "slidev" ? (
                  <div className="min-h-0 flex-1">
                    {latestResultSlidev?.build_url ? (
                      <button
                        type="button"
                        onClick={() =>
                          handleOpenSession(latestResultSession, { slide: previewSlideIndex + 1 })
                        }
                        className="group relative block w-full overflow-hidden rounded-xl border border-blue-100/80 bg-white/75 text-left transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/70"
                        aria-label="打开 Slidev 编辑器"
                      >
                        <div className="aspect-video w-full overflow-hidden">
                          <SlidevPreview
                            src={latestResultSlidev.build_url}
                            startSlide={previewSlideIndex}
                            onSlideChange={setPreviewSlideIndex}
                            className="w-full rounded-none"
                          />
                        </div>
                        <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-slate-900/55 via-slate-900/10 to-transparent px-3 py-2">
                          <p className="text-xs font-medium text-white/90">
                            共{" "}
                            {Array.isArray(latestResultSlidev.meta?.slides)
                              ? (latestResultSlidev.meta.slides as unknown[]).length
                              : "?"}{" "}
                            页 · 点击进入编辑器
                          </p>
                        </div>
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleOpenSession(latestResultSession)}
                        className="flex w-full flex-1 flex-col gap-2 rounded-xl border border-blue-100/80 bg-white/75 p-4 text-left transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/70"
                        aria-label="打开 Slidev 编辑器"
                      >
                        <p className="text-xs font-medium text-slate-500">
                          Slidev 演示稿 ·{" "}
                          {Array.isArray(latestResultSlidev?.meta?.slides)
                            ? `${(latestResultSlidev.meta.slides as unknown[]).length} 页`
                            : "预览尚未就绪"}
                        </p>
                        {Array.isArray(latestResultSlidev?.meta?.slides) && (
                          <ul className="space-y-1 text-sm text-slate-700">
                            {(
                              latestResultSlidev.meta.slides as Array<Record<string, unknown>>
                            ).map((s, i) => (
                              <li key={String(s.slide_id ?? i)} className="truncate">
                                <span className="mr-2 text-xs text-slate-400">{i + 1}.</span>
                                {String(s.title ?? `第 ${i + 1} 页`)}
                              </li>
                            ))}
                          </ul>
                        )}
                        <p className="mt-1 text-xs text-blue-600">点击进入编辑器 →</p>
                      </button>
                    )}
                  </div>
                ) : latestResultPresentation?.slides?.length ? (
                  <div className="min-h-0 flex-1">
                    <RecentResultCarousel
                      presentation={latestResultPresentation}
                      outputMode={latestResultOutputMode}
                      htmlContent={latestResultHtml}
                      previewSlideIndex={previewSlideIndex}
                      setPreviewSlideIndex={setPreviewSlideIndex}
                      isPreviewHovered={isPreviewHovered}
                      setIsPreviewHovered={setIsPreviewHovered}
                      onOpenCurrentSlide={() =>
                        handleOpenSession(latestResultSession, {
                          slide: previewSlideIndex + 1,
                        })
                      }
                    />
                  </div>
                ) : (
                  <div className="flex flex-1 items-center rounded-xl border border-rose-100/80 bg-white/75 px-4 text-sm leading-6 text-slate-600">
                    暂时无法加载该成果的页面预览，你仍可直接进入编辑器继续修改。
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm leading-6 text-slate-600">
                  暂无已生成文稿。你可以先新建演示稿，或进入工作台继续整理素材后生成。
                </p>
                <button
                  onClick={() => router.push("/create")}
                  className="inline-flex h-11 items-center gap-2 rounded-lg border border-blue-200 bg-white/85 px-3 text-sm font-medium text-blue-700 transition-all duration-200 hover:-translate-y-0.5 hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
                >
                  去创建工作台
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            )}
          </aside>
        </section>
      </main>

      <SessionListDialog
        open={isResultDialogOpen}
        onOpenChange={setIsResultDialogOpen}
        title="全部文稿"
        description="浏览当前 workspace 中可直接进入编辑器的文稿会话"
        emptyText="暂无可查看的已生成文稿"
        sessions={resultSessions}
        getSessionTitle={getResultTitle}
        getSessionMeta={getResultMeta}
        onOpenSession={handleOpenSession}
        onCreateSession={handleCreateSessionFromDialog}
        onRenameSession={handleRenameSession}
        onDeleteSession={handleDeleteSession}
        onTogglePinSession={handleTogglePinSession}
        onBatchDeleteSessions={handleBatchDeleteSessions}
      />

      <SessionListDialog
        open={isDraftDialogOpen}
        onOpenChange={setIsDraftDialogOpen}
        title="全部草稿会话"
        description="浏览仍在补充素材或继续完善中的会话"
        emptyText="暂无可查看的草稿会话"
        sessions={draftSessions}
        getSessionTitle={getDraftTitle}
        getSessionMeta={getDraftMeta}
        onOpenSession={handleOpenSession}
        onCreateSession={handleCreateSessionFromDialog}
        onRenameSession={handleRenameSession}
        onDeleteSession={handleDeleteSession}
        onTogglePinSession={handleTogglePinSession}
        onBatchDeleteSessions={handleBatchDeleteSessions}
      />
    </div>
  );
}

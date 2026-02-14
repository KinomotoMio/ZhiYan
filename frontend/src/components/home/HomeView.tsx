"use client";

import { useEffect, useMemo, useState } from "react";
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
  listSessions,
  listWorkspaceSources,
  type SessionSummary,
} from "@/lib/api";
import RecentResultCarousel from "@/components/home/RecentResultCarousel";
import UserMenu from "@/components/settings/UserMenu";
import { useSettingsStatus } from "@/hooks/useSettingsStatus";
import { useAppStore } from "@/lib/store";
import { getSessionEditorPath } from "@/lib/routes";
import type { Presentation as PresentationModel } from "@/types/slide";

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

function toPptFileDisplayName(
  presentationTitle?: string | null,
  sessionTitle?: string
): string {
  const title = presentationTitle?.trim();
  const fallback = sessionTitle?.trim() || "未命名演示稿";
  const baseName = title && title.length > 0 ? title : fallback;
  return /\.pptx$/i.test(baseName) ? baseName : `${baseName}.pptx`;
}

export default function HomeView() {
  const router = useRouter();
  const setCurrentSessionId = useAppStore((store) => store.setCurrentSessionId);
  const setWorkspaceId = useAppStore((store) => store.setWorkspaceId);

  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [workspaceSourceCount, setWorkspaceSourceCount] = useState(0);
  const [resultFileNames, setResultFileNames] = useState<Record<string, string>>({});
  const [latestResultPresentation, setLatestResultPresentation] =
    useState<PresentationModel | null>(null);
  const [previewSlideIndex, setPreviewSlideIndex] = useState(0);
  const [isPreviewHovered, setIsPreviewHovered] = useState(false);
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

  const resultListSessions = useMemo(() => resultSessions.slice(0, 4), [resultSessions]);
  const draftListSessions = useMemo(() => draftSessions.slice(0, 4), [draftSessions]);

  const latestResultSession = resultSessions[0] ?? null;
  const hasResultSessions = resultSessions.length > 0;

  useEffect(() => {
    let cancelled = false;
    const targets = resultSessions.slice(0, 6);

    if (targets.length === 0) {
      setResultFileNames({});
      setLatestResultPresentation(null);
      setPreviewSlideIndex(0);
      setIsPreviewHovered(false);
      return () => {
        cancelled = true;
      };
    }

    const fallbackMap = Object.fromEntries(
      targets.map((item) => [item.id, toPptFileDisplayName(undefined, item.title)])
    );
    setResultFileNames(fallbackMap);
    setLatestResultPresentation(null);
    setPreviewSlideIndex(0);
    setIsPreviewHovered(false);

    const run = async () => {
      const settled = await Promise.allSettled(
        targets.map(async (session) => {
          const latest = await getLatestSessionPresentation(session.id);
          return {
            sessionId: session.id,
            fileName: toPptFileDisplayName(latest?.presentation?.title, session.title),
            presentation: latest?.presentation ?? null,
          };
        })
      );
      if (cancelled) return;

      const nextMap = { ...fallbackMap };
      let latestPresentation: PresentationModel | null = null;

      for (const item of settled) {
        if (item.status !== "fulfilled") continue;
        nextMap[item.value.sessionId] = item.value.fileName;
        if (item.value.sessionId === targets[0]?.id) {
          latestPresentation = item.value.presentation;
        }
      }

      setResultFileNames(nextMap);
      setLatestResultPresentation(latestPresentation);
      setPreviewSlideIndex(0);
      setIsPreviewHovered(false);
    };

    run().catch((err) => {
      console.warn("load latest presentation titles failed", err);
    });

    return () => {
      cancelled = true;
    };
  }, [resultSessions]);

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

  const handlePrimaryAction = () => {
    if (latestResultSession) {
      handleOpenSession(latestResultSession);
      return;
    }
    void handleNewPpt();
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_12%_10%,rgba(56,189,248,0.26),transparent_46%),radial-gradient(circle_at_86%_8%,rgba(20,184,166,0.2),transparent_36%),radial-gradient(circle_at_58%_86%,rgba(251,191,36,0.16),transparent_42%),linear-gradient(165deg,rgba(248,250,252,0.95)_10%,rgba(239,246,255,0.94)_48%,rgba(236,253,245,0.9)_100%)]">
      <main className="relative mx-auto w-full max-w-[1480px] px-4 py-10 md:px-6 lg:px-8">
        <div className="pointer-events-none absolute -top-16 right-8 h-52 w-52 rounded-full bg-cyan-200/40 blur-3xl" />
        <div className="pointer-events-none absolute top-24 -left-14 h-40 w-40 rounded-full bg-teal-200/40 blur-3xl" />

        <section className="grid gap-6 animate-in fade-in slide-in-from-bottom-2 duration-200 lg:grid-cols-[minmax(320px,0.92fr)_minmax(0,1.38fr)] lg:items-start">
          <article className="min-w-0 rounded-3xl border border-white/60 bg-card/80 p-6 shadow-[0_20px_60px_-40px_rgba(15,23,42,0.5)] backdrop-blur-xl lg:p-7">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-600">欢迎回来</p>
                <h1 className="mt-1 text-3xl font-semibold tracking-tight text-slate-900">知演 ZhiYan</h1>
                <p className="mt-2 text-sm text-slate-600">知识变演示，更懂演示的 AI PPT 智能体</p>
              </div>
              <UserMenu compact />
            </div>

            {settingsStatus === "unconfigured" && settingsMessage ? (
              <p className="mt-3 text-xs text-amber-700">{settingsMessage}</p>
            ) : null}

            <div className="mt-5 grid gap-2 sm:grid-cols-3">
              <button
                onClick={handlePrimaryAction}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white transition-all duration-200 hover:-translate-y-0.5 hover:bg-slate-800 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/70"
              >
                {hasResultSessions ? <ArrowRight className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
                {hasResultSessions ? "继续最近成果" : "开始新建演示稿"}
              </button>
              <button
                onClick={() => {
                  void handleNewPpt();
                }}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white/70 px-4 text-sm font-medium text-slate-700 transition-all duration-200 hover:-translate-y-0.5 hover:bg-white hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60"
              >
                <FilePlus2 className="h-4 w-4" />
                新建演示稿
              </button>
              <button
                onClick={() => router.push("/assets")}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white/70 px-4 text-sm font-medium text-slate-700 transition-all duration-200 hover:-translate-y-0.5 hover:bg-white hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60"
              >
                <Library className="h-4 w-4" />
                素材库管理
              </button>
            </div>

            <div className="mt-5 grid gap-2">
              <article className="flex items-center justify-between rounded-xl border border-white/80 bg-white/75 px-3 py-2.5">
                <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                  <Presentation className="h-4 w-4 text-emerald-600" />
                  已生成文稿
                </div>
                <p className="text-xl font-semibold text-slate-900">{resultSessions.length}</p>
              </article>
              <article className="flex items-center justify-between rounded-xl border border-white/80 bg-white/75 px-3 py-2.5">
                <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                  <FolderOpenDot className="h-4 w-4 text-sky-600" />
                  待完善草稿
                </div>
                <p className="text-xl font-semibold text-slate-900">{draftSessions.length}</p>
              </article>
              <article className="flex items-center justify-between rounded-xl border border-white/80 bg-white/75 px-3 py-2.5">
                <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                  <Library className="h-4 w-4 text-amber-600" />
                  素材库条目
                </div>
                <p className="text-xl font-semibold text-slate-900">{workspaceSourceCount}</p>
              </article>
            </div>

            <section className="mt-5 rounded-2xl border border-white/80 bg-white/75 p-3">
              <div className="mb-2 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-800">最近生成文稿</h2>
                <button
                  onClick={() => router.push("/create")}
                  className="text-xs text-slate-500 transition-colors hover:text-slate-900"
                >
                  查看全部
                </button>
              </div>
              {loading ? (
                <p className="py-4 text-sm text-slate-500">加载中...</p>
              ) : resultListSessions.length === 0 ? (
                <p className="py-4 text-sm text-slate-500">还没有已生成文稿</p>
              ) : (
                <div className="space-y-1.5">
                  {resultListSessions.map((session) => (
                    <button
                      key={session.id}
                      onClick={() => handleOpenSession(session)}
                      className="flex w-full items-center justify-between rounded-lg border border-slate-200 bg-white/80 px-3 py-2.5 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-slate-300 hover:bg-white hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-slate-900">
                          {resultFileNames[session.id] ||
                            toPptFileDisplayName(undefined, session.title)}
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

            <section className="mt-3 rounded-2xl border border-white/80 bg-white/75 p-3">
              <div className="mb-2 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-800">继续中的草稿</h2>
                <button
                  onClick={() => router.push("/create")}
                  className="text-xs text-slate-500 transition-colors hover:text-slate-900"
                >
                  去工作台
                </button>
              </div>
              {loading ? (
                <p className="py-4 text-sm text-slate-500">加载中...</p>
              ) : draftListSessions.length === 0 ? (
                <p className="py-4 text-sm text-slate-500">暂无草稿会话</p>
              ) : (
                <div className="space-y-1.5">
                  {draftListSessions.map((session) => (
                    <button
                      key={session.id}
                      onClick={() => handleOpenSession(session)}
                      className="flex w-full items-center justify-between rounded-lg border border-slate-200 bg-white/80 px-3 py-2.5 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-slate-300 hover:bg-white hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-slate-900">
                          {session.title || "未命名会话"}
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
          </article>

          <aside className="flex min-h-[460px] min-w-0 flex-col rounded-3xl border border-cyan-100/80 bg-gradient-to-br from-white/90 via-white/80 to-emerald-50/70 p-5 shadow-[0_20px_45px_-35px_rgba(2,132,199,0.55)]">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-700">
              <FileText className="h-4 w-4 text-cyan-600" />
              最近成果预览
            </div>
            {loading ? (
              <p className="py-7 text-sm text-slate-500">加载最近成果...</p>
            ) : latestResultSession ? (
              <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
                <p className="truncate text-base font-semibold text-slate-900">
                  {resultFileNames[latestResultSession.id] ||
                    toPptFileDisplayName(undefined, latestResultSession.title)}
                </p>
                <p className="text-xs leading-5 text-slate-600">
                  会话：{latestResultSession.title || "未命名会话"}
                  <br />
                  更新时间：{formatUpdatedAt(latestResultSession.updated_at)}
                </p>
                {latestResultPresentation?.slides?.length ? (
                  <div className="min-h-0 flex-1">
                    <RecentResultCarousel
                      presentation={latestResultPresentation}
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
                  <div className="flex flex-1 items-center rounded-xl border border-cyan-100/80 bg-white/70 px-4 text-sm leading-6 text-slate-600">
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
                  className="inline-flex h-11 items-center gap-2 rounded-lg border border-cyan-200 bg-white/80 px-3 text-sm font-medium text-cyan-700 transition-all duration-200 hover:-translate-y-0.5 hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60"
                >
                  去创建工作台
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            )}
          </aside>
        </section>
      </main>
    </div>
  );
}

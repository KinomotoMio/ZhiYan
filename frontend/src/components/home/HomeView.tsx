"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, FilePlus2, FolderOpenDot, Library, Presentation } from "lucide-react";
import {
  createSession,
  getWorkspaceId,
  listSessions,
  listWorkspaceSources,
  type SessionSummary,
} from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { getSessionEditorPath } from "@/lib/routes";

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
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [workspaceSourceCount, setWorkspaceSourceCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      try {
        const ws = getWorkspaceId();
        setWorkspaceId(ws);
        const [sessionItems, sourceItems] = await Promise.all([
          listSessions({ limit: 100, offset: 0 }),
          listWorkspaceSources({ limit: 500, offset: 0 }),
        ]);
        if (cancelled) return;
        setSessions(sessionItems);
        setWorkspaceSourceCount(sourceItems.length > 0 ? sourceItems.length : 0);
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
    () => sessions.filter((item) => item.has_presentation).slice(0, 6),
    [sessions]
  );
  const draftSessions = useMemo(
    () => sessions.filter((item) => !item.has_presentation).slice(0, 6),
    [sessions]
  );

  const handleNewPpt = async () => {
    const created = await createSession("未命名会话");
    setCurrentSessionId(created.id);
    router.push(`/create?session=${encodeURIComponent(created.id)}`);
  };

  const handleOpenSession = (session: SessionSummary) => {
    setCurrentSessionId(session.id);
    if (session.has_presentation) {
      router.push(getSessionEditorPath(session.id));
      return;
    }
    router.push(`/create?session=${encodeURIComponent(session.id)}`);
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.08),_transparent_45%),radial-gradient(circle_at_85%_10%,_rgba(16,185,129,0.08),_transparent_35%)]">
      <main className="mx-auto w-full max-w-6xl px-6 py-10">
        <section className="rounded-2xl border border-border/70 bg-card/80 p-7 backdrop-blur">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            ZhiYan Workspace
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight">一会话一演示稿</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
            已有结果的会话直接进入编辑器。要开始一份新的 PPT，请先新建会话，再进入创建工作台。
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <button
              onClick={() => {
                void handleNewPpt();
              }}
              className="inline-flex h-11 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              <FilePlus2 className="h-4 w-4" />
              新建 PPT 会话
            </button>
            <button
              onClick={() => router.push("/create")}
              className="inline-flex h-11 items-center gap-2 rounded-lg border border-input px-4 text-sm font-medium hover:bg-accent"
            >
              <FolderOpenDot className="h-4 w-4" />
              进入创建工作台
            </button>
          </div>
        </section>

        <section className="mt-6 grid gap-4 md:grid-cols-3">
          <article className="rounded-xl border border-border/70 bg-card p-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Presentation className="h-4 w-4 text-emerald-500" />
              已生成会话
            </div>
            <p className="mt-2 text-2xl font-semibold">{resultSessions.length}</p>
            <p className="text-xs text-muted-foreground">可直接进入编辑器继续修改</p>
          </article>
          <article className="rounded-xl border border-border/70 bg-card p-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <FolderOpenDot className="h-4 w-4 text-sky-500" />
              草稿会话
            </div>
            <p className="mt-2 text-2xl font-semibold">{draftSessions.length}</p>
            <p className="text-xs text-muted-foreground">可继续补充素材并生成新稿</p>
          </article>
          <article className="rounded-xl border border-border/70 bg-card p-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Library className="h-4 w-4 text-violet-500" />
              素材库
            </div>
            <p className="mt-2 text-2xl font-semibold">{workspaceSourceCount}</p>
            <p className="text-xs text-muted-foreground">workspace 级可复用素材条目</p>
          </article>
        </section>

        <section className="mt-6 grid gap-4 lg:grid-cols-2">
          <article className="rounded-xl border border-border/70 bg-card p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold">最近结果会话</h2>
              <button
                onClick={() => router.push("/create")}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                查看全部
              </button>
            </div>
            {loading ? (
              <p className="py-6 text-sm text-muted-foreground">加载中...</p>
            ) : resultSessions.length === 0 ? (
              <p className="py-6 text-sm text-muted-foreground">还没有已生成会话</p>
            ) : (
              <div className="space-y-2">
                {resultSessions.map((session) => (
                  <button
                    key={session.id}
                    onClick={() => handleOpenSession(session)}
                    className="flex w-full items-center justify-between rounded-lg border border-border px-3 py-2 text-left hover:bg-accent"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{session.title || "未命名会话"}</p>
                      <p className="text-xs text-muted-foreground">
                        {session.source_count} 素材 · {session.chat_count} 对话 · {formatUpdatedAt(session.updated_at)}
                      </p>
                    </div>
                    <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                  </button>
                ))}
              </div>
            )}
          </article>

          <article className="rounded-xl border border-border/70 bg-card p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold">最近草稿会话</h2>
              <button
                onClick={() => router.push("/create")}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                去工作台
              </button>
            </div>
            {loading ? (
              <p className="py-6 text-sm text-muted-foreground">加载中...</p>
            ) : draftSessions.length === 0 ? (
              <p className="py-6 text-sm text-muted-foreground">暂无草稿会话</p>
            ) : (
              <div className="space-y-2">
                {draftSessions.map((session) => (
                  <button
                    key={session.id}
                    onClick={() => handleOpenSession(session)}
                    className="flex w-full items-center justify-between rounded-lg border border-border px-3 py-2 text-left hover:bg-accent"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{session.title || "未命名会话"}</p>
                      <p className="text-xs text-muted-foreground">
                        {session.source_count} 素材 · {session.chat_count} 对话 · {formatUpdatedAt(session.updated_at)}
                      </p>
                    </div>
                    <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                  </button>
                ))}
              </div>
            )}
          </article>
        </section>
      </main>
    </div>
  );
}

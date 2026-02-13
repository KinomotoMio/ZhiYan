"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { MessageSquare, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useAppStore, type ChatMessage } from "@/lib/store";
import {
  appendSessionChat,
  createSession,
  createSessionSnapshot,
  deleteSessionSource,
  fetchSessionUrlSource,
  getSessionDetail,
  getWorkspaceId,
  listSessions,
  removeSession,
  updateSession,
  uploadSessionSource,
} from "@/lib/api";
import SourceItem from "./SourceItem";
import SourcePreviewModal from "./SourcePreviewModal";
import AddSourceArea from "./AddSourceArea";
import UserMenu from "@/components/settings/UserMenu";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import type { SourceMeta } from "@/types/source";
import type { Presentation } from "@/types/slide";

const MIGRATION_FLAG_KEY = "zhiyan-session-migrated-v1";

function isUrl(text: string): boolean {
  try {
    const url = new URL(text);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
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

function readLegacyStore() {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem("zhiyan-store");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { state?: Record<string, unknown> };
    return parsed.state || null;
  } catch {
    return null;
  }
}

function toStoreChatMessages(records: Array<Record<string, unknown>>): ChatMessage[] {
  return records
    .map((item) => {
      const role = item.role === "assistant" ? "assistant" : "user";
      const content = typeof item.content === "string" ? item.content : "";
      const createdAt = typeof item.created_at === "string" ? item.created_at : "";
      return {
        id: typeof item.id === "string" ? item.id : `msg-${Math.random().toString(36).slice(2)}`,
        role,
        content,
        timestamp: Date.parse(createdAt) || Date.now(),
      } as ChatMessage;
    })
    .filter((item) => item.content.trim().length > 0);
}

export default function SourcePanel() {
  const {
    workspaceId,
    setWorkspaceId,
    sessions,
    setSessions,
    upsertSession,
    removeSessionEntry,
    currentSessionId,
    setCurrentSessionId,
    setSessionData,
    resetJobState,
    sources,
    selectedSourceIds,
    addSource,
    updateSource,
    removeSource,
    toggleSourceSelection,
    selectAllSources,
    deselectAllSources,
  } = useAppStore();

  const [activeTab, setActiveTab] = useState<"sources" | "sessions">("sources");
  const [sessionQuery, setSessionQuery] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);
  const [previewSource, setPreviewSource] = useState<SourceMeta | null>(null);
  const [loadingSession, setLoadingSession] = useState(false);
  const bootstrappedRef = useRef(false);

  const readySources = sources.filter((s) => s.status === "ready");
  const selectedCount = readySources.filter((s) =>
    selectedSourceIds.includes(s.id)
  ).length;
  const allSelected =
    readySources.length > 0 && selectedCount === readySources.length;

  const refreshSessions = useCallback(
    async (q = "") => {
      const result = await listSessions({ q, limit: 100, offset: 0 });
      setSessions(result);
      return result;
    },
    [setSessions]
  );

  const loadSession = useCallback(
    async (sessionId: string) => {
      setLoadingSession(true);
      try {
        const detail = await getSessionDetail(sessionId);
        const chatMessages = toStoreChatMessages(
          detail.chat_messages as unknown as Array<Record<string, unknown>>
        );
        setCurrentSessionId(sessionId);
        upsertSession(detail.session);
        setSessionData({
          sources: detail.sources,
          chatMessages,
          presentation: detail.latest_presentation?.presentation ?? null,
        });
        resetJobState();
      } finally {
        setLoadingSession(false);
      }
    },
    [resetJobState, setCurrentSessionId, setSessionData, upsertSession]
  );

  const createAndOpenSession = useCallback(
    async (title: string) => {
      const created = await createSession(title);
      upsertSession(created);
      await loadSession(created.id);
      return created.id;
    },
    [loadSession, upsertSession]
  );

  useEffect(() => {
    if (bootstrappedRef.current) return;
    bootstrappedRef.current = true;

    let cancelled = false;
    const run = async () => {
      const wsId = getWorkspaceId();
      setWorkspaceId(wsId);

      let items = await refreshSessions();
      if (cancelled) return;

      if (items.length === 0) {
        const legacy = readLegacyStore();
        const migrated = typeof window !== "undefined" && window.localStorage.getItem(MIGRATION_FLAG_KEY) === "1";
        const legacyPresentation = legacy?.presentation as Record<string, unknown> | undefined;
        const legacyChats = Array.isArray(legacy?.chatMessages)
          ? (legacy?.chatMessages as Array<Record<string, unknown>>)
          : [];
        const legacyTopic = typeof legacy?.topic === "string" ? legacy.topic.trim() : "";
        const hasLegacyData =
          Boolean(legacyPresentation) || legacyChats.length > 0 || legacyTopic.length > 0;

        if (hasLegacyData && !migrated) {
          const migratedSessionId = await createAndOpenSession("本地迁移会话");
          if (legacyPresentation) {
            await createSessionSnapshot(
              migratedSessionId,
              "本地迁移快照",
              legacyPresentation as unknown as Presentation
            ).catch(() => {});
          }
          for (const msg of legacyChats) {
            const role = msg.role === "assistant" ? "assistant" : "user";
            const content = typeof msg.content === "string" ? msg.content : "";
            if (!content.trim()) continue;
            await appendSessionChat(migratedSessionId, { role, content }).catch(() => {});
          }
          if (typeof window !== "undefined") {
            window.localStorage.setItem(MIGRATION_FLAG_KEY, "1");
          }
          items = await refreshSessions();
          if (cancelled) return;
          await loadSession(migratedSessionId);
          return;
        }

        const sid = await createAndOpenSession("未命名会话");
        items = await refreshSessions();
        if (cancelled) return;
        await loadSession(sid);
        return;
      }

      const preferred =
        currentSessionId && items.some((item) => item.id === currentSessionId)
          ? currentSessionId
          : items[0]?.id;

      if (preferred) {
        await loadSession(preferred);
      }
    };

    run().catch((err) => {
      console.error("session bootstrap failed", err);
    });

    return () => {
      cancelled = true;
    };
  }, [createAndOpenSession, currentSessionId, loadSession, refreshSessions, setWorkspaceId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      refreshSessions(sessionQuery).catch((err) => {
        console.error("refresh sessions failed", err);
      });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [refreshSessions, sessionQuery]);

  const ensureSession = useCallback(async () => {
    if (currentSessionId) return currentSessionId;
    return createAndOpenSession("未命名会话");
  }, [createAndOpenSession, currentSessionId]);

  const handleUploadFiles = useCallback(
    async (files: File[]) => {
      const sessionId = await ensureSession();
      for (const file of files) {
        const tempId = `temp-${Date.now()}-${file.name}`;
        addSource({
          id: tempId,
          name: file.name,
          type: "file",
          size: file.size,
          status: "uploading",
        });

        try {
          const meta = await uploadSessionSource(sessionId, file, (pct) => {
            if (pct < 100) {
              updateSource(tempId, { status: "uploading" });
            }
          });
          removeSource(tempId);
          addSource(meta);
          refreshSessions(sessionQuery).catch(() => {});
        } catch {
          updateSource(tempId, {
            status: "error",
            error: "上传失败",
          });
        }
      }
    },
    [addSource, ensureSession, refreshSessions, removeSource, sessionQuery, updateSource]
  );

  const handleUrlSubmit = useCallback(
    async (url: string) => {
      const sessionId = await ensureSession();
      const tempId = `temp-url-${Date.now()}`;
      addSource({
        id: tempId,
        name: url,
        type: "url",
        status: "parsing",
      });

      try {
        const meta = await fetchSessionUrlSource(sessionId, url);
        removeSource(tempId);
        addSource(meta);
        refreshSessions(sessionQuery).catch(() => {});
      } catch {
        updateSource(tempId, { status: "error", error: "抓取失败" });
      }
    },
    [addSource, ensureSession, refreshSessions, removeSource, sessionQuery, updateSource]
  );

  const handleRemoveSource = useCallback(
    async (id: string) => {
      if (!currentSessionId) return;
      removeSource(id);
      deleteSessionSource(currentSessionId, id).catch(() => {});
      refreshSessions(sessionQuery).catch(() => {});
    },
    [currentSessionId, refreshSessions, removeSource, sessionQuery]
  );

  const handleToggleAll = useCallback(() => {
    if (allSelected) {
      deselectAllSources();
    } else {
      selectAllSources();
    }
  }, [allSelected, deselectAllSources, selectAllSources]);

  const handleCreateSession = useCallback(async () => {
    const id = await createAndOpenSession("未命名会话");
    await refreshSessions(sessionQuery);
    setCurrentSessionId(id);
    setActiveTab("sources");
  }, [createAndOpenSession, refreshSessions, sessionQuery, setCurrentSessionId]);

  const handleRenameSession = useCallback(
    async (sessionId: string, oldTitle: string) => {
      const nextTitle = window.prompt("输入新的会话名称", oldTitle)?.trim();
      if (!nextTitle || nextTitle === oldTitle) return;
      const updated = await updateSession(sessionId, { title: nextTitle });
      upsertSession(updated);
    },
    [upsertSession]
  );

  const handleDeleteSession = useCallback(
    async (sessionId: string) => {
      if (!window.confirm("确认删除该会话？会话将被归档。")) return;
      await removeSession(sessionId);
      removeSessionEntry(sessionId);
      const next = await refreshSessions("");
      if (next.length > 0) {
        const fallback = next[0].id;
        await loadSession(fallback);
      } else {
        await handleCreateSession();
      }
    },
    [handleCreateSession, loadSession, refreshSessions, removeSessionEntry]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    if (activeTab !== "sources") return;
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, [activeTab]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    if (activeTab !== "sources") return;
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, [activeTab]);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      if (activeTab !== "sources") return;
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);

      const files = Array.from(e.dataTransfer.files);
      if (files.length > 0) {
        void handleUploadFiles(files);
        return;
      }

      const text = e.dataTransfer.getData("text/plain");
      if (text && isUrl(text)) {
        void handleUrlSubmit(text);
      }
    },
    [activeTab, handleUploadFiles, handleUrlSubmit]
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent) => {
      if (activeTab !== "sources") return;
      const files = Array.from(e.clipboardData.files);
      if (files.length > 0) {
        void handleUploadFiles(files);
        return;
      }

      const text = e.clipboardData.getData("text/plain");
      if (text && isUrl(text)) {
        e.preventDefault();
        void handleUrlSubmit(text);
      }
    },
    [activeTab, handleUploadFiles, handleUrlSubmit]
  );

  return (
    <>
      <div
        className={cn(
          "relative flex w-[340px] shrink-0 flex-col border-r border-border bg-muted/30",
          isDragOver && "ring-2 ring-inset ring-primary/50"
        )}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onPaste={handlePaste}
        tabIndex={0}
      >
        {isDragOver && (
          <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-primary/5">
            <p className="text-sm font-medium text-primary">松开以上传素材</p>
          </div>
        )}

        <Tabs
          value={activeTab}
          onValueChange={(value) => setActiveTab(value as "sources" | "sessions")}
          className="flex min-h-0 flex-1 flex-col gap-0"
        >
          <div className="border-b border-border px-4 py-3">
            <TabsList className="grid w-full grid-cols-2" aria-label="切换素材和会话视图">
              <TabsTrigger value="sources">素材</TabsTrigger>
              <TabsTrigger value="sessions">会话</TabsTrigger>
            </TabsList>
            <p className="mt-2 text-xs text-muted-foreground">
              {workspaceId}
            </p>
          </div>

          <TabsContent value="sources" className="flex min-h-0 flex-1 flex-col data-[state=inactive]:hidden">
            <div className="border-b border-border px-4 py-3">
              <div className="flex items-center gap-2">
                {readySources.length > 0 && (
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={handleToggleAll}
                    className="h-4 w-4 cursor-pointer rounded border-gray-300 accent-primary"
                    aria-label="全选来源"
                  />
                )}
                <h2 className="text-sm font-semibold">会话素材</h2>
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {currentSessionId
                  ? loadingSession
                    ? "加载会话中..."
                    : readySources.length > 0
                      ? `已选择 ${selectedCount}/${readySources.length} 个来源`
                      : `已添加 ${sources.length} 个来源`
                  : "正在初始化会话..."}
              </p>
            </div>

            <div className="flex-1 overflow-y-auto px-3 py-2">
              {sources.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-center text-sm text-muted-foreground">
                  <p>当前会话还没有素材</p>
                  <p className="mt-1 text-xs">上传文档、粘贴网址，即可开始生成</p>
                </div>
              ) : (
                <div className="space-y-1.5">
                  {sources.map((source) => (
                    <SourceItem
                      key={source.id}
                      source={source}
                      isSelected={selectedSourceIds.includes(source.id)}
                      onToggleSelect={toggleSourceSelection}
                      onRemove={handleRemoveSource}
                      onPreview={setPreviewSource}
                    />
                  ))}
                </div>
              )}
            </div>

            <div className="border-t border-border px-3 py-3">
              <AddSourceArea
                onFilesSelected={(files) => {
                  void handleUploadFiles(files);
                }}
                onUrlSubmit={(url) => {
                  void handleUrlSubmit(url);
                }}
              />
            </div>
          </TabsContent>

          <TabsContent value="sessions" className="flex min-h-0 flex-1 flex-col data-[state=inactive]:hidden">
            <div className="space-y-2 border-b border-border px-3 py-3">
              <button
                onClick={() => {
                  void handleCreateSession();
                }}
                className="inline-flex h-10 w-full items-center justify-center gap-1.5 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
              >
                <Plus className="h-4 w-4" />
                新建会话
              </button>
              <div className="relative">
                <Search className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                <input
                  value={sessionQuery}
                  onChange={(e) => setSessionQuery(e.target.value)}
                  placeholder="搜索会话"
                  className="h-9 w-full rounded-md border border-input bg-background pl-8 pr-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-2 py-2">
              {sessions.length === 0 ? (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  暂无会话
                </div>
              ) : (
                <div className="space-y-1">
                  {sessions.map((session) => {
                    const active = session.id === currentSessionId;
                    return (
                      <div
                        key={session.id}
                        className={cn(
                          "rounded-md border px-2 py-2",
                          active
                            ? "border-primary/50 bg-primary/5"
                            : "border-transparent hover:border-border hover:bg-accent/40"
                        )}
                      >
                        <button
                          onClick={() => {
                            void loadSession(session.id);
                            setActiveTab("sources");
                          }}
                          className="w-full text-left"
                        >
                          <p className="truncate text-sm font-medium">{session.title || "未命名会话"}</p>
                          <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
                            <span className="inline-flex items-center gap-1">
                              <MessageSquare className="h-3.5 w-3.5" />
                              {session.chat_count} 对话 · {session.source_count} 素材
                            </span>
                            <span>{formatUpdatedAt(session.updated_at)}</span>
                          </div>
                        </button>
                        <div className="mt-2 flex justify-end gap-1">
                          <button
                            onClick={() => {
                              void handleRenameSession(session.id, session.title);
                            }}
                            className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                            aria-label="重命名会话"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => {
                              void handleDeleteSession(session.id);
                            }}
                            className="rounded p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                            aria-label="删除会话"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </TabsContent>
        </Tabs>

        <div className="border-t border-border px-2 py-2">
          <UserMenu />
        </div>
      </div>

      {previewSource && currentSessionId && (
        <SourcePreviewModal
          source={previewSource}
          sessionId={currentSessionId}
          onClose={() => setPreviewSource(null)}
        />
      )}
    </>
  );
}

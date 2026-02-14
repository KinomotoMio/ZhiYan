"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Ellipsis, Pencil, Plus, Trash2, ExternalLink } from "lucide-react";
import { useAppStore, type ChatMessage } from "@/lib/store";
import {
  appendSessionChat,
  createSession,
  createSessionSnapshot,
  fetchWorkspaceUrlSource,
  getSessionDetail,
  getWorkspaceId,
  linkSourcesToSession,
  listSessions,
  listWorkspaceSources,
  removeSession,
  unlinkSourceFromSession,
  updateSession,
  uploadWorkspaceSource,
} from "@/lib/api";
import SourceItem from "./SourceItem";
import SourcePreviewModal from "./SourcePreviewModal";
import AddSourceArea from "./AddSourceArea";
import SessionSwitcher from "./SessionSwitcher";
import RenameDialog from "./RenameDialog";
import DeleteConfirmDialog from "./DeleteConfirmDialog";
import UserMenu from "@/components/settings/UserMenu";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import {
  getSessionEditorPath,
  pickCreateLandingSessionId,
  shouldAutoRedirectToEditor,
} from "@/lib/routes";
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
  const router = useRouter();
  const searchParams = useSearchParams();
  const preferredSessionId = searchParams.get("session");
  const {
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

  const [sessionQuery, setSessionQuery] = useState("");
  const [workspaceQuery, setWorkspaceQuery] = useState("");
  const [workspaceSources, setWorkspaceSources] = useState<SourceMeta[]>([]);
  const [loadingWorkspaceSources, setLoadingWorkspaceSources] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [previewSource, setPreviewSource] = useState<SourceMeta | null>(null);
  const [loadingSession, setLoadingSession] = useState(false);
  const [renameTarget, setRenameTarget] = useState<{ id: string; title: string } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string } | null>(null);
  const bootstrappedRef = useRef(false);

  const readySources = sources.filter((s) => s.status === "ready");
  const selectedCount = readySources.filter((s) =>
    selectedSourceIds.includes(s.id)
  ).length;
  const allSelected =
    readySources.length > 0 && selectedCount === readySources.length;
  const linkedSourceIds = new Set(sources.map((item) => item.id));
  const reusableWorkspaceSources = workspaceSources.filter(
    (item) => !linkedSourceIds.has(item.id) && item.status === "ready"
  );

  const currentSession = sessions.find((s) => s.id === currentSessionId);
  const currentSessionTitle = currentSession?.title || "未命名会话";

  const refreshSessions = useCallback(
    async (q = "") => {
      const result = await listSessions({ q, limit: 100, offset: 0 });
      setSessions(result);
      return result;
    },
    [setSessions]
  );

  const refreshWorkspaceSources = useCallback(async (q = "") => {
    setLoadingWorkspaceSources(true);
    try {
      const result = await listWorkspaceSources({ q, limit: 100, offset: 0 });
      setWorkspaceSources(result);
      return result;
    } finally {
      setLoadingWorkspaceSources(false);
    }
  }, []);

  const loadSession = useCallback(
    async (
      sessionId: string,
      options?: {
        fromExplicitSessionParam?: boolean;
      }
    ) => {
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

        if (
          shouldAutoRedirectToEditor(
            Boolean(detail.latest_presentation),
            Boolean(options?.fromExplicitSessionParam)
          )
        ) {
          router.push(getSessionEditorPath(sessionId));
          return;
        }
      } finally {
        setLoadingSession(false);
      }
    },
    [resetJobState, router, setCurrentSessionId, setSessionData, upsertSession]
  );

  const createAndOpenSession = useCallback(
    async (title: string) => {
      const created = await createSession(title);
      upsertSession(created);
      await loadSession(created.id, { fromExplicitSessionParam: false });
      return created.id;
    },
    [loadSession, upsertSession]
  );

  // Bootstrap: load workspace + sessions on mount
  useEffect(() => {
    if (bootstrappedRef.current) return;
    bootstrappedRef.current = true;

    let cancelled = false;
    const run = async () => {
      const wsId = getWorkspaceId();
      setWorkspaceId(wsId);

      let items = await refreshSessions();
      await refreshWorkspaceSources();
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
          await loadSession(migratedSessionId, { fromExplicitSessionParam: false });
          return;
        }

        const sid = await createAndOpenSession("未命名会话");
        items = await refreshSessions();
        if (cancelled) return;
        await loadSession(sid, { fromExplicitSessionParam: false });
        return;
      }

      if (preferredSessionId && items.some((item) => item.id === preferredSessionId)) {
        await loadSession(preferredSessionId, { fromExplicitSessionParam: true });
        return;
      }

      const landingSessionId = pickCreateLandingSessionId(items, currentSessionId);
      if (landingSessionId) {
        await loadSession(landingSessionId, { fromExplicitSessionParam: false });
        return;
      }

      const sid = await createAndOpenSession("未命名会话");
      await refreshSessions();
      if (cancelled) return;
      await loadSession(sid, { fromExplicitSessionParam: false });
    };

    run().catch((err) => {
      console.error("session bootstrap failed", err);
    });

    return () => {
      cancelled = true;
    };
  }, [
    createAndOpenSession,
    currentSessionId,
    loadSession,
    preferredSessionId,
    refreshSessions,
    refreshWorkspaceSources,
    setWorkspaceId,
  ]);

  // Debounced session search
  useEffect(() => {
    const timer = window.setTimeout(() => {
      refreshSessions(sessionQuery).catch((err) => {
        console.error("refresh sessions failed", err);
      });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [refreshSessions, sessionQuery]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      refreshWorkspaceSources(workspaceQuery).catch((err) => {
        console.error("refresh workspace sources failed", err);
      });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [refreshWorkspaceSources, workspaceQuery]);

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
          const meta = await uploadWorkspaceSource(file, (pct) => {
            if (pct < 100) {
              updateSource(tempId, { status: "uploading" });
            }
          });
          await linkSourcesToSession(sessionId, [meta.id]);
          removeSource(tempId);
          addSource(meta);
          refreshSessions(sessionQuery).catch(() => {});
          refreshWorkspaceSources(workspaceQuery).catch(() => {});
        } catch {
          updateSource(tempId, {
            status: "error",
            error: "上传失败",
          });
        }
      }
    },
    [
      addSource,
      ensureSession,
      refreshSessions,
      refreshWorkspaceSources,
      removeSource,
      sessionQuery,
      updateSource,
      workspaceQuery,
    ]
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
        const meta = await fetchWorkspaceUrlSource(url);
        await linkSourcesToSession(sessionId, [meta.id]);
        removeSource(tempId);
        addSource(meta);
        refreshSessions(sessionQuery).catch(() => {});
        refreshWorkspaceSources(workspaceQuery).catch(() => {});
      } catch {
        updateSource(tempId, { status: "error", error: "抓取失败" });
      }
    },
    [
      addSource,
      ensureSession,
      refreshSessions,
      refreshWorkspaceSources,
      removeSource,
      sessionQuery,
      updateSource,
      workspaceQuery,
    ]
  );

  const handleAttachWorkspaceSource = useCallback(
    async (source: SourceMeta) => {
      const sessionId = await ensureSession();
      await linkSourcesToSession(sessionId, [source.id]);
      addSource(source);
      refreshSessions(sessionQuery).catch(() => {});
    },
    [addSource, ensureSession, refreshSessions, sessionQuery]
  );

  const handleRemoveSource = useCallback(
    async (id: string) => {
      if (!currentSessionId) return;
      removeSource(id);
      unlinkSourceFromSession(currentSessionId, id).catch(() => {});
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
  }, [createAndOpenSession, refreshSessions, sessionQuery, setCurrentSessionId]);

  const handleOpenSessionResult = useCallback(
    (sessionId: string) => {
      setCurrentSessionId(sessionId);
      router.push(getSessionEditorPath(sessionId));
    },
    [router, setCurrentSessionId]
  );

  const handleRenameConfirm = useCallback(
    async (newTitle: string) => {
      if (!renameTarget) return;
      const updated = await updateSession(renameTarget.id, { title: newTitle });
      upsertSession(updated);
    },
    [renameTarget, upsertSession]
  );

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) return;
    await removeSession(deleteTarget.id);
    removeSessionEntry(deleteTarget.id);
    const next = await refreshSessions("");
    const landingSessionId = pickCreateLandingSessionId(next, null);
    if (landingSessionId) {
      await loadSession(landingSessionId, { fromExplicitSessionParam: false });
    } else {
      await handleCreateSession();
    }
  }, [deleteTarget, handleCreateSession, loadSession, refreshSessions, removeSessionEntry]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
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
    [handleUploadFiles, handleUrlSubmit]
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent) => {
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
    [handleUploadFiles, handleUrlSubmit]
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

        {/* SessionHeader: switcher + actions */}
        <div className="flex items-center gap-1 border-b border-border px-3 py-2.5">
          <SessionSwitcher
            sessions={sessions}
            currentSessionId={currentSessionId}
            currentSessionTitle={currentSessionTitle}
            sessionQuery={sessionQuery}
            onSessionQueryChange={setSessionQuery}
            onSelectSession={(id) => {
              void loadSession(id, { fromExplicitSessionParam: true });
            }}
            onCreateSession={() => {
              void handleCreateSession();
            }}
            loadingSession={loadingSession}
          />

          {/* More actions menu */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                aria-label="会话操作"
              >
                <Ellipsis className="h-4 w-4" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onClick={() =>
                  setRenameTarget({
                    id: currentSessionId || "",
                    title: currentSessionTitle,
                  })
                }
                disabled={!currentSessionId}
              >
                <Pencil className="h-4 w-4" />
                重命名
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => {
                  if (currentSessionId) {
                    handleOpenSessionResult(currentSessionId);
                  }
                }}
                disabled={!currentSessionId}
              >
                <ExternalLink className="h-4 w-4" />
                编辑结果
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                variant="destructive"
                onClick={() =>
                  setDeleteTarget({
                    id: currentSessionId || "",
                    title: currentSessionTitle,
                  })
                }
                disabled={!currentSessionId}
              >
                <Trash2 className="h-4 w-4" />
                删除会话
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

        </div>

        {/* Source stats bar */}
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

        {/* Source list (scrollable) */}
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

        {/* Workspace library */}
        <div className="border-t border-border px-3 py-2">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Workspace 素材库
            </h3>
            <span className="text-xs text-muted-foreground">
              {loadingWorkspaceSources ? "加载中..." : `${workspaceSources.length} 条`}
            </span>
          </div>
          <input
            value={workspaceQuery}
            onChange={(e) => setWorkspaceQuery(e.target.value)}
            placeholder="检索素材库..."
            className="mb-2 h-8 w-full rounded-md border border-input bg-background px-2 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <div className="max-h-28 space-y-1 overflow-y-auto">
            {reusableWorkspaceSources.length === 0 ? (
              <p className="py-2 text-xs text-muted-foreground">
                暂无可复用素材（当前会话已全部关联或素材库为空）
              </p>
            ) : (
              reusableWorkspaceSources.slice(0, 8).map((source) => (
                <div
                  key={`workspace-${source.id}`}
                  className="flex items-center justify-between rounded-md border border-border bg-card px-2 py-1.5"
                >
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium">{source.name}</p>
                    <p className="truncate text-[11px] text-muted-foreground">{source.type}</p>
                  </div>
                  <button
                    onClick={() => {
                      void handleAttachWorkspaceSource(source);
                    }}
                    className="ml-2 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
                    aria-label="关联到当前会话"
                  >
                    <Plus className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Add source area */}
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

        {/* User menu */}
        <div className="border-t border-border px-2 py-2">
          <UserMenu />
        </div>
      </div>

      {/* Dialogs */}
      <RenameDialog
        open={renameTarget !== null}
        currentTitle={renameTarget?.title || ""}
        onConfirm={(newTitle) => {
          void handleRenameConfirm(newTitle);
        }}
        onClose={() => setRenameTarget(null)}
      />

      <DeleteConfirmDialog
        open={deleteTarget !== null}
        sessionTitle={deleteTarget?.title || ""}
        onConfirm={() => {
          void handleDeleteConfirm();
        }}
        onClose={() => setDeleteTarget(null)}
      />

      {previewSource && (
        <SourcePreviewModal
          source={previewSource}
          onClose={() => setPreviewSource(null)}
        />
      )}
    </>
  );
}

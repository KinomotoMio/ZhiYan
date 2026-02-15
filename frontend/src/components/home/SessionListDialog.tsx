"use client";

import { useMemo, useState, useCallback } from "react";
import {
  ArrowRight,
  Check,
  Ellipsis,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Presentation,
  Search,
  Trash2,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import type { SessionSummary } from "@/lib/api";
import { cn } from "@/lib/utils";
import RenameDialog from "@/components/create/RenameDialog";

interface SessionListDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  emptyText: string;
  sessions: SessionSummary[];
  getSessionTitle: (session: SessionSummary) => string;
  getSessionMeta: (session: SessionSummary) => string;
  onOpenSession: (session: SessionSummary) => void;
  onCreateSession?: () => Promise<void>;
  onRenameSession?: (id: string, newTitle: string) => Promise<void>;
  onDeleteSession?: (id: string) => Promise<void>;
  onTogglePinSession?: (id: string, isPinned: boolean) => Promise<void>;
  onBatchDeleteSessions?: (ids: string[]) => Promise<void>;
}

type SortOrder = "latest" | "earliest";

function toTimestamp(iso: string): number {
  const time = Date.parse(iso);
  return Number.isNaN(time) ? 0 : time;
}

export default function SessionListDialog({
  open,
  onOpenChange,
  title,
  description,
  emptyText,
  sessions,
  getSessionTitle,
  getSessionMeta,
  onOpenSession,
  onCreateSession,
  onRenameSession,
  onDeleteSession,
  onTogglePinSession,
  onBatchDeleteSessions,
}: SessionListDialogProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [sortOrder, setSortOrder] = useState<SortOrder>("latest");
  const [batchMode, setBatchMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [renameTarget, setRenameTarget] = useState<{
    id: string;
    title: string;
  } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{
    id: string;
    title: string;
  } | null>(null);
  const [batchDeleteConfirm, setBatchDeleteConfirm] = useState(false);

  const hasManagement = Boolean(
    onRenameSession || onDeleteSession || onTogglePinSession
  );

  const handleDialogOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      setSearchTerm("");
      setSortOrder("latest");
      setBatchMode(false);
      setSelectedIds(new Set());
    }
    onOpenChange(nextOpen);
  };

  const filteredSessions = useMemo(() => {
    const normalizedTerm = searchTerm.trim().toLowerCase();
    const items =
      normalizedTerm.length === 0
        ? sessions
        : sessions.filter((session) =>
            getSessionTitle(session).toLowerCase().includes(normalizedTerm)
          );

    return [...items].sort((a, b) => {
      if (a.is_pinned !== b.is_pinned) return a.is_pinned ? -1 : 1;
      const left = toTimestamp(a.updated_at);
      const right = toTimestamp(b.updated_at);
      return sortOrder === "latest" ? right - left : left - right;
    });
  }, [getSessionTitle, searchTerm, sessions, sortOrder]);

  const hasSourceItems = sessions.length > 0;
  const hasFilteredItems = filteredSessions.length > 0;

  const toggleBatchMode = useCallback(() => {
    setBatchMode((prev) => {
      if (prev) setSelectedIds(new Set());
      return !prev;
    });
  }, []);

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleBatchDelete = useCallback(async () => {
    if (!onBatchDeleteSessions || selectedIds.size === 0) return;
    await onBatchDeleteSessions(Array.from(selectedIds));
    setSelectedIds(new Set());
    setBatchMode(false);
    setBatchDeleteConfirm(false);
  }, [onBatchDeleteSessions, selectedIds]);

  const handleRenameConfirm = useCallback(
    async (newTitle: string) => {
      if (!renameTarget || !onRenameSession) return;
      await onRenameSession(renameTarget.id, newTitle);
    },
    [onRenameSession, renameTarget]
  );

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget || !onDeleteSession) return;
    await onDeleteSession(deleteTarget.id);
    setDeleteTarget(null);
  }, [deleteTarget, onDeleteSession]);

  return (
    <>
      <Dialog open={open} onOpenChange={handleDialogOpenChange}>
        <DialogContent className="max-h-[85vh] gap-0 overflow-hidden border-slate-200 bg-white p-0 shadow-[0_26px_70px_-42px_rgba(15,23,42,0.65)] sm:max-w-3xl">
          <div className="border-b border-slate-200 bg-slate-50 px-6 py-5">
            <DialogHeader className="space-y-1.5 text-left">
              <DialogTitle className="text-xl font-semibold text-slate-900">
                {title}
              </DialogTitle>
              <DialogDescription className="text-sm text-slate-600">
                {description}
              </DialogDescription>
            </DialogHeader>
            <div className="mt-3 flex items-center gap-2">
              <p className="inline-flex items-center rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700">
                共 {filteredSessions.length} 条
              </p>
              {onCreateSession && (
                <button
                  type="button"
                  onClick={() => {
                    void onCreateSession();
                    handleDialogOpenChange(false);
                  }}
                  className="inline-flex items-center gap-1 rounded-full border border-cyan-200 bg-white px-3 py-1 text-xs font-medium text-cyan-700 transition-colors hover:bg-cyan-50"
                >
                  <Plus className="h-3.5 w-3.5" />
                  新建会话
                </button>
              )}
            </div>
          </div>

          <div className="border-b border-slate-200 bg-white px-4 py-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <Input
                  aria-label="按标题搜索会话"
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  placeholder="搜索标题或文稿文件名"
                  className="h-10 rounded-lg border-slate-300 bg-white pl-9 text-sm shadow-none"
                />
              </div>

              <div className="flex items-center gap-2">
                <div
                  role="group"
                  aria-label="更新时间排序"
                  className="inline-flex h-10 items-center rounded-lg border border-slate-300 bg-slate-50 p-1"
                >
                  <button
                    type="button"
                    aria-pressed={sortOrder === "latest"}
                    onClick={() => setSortOrder("latest")}
                    className={cn(
                      "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                      sortOrder === "latest"
                        ? "bg-slate-900 text-white shadow-sm"
                        : "text-slate-600 hover:bg-slate-100"
                    )}
                  >
                    最近更新
                  </button>
                  <button
                    type="button"
                    aria-pressed={sortOrder === "earliest"}
                    onClick={() => setSortOrder("earliest")}
                    className={cn(
                      "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                      sortOrder === "earliest"
                        ? "bg-slate-900 text-white shadow-sm"
                        : "text-slate-600 hover:bg-slate-100"
                    )}
                  >
                    最早更新
                  </button>
                </div>

                {hasManagement && onBatchDeleteSessions && (
                  <button
                    type="button"
                    onClick={toggleBatchMode}
                    className={cn(
                      "h-10 rounded-lg border px-3 text-xs font-medium transition-colors",
                      batchMode
                        ? "border-cyan-300 bg-cyan-50 text-cyan-700"
                        : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50"
                    )}
                  >
                    {batchMode ? "退出批量" : "批量操作"}
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className="relative max-h-[62vh] overflow-y-auto bg-slate-50/60 px-4 py-4">
            {!hasSourceItems ? (
              <p className="rounded-xl border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500">
                {emptyText}
              </p>
            ) : !hasFilteredItems ? (
              <div className="rounded-xl border border-slate-200 bg-white px-4 py-8 text-center">
                <p className="text-sm font-medium text-slate-700">
                  无匹配结果
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  试试其他关键词，或清空搜索后查看全部内容。
                </p>
                <button
                  type="button"
                  onClick={() => setSearchTerm("")}
                  className="mt-4 inline-flex h-9 items-center justify-center rounded-lg border border-slate-300 bg-white px-3 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100"
                >
                  清空搜索
                </button>
              </div>
            ) : (
              <div className="space-y-2.5">
                {filteredSessions.map((session) => (
                  <div
                    key={session.id}
                    className="group flex items-center gap-2"
                  >
                    {batchMode && (
                      <button
                        type="button"
                        onClick={() => toggleSelect(session.id)}
                        className={cn(
                          "flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors",
                          selectedIds.has(session.id)
                            ? "border-cyan-500 bg-cyan-500 text-white"
                            : "border-slate-300 bg-white hover:border-slate-400"
                        )}
                      >
                        {selectedIds.has(session.id) && (
                          <Check className="h-3.5 w-3.5" />
                        )}
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={() => {
                        if (batchMode) {
                          toggleSelect(session.id);
                          return;
                        }
                        handleDialogOpenChange(false);
                        onOpenSession(session);
                      }}
                      className="flex min-w-0 flex-1 items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 text-left shadow-[0_12px_24px_-22px_rgba(15,23,42,0.45)] transition-all duration-200 hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-[0_16px_24px_-20px_rgba(15,23,42,0.38)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="flex items-center gap-1.5 truncate text-sm font-semibold text-slate-900">
                          {session.is_pinned && (
                            <Pin className="h-3.5 w-3.5 shrink-0 text-amber-500" />
                          )}
                          {session.has_presentation && (
                            <Presentation className="h-3.5 w-3.5 shrink-0 text-green-500" />
                          )}
                          {getSessionTitle(session)}
                        </p>
                        <p className="mt-1 truncate text-xs text-slate-500">
                          {getSessionMeta(session)}
                        </p>
                      </div>

                      {!batchMode && !hasManagement && (
                        <ArrowRight className="h-4 w-4 shrink-0 text-slate-400 transition-colors group-hover:text-slate-700" />
                      )}
                    </button>

                    {!batchMode && hasManagement && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <button
                            type="button"
                            onClick={(e) => e.stopPropagation()}
                            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-400 opacity-0 transition-all group-hover:opacity-100 hover:bg-slate-100 hover:text-slate-700"
                            aria-label="会话操作"
                          >
                            <Ellipsis className="h-4 w-4" />
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          {onRenameSession && (
                            <DropdownMenuItem
                              onClick={() =>
                                setRenameTarget({
                                  id: session.id,
                                  title:
                                    session.title || "未命名会话",
                                })
                              }
                            >
                              <Pencil className="h-4 w-4" />
                              重命名
                            </DropdownMenuItem>
                          )}
                          {onTogglePinSession && (
                            <DropdownMenuItem
                              onClick={() => {
                                void onTogglePinSession(
                                  session.id,
                                  !session.is_pinned
                                );
                              }}
                            >
                              {session.is_pinned ? (
                                <>
                                  <PinOff className="h-4 w-4" />
                                  取消置顶
                                </>
                              ) : (
                                <>
                                  <Pin className="h-4 w-4" />
                                  置顶
                                </>
                              )}
                            </DropdownMenuItem>
                          )}
                          {onDeleteSession && (
                            <>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                variant="destructive"
                                onClick={() =>
                                  setDeleteTarget({
                                    id: session.id,
                                    title:
                                      session.title || "未命名会话",
                                  })
                                }
                              >
                                <Trash2 className="h-4 w-4" />
                                删除
                              </DropdownMenuItem>
                            </>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </div>
                ))}
              </div>
            )}

            {batchMode && selectedIds.size > 0 && (
              <div className="sticky bottom-0 mt-4 flex items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-lg">
                <span className="text-sm font-medium text-slate-700">
                  已选中 {selectedIds.size} 项
                </span>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => setBatchDeleteConfirm(true)}
                >
                  <Trash2 className="mr-1.5 h-4 w-4" />
                  批量删除
                </Button>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <RenameDialog
        open={renameTarget !== null}
        currentTitle={renameTarget?.title || ""}
        onConfirm={(newTitle) => {
          void handleRenameConfirm(newTitle);
        }}
        onClose={() => setRenameTarget(null)}
      />

      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(v) => !v && setDeleteTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除会话</DialogTitle>
            <DialogDescription>
              确认删除会话「{deleteTarget?.title}」？会话将被归档。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                void handleDeleteConfirm();
              }}
            >
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={batchDeleteConfirm}
        onOpenChange={(v) => !v && setBatchDeleteConfirm(false)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>批量删除</DialogTitle>
            <DialogDescription>
              确认删除选中的 {selectedIds.size} 个会话？此操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setBatchDeleteConfirm(false)}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                void handleBatchDelete();
              }}
            >
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

"use client";

import { useMemo, useState } from "react";
import { ArrowRight, Search } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { SessionSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

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
}: SessionListDialogProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [sortOrder, setSortOrder] = useState<SortOrder>("latest");
  const handleDialogOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      setSearchTerm("");
      setSortOrder("latest");
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
      const left = toTimestamp(a.updated_at);
      const right = toTimestamp(b.updated_at);
      return sortOrder === "latest" ? right - left : left - right;
    });
  }, [getSessionTitle, searchTerm, sessions, sortOrder]);

  const hasSourceItems = sessions.length > 0;
  const hasFilteredItems = filteredSessions.length > 0;

  return (
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
          <p className="mt-3 inline-flex items-center rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700">
            共 {filteredSessions.length} 条
          </p>
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
          </div>
        </div>

        <div className="max-h-[62vh] overflow-y-auto bg-slate-50/60 px-4 py-4">
          {!hasSourceItems ? (
            <p className="rounded-xl border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500">
              {emptyText}
            </p>
          ) : !hasFilteredItems ? (
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-8 text-center">
              <p className="text-sm font-medium text-slate-700">无匹配结果</p>
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
                <button
                  key={session.id}
                  onClick={() => {
                    handleDialogOpenChange(false);
                    onOpenSession(session);
                  }}
                  className="group flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 text-left shadow-[0_12px_24px_-22px_rgba(15,23,42,0.45)] transition-all duration-200 hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-[0_16px_24px_-20px_rgba(15,23,42,0.38)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-900">
                      {getSessionTitle(session)}
                    </p>
                    <p className="mt-1 truncate text-xs text-slate-500">
                      {getSessionMeta(session)}
                    </p>
                  </div>
                  <ArrowRight className="h-4 w-4 shrink-0 text-slate-400 transition-colors group-hover:text-slate-700" />
                </button>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

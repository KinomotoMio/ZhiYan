"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { ChevronDown, MessageSquare, Presentation, Plus, Search } from "lucide-react";
import { Popover as PopoverPrimitive } from "radix-ui";
import { cn } from "@/lib/utils";
import type { SessionSummary } from "@/lib/api";

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

interface SessionSwitcherProps {
  sessions: SessionSummary[];
  currentSessionId: string | null;
  currentSessionTitle: string;
  sessionQuery: string;
  onSessionQueryChange: (q: string) => void;
  onSelectSession: (id: string) => void;
  onCreateSession: () => void;
  loadingSession: boolean;
}

export default function SessionSwitcher({
  sessions,
  currentSessionId,
  currentSessionTitle,
  sessionQuery,
  onSessionQueryChange,
  onSelectSession,
  onCreateSession,
  loadingSession,
}: SessionSwitcherProps) {
  const [open, setOpen] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      // auto-focus the search input when popover opens
      requestAnimationFrame(() => {
        searchInputRef.current?.focus();
      });
    } else {
      onSessionQueryChange("");
    }
  }, [open, onSessionQueryChange]);

  const handleSelect = useCallback(
    (id: string) => {
      onSelectSession(id);
      setOpen(false);
    },
    [onSelectSession]
  );

  const handleCreate = useCallback(() => {
    onCreateSession();
    setOpen(false);
  }, [onCreateSession]);

  return (
    <PopoverPrimitive.Root open={open} onOpenChange={setOpen}>
      <PopoverPrimitive.Trigger asChild>
        <button
          className="flex min-w-0 flex-1 items-center gap-1.5 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-accent"
          disabled={loadingSession}
        >
          <span className="truncate text-sm font-semibold">
            {loadingSession ? "加载中..." : currentSessionTitle}
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        </button>
      </PopoverPrimitive.Trigger>

      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          align="start"
          sideOffset={4}
          className="z-50 w-[308px] rounded-md border bg-popover p-0 text-popover-foreground shadow-md data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
        >
          {/* Search + Create */}
          <div className="flex items-center gap-1.5 border-b p-2">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-2 top-2 h-4 w-4 text-muted-foreground" />
              <input
                ref={searchInputRef}
                value={sessionQuery}
                onChange={(e) => onSessionQueryChange(e.target.value)}
                placeholder="搜索会话..."
                className="h-8 w-full rounded-md border border-input bg-background pl-8 pr-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <button
              onClick={handleCreate}
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              aria-label="新建会话"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>

          {/* Session list */}
          <div className="max-h-[320px] overflow-y-auto p-1">
            {sessions.length === 0 ? (
              <div className="py-6 text-center text-sm text-muted-foreground">
                暂无会话
              </div>
            ) : (
              sessions.map((session) => {
                const active = session.id === currentSessionId;
                return (
                  <button
                    key={session.id}
                    onClick={() => handleSelect(session.id)}
                    className={cn(
                      "flex w-full flex-col rounded-md px-2.5 py-2 text-left transition-colors",
                      active
                        ? "bg-primary/10 text-foreground"
                        : "text-foreground hover:bg-accent"
                    )}
                  >
                    <span className="flex items-center gap-1.5 truncate text-sm font-medium">
                      {session.has_presentation && (
                        <Presentation className="h-3.5 w-3.5 shrink-0 text-green-500" />
                      )}
                      {session.title || "未命名会话"}
                    </span>
                    <span className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
                      <MessageSquare className="h-3 w-3" />
                      {session.chat_count} 对话 · {session.source_count} 素材
                      <span className="ml-auto">{formatUpdatedAt(session.updated_at)}</span>
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}

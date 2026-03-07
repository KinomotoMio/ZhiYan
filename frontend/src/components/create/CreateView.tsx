"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Ellipsis, Pencil, ExternalLink, Trash2 } from "lucide-react";
import { useAppStore } from "@/lib/store";
import { removeSession, updateSession } from "@/lib/api";
import { getSessionEditorPath } from "@/lib/routes";
import SourcePanel from "./SourcePanel";
import CreateForm from "./CreateForm";
import RenameDialog from "./RenameDialog";
import DeleteConfirmDialog from "./DeleteConfirmDialog";
import SessionTitleInlineEditor from "@/components/session/SessionTitleInlineEditor";
import UserMenu from "@/components/settings/UserMenu";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export default function CreateView() {
  const router = useRouter();
  const sessions = useAppStore((s) => s.sessions);
  const currentSessionId = useAppStore((s) => s.currentSessionId);
  const upsertSession = useAppStore((s) => s.upsertSession);
  const removeSessionEntry = useAppStore((s) => s.removeSessionEntry);

  const currentSession = sessions.find((s) => s.id === currentSessionId);
  const currentSessionTitle = currentSession?.title || "未命名会话";

  const [renameTarget, setRenameTarget] = useState<{
    id: string;
    title: string;
  } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{
    id: string;
    title: string;
  } | null>(null);

  const handleRenameConfirm = useCallback(
    async (newTitle: string) => {
      if (!renameTarget) return;
      const updated = await updateSession(renameTarget.id, { title: newTitle });
      upsertSession(updated);
    },
    [renameTarget, upsertSession]
  );

  const handleRenameSessionTitle = useCallback(
    async (nextTitle: string) => {
      if (!currentSessionId) return;
      const updated = await updateSession(currentSessionId, { title: nextTitle });
      upsertSession(updated);
    },
    [currentSessionId, upsertSession]
  );

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) return;
    await removeSession(deleteTarget.id);
    removeSessionEntry(deleteTarget.id);
    router.push("/");
  }, [deleteTarget, removeSessionEntry, router]);

  const handleOpenSessionResult = useCallback(() => {
    if (!currentSessionId) return;
    router.push(getSessionEditorPath(currentSessionId));
  }, [currentSessionId, router]);

  return (
    <div className="flex min-h-screen flex-col zy-bg-page">
      <div className="flex h-12 shrink-0 items-center gap-3 border-b border-slate-200 bg-white/80 px-4 backdrop-blur-sm">
        <button
          onClick={() => router.push("/")}
          className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" />
          首页
        </button>

        <div className="mx-1 h-4 w-px bg-slate-200" />

        <SessionTitleInlineEditor
          title={currentSessionTitle}
          onSave={handleRenameSessionTitle}
          disabled={!currentSessionId}
          className="min-w-0"
        />

        <div className="ml-auto flex items-center gap-1">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
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
                onClick={handleOpenSessionResult}
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
          <UserMenu compact />
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        <SourcePanel />
        <CreateForm />
      </div>

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
    </div>
  );
}

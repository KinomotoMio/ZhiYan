"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import EditorWorkspace from "@/components/editor/EditorWorkspace";
import { getSessionDetail } from "@/lib/api";
import { useAppStore, type ChatMessage } from "@/lib/store";

type LoadState = "loading" | "ready" | "empty" | "error";

function toStoreChatMessages(records: Array<Record<string, unknown>>): ChatMessage[] {
  return records
    .map((item) => {
      const role = item.role === "assistant" ? "assistant" : "user";
      const content = typeof item.content === "string" ? item.content : "";
      const createdAt = typeof item.created_at === "string" ? item.created_at : "";
      return {
        id:
          typeof item.id === "string"
            ? item.id
            : `msg-${Math.random().toString(36).slice(2)}`,
        role,
        content,
        timestamp: Date.parse(createdAt) || Date.now(),
      } as ChatMessage;
    })
    .filter((item) => item.content.trim().length > 0);
}

export default function SessionEditorPage() {
  const params = useParams<{ sessionId: string }>();
  const router = useRouter();
  const sessionId = useMemo(() => {
    const value = params?.sessionId;
    return typeof value === "string" ? value : "";
  }, [params]);

  const [state, setState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState("会话不存在或无权限访问。");
  const setCurrentSessionId = useAppStore((store) => store.setCurrentSessionId);
  const setSessionData = useAppStore((store) => store.setSessionData);

  useEffect(() => {
    if (!sessionId) return;

    let cancelled = false;

    getSessionDetail(sessionId)
      .then((detail) => {
        if (cancelled) return;
        const chatMessages = toStoreChatMessages(
          detail.chat_messages as unknown as Array<Record<string, unknown>>
        );
        const currentStore = useAppStore.getState();
        const localPresentation =
          currentStore.currentSessionId === sessionId
            ? currentStore.presentation
            : null;
        const presentation =
          detail.latest_presentation?.presentation ?? localPresentation ?? null;

        setCurrentSessionId(sessionId);
        setSessionData({
          sources: detail.sources,
          chatMessages,
          presentation,
        });

        if (presentation) {
          setState("ready");
        } else {
          setState("empty");
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setState("error");
        setErrorMessage(
          err instanceof Error && err.message
            ? `会话加载失败：${err.message}`
            : "会话不存在或无权限访问。"
        );
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId, setCurrentSessionId, setSessionData]);

  if (!sessionId) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-muted-foreground">会话参数缺失。</p>
          <button
            onClick={() => router.push("/")}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md"
          >
            返回创建页
          </button>
        </div>
      </div>
    );
  }

  if (state === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在加载会话内容...
        </div>
      </div>
    );
  }

  if (state === "error") {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-muted-foreground">{errorMessage}</p>
          <button
            onClick={() => router.push("/")}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md"
          >
            返回创建页
          </button>
        </div>
      </div>
    );
  }

  if (state === "empty") {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-muted-foreground">该会话暂无生成结果</p>
          <button
            onClick={() => router.push("/")}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md"
          >
            返回创建页
          </button>
        </div>
      </div>
    );
  }

  return (
    <EditorWorkspace
      returnHref={`/?tab=sessions&session=${encodeURIComponent(sessionId)}`}
      returnLabel="返回会话"
    />
  );
}

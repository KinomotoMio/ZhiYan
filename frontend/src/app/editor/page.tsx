"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAppStore } from "@/lib/store";
import { getSessionEditorPath } from "@/lib/routes";

export default function LegacyEditorPage() {
  const router = useRouter();
  const currentSessionId = useAppStore((state) => state.currentSessionId);

  useEffect(() => {
    if (!currentSessionId) return;
    router.replace(getSessionEditorPath(currentSessionId));
  }, [currentSessionId, router]);

  if (currentSessionId) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-sm text-muted-foreground">正在跳转到会话编辑器...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center space-y-4">
        <p className="text-muted-foreground">未选择会话，请先从创建页进入会话。</p>
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


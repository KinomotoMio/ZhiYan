"use client";

import { useState } from "react";
import { useAppStore, type ChatMessage } from "@/lib/store";

function MessageBubble({ msg }: { msg: ChatMessage }) {
  return (
    <div
      className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
          msg.role === "user"
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground"
        }`}
      >
        {msg.content}
      </div>
    </div>
  );
}

export default function ChatPanel() {
  const { chatMessages, addChatMessage } = useAppStore();
  const [input, setInput] = useState("");

  const handleSend = () => {
    if (!input.trim()) return;

    addChatMessage({
      id: `msg-${Date.now()}`,
      role: "user",
      content: input,
      timestamp: Date.now(),
    });

    // TODO: 接入后端 chat API
    setTimeout(() => {
      addChatMessage({
        id: `msg-${Date.now()}-reply`,
        role: "assistant",
        content: "收到！功能开发中，稍后支持实时对话优化。",
        timestamp: Date.now(),
      });
    }, 500);

    setInput("");
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b font-medium text-sm">AI 助手</div>

      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {chatMessages.length === 0 && (
          <div className="text-center text-muted-foreground text-sm mt-8">
            <p>输入消息或使用 /command 触发 Skill</p>
            <p className="mt-1 text-xs">例如: /ppt-health-check</p>
          </div>
        )}
        {chatMessages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}
      </div>

      {/* 输入框 */}
      <div className="p-3 border-t">
        <div className="flex gap-2">
          <input
            type="text"
            className="flex-1 px-3 py-2 border border-input rounded-md bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            placeholder="输入消息或 /command..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm hover:bg-primary/90 disabled:opacity-50"
          >
            发送
          </button>
        </div>
      </div>
    </div>
  );
}

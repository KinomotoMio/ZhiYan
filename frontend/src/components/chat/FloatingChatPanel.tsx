"use client";

import { useState, useEffect, useRef } from "react";
import {
  Sparkles,
  X,
  RefreshCw,
  Scissors,
  FileText,
  Palette,
  Theater,
  Loader2,
} from "lucide-react";
import { useAppStore, type ChatMessage } from "@/lib/store";
import { chatStream } from "@/lib/api";

function MessageBubble({ msg }: { msg: ChatMessage }) {
  return (
    <div
      className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
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

const QUICK_ACTIONS = [
  {
    category: "优化",
    description: "优化当前幻灯片的布局或内容",
    actions: [
      { icon: RefreshCw, label: "刷新布局", message: "请刷新当前页面的布局" },
      {
        icon: Scissors,
        label: "简洁一点",
        message: "请让当前页面的内容更简洁",
      },
      {
        icon: FileText,
        label: "添加更多",
        message: "请为当前页面添加更多内容细节",
      },
      {
        icon: Palette,
        label: "丰富视觉",
        message: "请丰富当前页面的视觉效果",
      },
    ],
  },
  {
    category: "重新设计",
    description: null,
    actions: [
      { icon: Theater, label: "更改主题", message: "请帮我更换演示文稿的主题风格" },
    ],
  },
];

export default function FloatingChatPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const { chatMessages, addChatMessage, presentation, currentSlideIndex } =
    useAppStore();
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const streamingMsgRef = useRef<string>("");

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) setIsOpen(false);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || isStreaming) return;

    addChatMessage({
      id: `msg-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: Date.now(),
    });

    setIsStreaming(true);
    streamingMsgRef.current = "";
    const replyId = `msg-${Date.now()}-reply`;

    // 先添加一个空的 assistant 消息
    addChatMessage({
      id: replyId,
      role: "assistant",
      content: "",
      timestamp: Date.now(),
    });

    await chatStream(
      {
        message: text,
        presentation_context: presentation
          ? { slides: presentation.slides, title: presentation.title }
          : undefined,
        current_slide_index: currentSlideIndex,
      },
      (chunk) => {
        streamingMsgRef.current += chunk;
        // 更新最后一条消息的内容
        useAppStore.setState((state) => ({
          chatMessages: state.chatMessages.map((msg) =>
            msg.id === replyId
              ? { ...msg, content: streamingMsgRef.current }
              : msg
          ),
        }));
      },
      () => {
        setIsStreaming(false);
      },
      (err) => {
        console.error("Chat error:", err);
        useAppStore.setState((state) => ({
          chatMessages: state.chatMessages.map((msg) =>
            msg.id === replyId
              ? { ...msg, content: `发生错误: ${err.message}` }
              : msg
          ),
        }));
        setIsStreaming(false);
      }
    );
  };

  const handleSend = () => {
    sendMessage(input);
    setInput("");
  };

  const handleQuickAction = (message: string) => {
    sendMessage(message);
  };

  return (
    <>
      {/* 面板 */}
      {isOpen && (
        <>
          {/* 背景点击关闭 */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />

          <div className="fixed bottom-20 right-6 z-50 flex w-[380px] max-h-[600px] flex-col rounded-xl border bg-background shadow-2xl">
            {/* 标题 */}
            <div className="flex items-center justify-between border-b px-4 py-3">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-primary" />
                <span className="text-sm font-semibold">AI 助手</span>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="rounded-md p-1 hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* 消息列表 */}
            <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-[120px] max-h-[240px]">
              {chatMessages.length === 0 && (
                <div className="text-center text-muted-foreground text-xs mt-4">
                  <p>输入消息或使用下方快捷操作</p>
                </div>
              )}
              {chatMessages.map((msg) => (
                <MessageBubble key={msg.id} msg={msg} />
              ))}
              {isStreaming && (
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span>思考中...</span>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* 输入框 */}
            <div className="border-t px-3 py-2">
              <div className="flex gap-2">
                <input
                  type="text"
                  className="flex-1 px-3 py-2 border border-input rounded-md bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder="输入消息或 /command..."
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSend()}
                  disabled={isStreaming}
                />
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || isStreaming}
                  className="px-3 py-2 bg-primary text-primary-foreground rounded-md text-sm hover:bg-primary/90 disabled:opacity-50"
                >
                  发送
                </button>
              </div>
            </div>

            {/* 快捷操作区 */}
            <div className="border-t px-4 py-3 space-y-3">
              {QUICK_ACTIONS.map((group) => (
                <div key={group.category}>
                  <p className="text-xs font-semibold text-foreground">
                    {group.category}
                  </p>
                  {group.description && (
                    <p className="text-xs text-muted-foreground mb-1.5">
                      {group.description}
                    </p>
                  )}
                  <div className="grid grid-cols-2 gap-1.5 mt-1">
                    {group.actions.map((action) => {
                      const Icon = action.icon;
                      return (
                        <button
                          key={action.label}
                          onClick={() => handleQuickAction(action.message)}
                          disabled={isStreaming}
                          className="flex items-center gap-1.5 rounded-md border border-input px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
                        >
                          <Icon className="h-3.5 w-3.5 shrink-0" />
                          {action.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* FAB 按钮 */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`fixed bottom-6 right-6 z-50 flex h-12 w-12 items-center justify-center rounded-full shadow-lg transition-all hover:scale-105 ${
          isOpen
            ? "bg-muted text-muted-foreground"
            : "bg-primary text-primary-foreground"
        }`}
      >
        <Sparkles className="h-5 w-5" />
      </button>
    </>
  );
}

"use client";

import { useState, useEffect, useRef, type ComponentType } from "react";
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
import { toast } from "sonner";
import { useAppStore, type ChatMessage } from "@/lib/store";
import {
  chatStream,
  listSkills,
  saveLatestSessionPresentation,
  type ChatActionHint,
} from "@/lib/api";
import type { Slide } from "@/types/slide";

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

interface QuickAction {
  icon: ComponentType<{ className?: string }>;
  label: string;
  message: string;
  actionHint: ChatActionHint;
}

interface QuickActionGroup {
  category: string;
  description: string | null;
  actions: QuickAction[];
}

const QUICK_ACTIONS: QuickActionGroup[] = [
  {
    category: "优化",
    description: "优化当前幻灯片的布局或内容",
    actions: [
      {
        icon: RefreshCw,
        label: "刷新布局",
        message: "请刷新当前页面的布局",
        actionHint: "refresh_layout",
      },
      {
        icon: Scissors,
        label: "简洁一点",
        message: "请让当前页面的内容更简洁",
        actionHint: "simplify",
      },
      {
        icon: FileText,
        label: "添加更多",
        message: "请为当前页面添加更多内容细节",
        actionHint: "add_detail",
      },
      {
        icon: Palette,
        label: "丰富视觉",
        message: "请丰富当前页面的视觉效果",
        actionHint: "enrich_visual",
      },
    ],
  },
  {
    category: "重新设计",
    description: null,
    actions: [
      {
        icon: Theater,
        label: "更改主题",
        message: "请帮我更换演示文稿的主题风格",
        actionHint: "change_theme",
      },
    ],
  },
];

interface PendingSlideChange {
  previousSlides: Slide[];
  proposedSlides: Slide[];
  modifications: Record<string, unknown>[];
  saving: boolean;
}

function cloneSlides(slides: Slide[]): Slide[] {
  return JSON.parse(JSON.stringify(slides)) as Slide[];
}

export function buildHistoryForApi(
  messages: ChatMessage[],
  replyId: string,
  currentText: string
): Array<{ role: "user" | "assistant"; content: string }> {
  const filtered = messages.filter((m) => m.id !== replyId && m.content.trim());
  if (filtered.length > 0) {
    const last = filtered[filtered.length - 1];
    if (last.role === "user" && last.content.trim() === currentText.trim()) {
      filtered.pop();
    }
  }
  return filtered
    .slice(-20)
    .map((m) => ({ role: m.role, content: m.content }));
}

export function shouldDisableChatActions(
  isStreaming: boolean,
  hasPendingChange: boolean
): boolean {
  return isStreaming || hasPendingChange;
}

export default function FloatingChatPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const {
    chatMessages,
    addChatMessage,
    presentation,
    currentSlideIndex,
    currentSessionId,
    updateSlides,
  } = useAppStore();
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [showSkills, setShowSkills] = useState(false);
  const [skills, setSkills] = useState<{ name: string; description: string; command?: string }[]>([]);
  const [pendingChange, setPendingChange] = useState<PendingSlideChange | null>(null);
  const [noOpReason, setNoOpReason] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const streamingMsgRef = useRef<string>("");
  const messageSeqRef = useRef(1);

  const hasPendingChange = pendingChange !== null;
  const disableActions = shouldDisableChatActions(isStreaming, hasPendingChange);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages, pendingChange, noOpReason]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) setIsOpen(false);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  const handleRollbackPending = () => {
    if (!pendingChange) return;
    updateSlides(cloneSlides(pendingChange.previousSlides));
    setPendingChange(null);
    const rollbackSeq = messageSeqRef.current++;
    addChatMessage({
      id: `msg-${rollbackSeq}-rollback`,
      role: "assistant",
      content: "已撤回上一次预览改稿，当前页面恢复为撤回前状态。",
      timestamp: rollbackSeq,
    });
    toast.info("已撤回本次预览修改");
  };

  const handleApplyPending = async () => {
    if (!pendingChange || !currentSessionId) return;
    const latestPresentation = useAppStore.getState().presentation;
    if (!latestPresentation) {
      toast.error("当前没有可保存的演示稿");
      return;
    }

    setPendingChange((prev) => (prev ? { ...prev, saving: true } : prev));
    try {
      await saveLatestSessionPresentation(currentSessionId, latestPresentation, "chat");
      setPendingChange(null);
      toast.success("已应用并保存到当前会话");
    } catch (err) {
      setPendingChange((prev) => (prev ? { ...prev, saving: false } : prev));
      toast.error(err instanceof Error ? err.message : "保存失败，请稍后重试");
    }
  };

  const sendMessage = async (
    text: string,
    actionHint: ChatActionHint = "free_text"
  ) => {
    if (!text.trim() || disableActions) return;
    if (!currentSessionId) {
      toast.error("请先创建或选择会话");
      return;
    }

    setNoOpReason(null);

    const userSeq = messageSeqRef.current++;
    addChatMessage({
      id: `msg-${userSeq}`,
      role: "user",
      content: text,
      timestamp: userSeq,
    });

    setIsStreaming(true);
    streamingMsgRef.current = "";
    const replySeq = messageSeqRef.current++;
    const replyId = `msg-${replySeq}-reply`;

    addChatMessage({
      id: replyId,
      role: "assistant",
      content: "",
      timestamp: replySeq,
    });

    const currentMessages = useAppStore.getState().chatMessages;
    const historyForApi = buildHistoryForApi(currentMessages, replyId, text);

    await chatStream(
      {
        message: text,
        session_id: currentSessionId,
        messages: historyForApi,
        presentation_context: presentation
          ? { slides: presentation.slides, title: presentation.title }
          : undefined,
        current_slide_index: currentSlideIndex,
        action_hint: actionHint,
      },
      (chunk) => {
        streamingMsgRef.current += chunk;
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
      },
      (slideUpdate) => {
        const currentSlides = useAppStore.getState().presentation?.slides ?? [];
        const previousSlidesSnapshot = pendingChange?.previousSlides
          ? cloneSlides(pendingChange.previousSlides)
          : cloneSlides(currentSlides);
        updateSlides(slideUpdate.slides);
        setPendingChange({
          previousSlides: previousSlidesSnapshot,
          proposedSlides: cloneSlides(slideUpdate.slides),
          modifications: slideUpdate.modifications,
          saving: false,
        });
        toast.info("已生成改稿预览，请确认应用或撤回");
      },
      (noOp) => {
        setNoOpReason(noOp.reason);
        toast.warning(noOp.reason);
      }
    );
  };

  const handleInputChange = (value: string) => {
    setInput(value);
    if (value === "/") {
      listSkills()
        .then((res) => {
          setSkills(res.skills);
          setShowSkills(true);
        })
        .catch(() => setShowSkills(false));
    } else if (!value.startsWith("/")) {
      setShowSkills(false);
    }
  };

  const handleSkillSelect = (command: string) => {
    setInput(`/${command} `);
    setShowSkills(false);
  };

  const handleSend = () => {
    setShowSkills(false);
    void sendMessage(input, "free_text");
    setInput("");
  };

  const handleQuickAction = (action: QuickAction) => {
    void sendMessage(action.message, action.actionHint);
  };

  return (
    <>
      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />

          <div className="fixed bottom-20 right-6 z-50 flex w-[380px] max-h-[640px] flex-col rounded-xl border bg-background shadow-2xl">
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

            {pendingChange && (
              <div className="border-t border-amber-300 bg-amber-50 px-3 py-2">
                <p className="text-xs text-amber-800">
                  已预览 {pendingChange.modifications.length} 处修改，是否应用到当前会话？
                </p>
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      void handleApplyPending();
                    }}
                    disabled={pendingChange.saving || isStreaming}
                    className="flex-1 rounded-md bg-amber-600 px-2 py-1.5 text-xs text-white hover:bg-amber-700 disabled:opacity-50"
                  >
                    {pendingChange.saving ? "保存中..." : "应用并保存"}
                  </button>
                  <button
                    type="button"
                    onClick={handleRollbackPending}
                    disabled={pendingChange.saving}
                    className="flex-1 rounded-md border border-amber-300 px-2 py-1.5 text-xs text-amber-700 hover:bg-amber-100 disabled:opacity-50"
                  >
                    撤回
                  </button>
                </div>
              </div>
            )}

            {noOpReason && (
              <div className="border-t border-muted px-3 py-2 bg-muted/30">
                <p className="text-xs text-muted-foreground">{noOpReason}</p>
              </div>
            )}

            <div className="border-t px-3 py-2">
              {showSkills && skills.length > 0 && (
                <div className="mb-2 max-h-32 overflow-y-auto rounded-md border bg-background shadow-sm">
                  {skills.map((skill) => (
                    <button
                      key={skill.name}
                      onClick={() => handleSkillSelect(skill.command || skill.name)}
                      className="w-full px-3 py-1.5 text-left text-xs hover:bg-accent flex items-center gap-2"
                    >
                      <span className="font-medium">/{skill.command || skill.name}</span>
                      <span className="text-muted-foreground truncate">{skill.description}</span>
                    </button>
                  ))}
                </div>
              )}
              <div className="flex gap-2">
                <input
                  type="text"
                  className="flex-1 px-3 py-2 border border-input rounded-md bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder={
                    hasPendingChange
                      ? "请先应用或撤回当前预览修改"
                      : "输入消息或 / 触发 Skill..."
                  }
                  value={input}
                  onChange={(e) => handleInputChange(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSend()}
                  disabled={disableActions}
                />
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || disableActions}
                  className="px-3 py-2 bg-primary text-primary-foreground rounded-md text-sm hover:bg-primary/90 disabled:opacity-50"
                >
                  发送
                </button>
              </div>
            </div>

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
                          onClick={() => handleQuickAction(action)}
                          disabled={disableActions}
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

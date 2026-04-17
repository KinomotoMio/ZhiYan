"use client";

import { useEffect, useRef, useState, type ComponentType } from "react";
import {
  Bot,
  CheckCircle2,
  FileText,
  Loader2,
  MessageSquareMore,
  Palette,
  RefreshCw,
  Scissors,
  Sparkles,
  Theater,
  Wrench,
  X,
} from "lucide-react";
import { toast } from "sonner";

import MarkdownMessage from "@/components/chat/MarkdownMessage";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  chatStream,
  defaultSkillIdForOutputMode,
  listSkills,
  saveLatestSessionHtmlPresentation,
  saveLatestSessionPresentation,
  saveLatestSessionSlidevPresentation,
  type ChatActionHint,
  type ChatAssistantStatusEvent,
  type ChatToolCallEvent,
  type ChatToolResultEvent,
} from "@/lib/api";
import { sanitizeAssistantText } from "@/lib/chat-sanitize";
import { useAppStore, type ChatMessage } from "@/lib/store";
import { cn } from "@/lib/utils";
import type { Slide } from "@/types/slide";

function ChatAvatar({ role }: { role: "assistant" | "user" }) {
  if (role === "assistant") {
    return (
      <Avatar size="lg" className="ring-1 ring-white/70">
        <AvatarFallback className="bg-cyan-50 text-cyan-700">
          <Sparkles className="h-4 w-4" />
        </AvatarFallback>
      </Avatar>
    );
  }
  return (
    <Avatar size="lg" className="ring-1 ring-white/70">
      <AvatarFallback className="bg-slate-900 text-white">你</AvatarFallback>
    </Avatar>
  );
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  if (msg.role === "user") {
    return (
      <div className="zy-chat-enter-user flex justify-end">
        <div className="flex max-w-[92%] items-end gap-3">
          <div className="zy-chat-enter-body max-w-[640px] rounded-[24px] bg-slate-900 px-5 py-4 text-sm leading-7 text-white shadow-[0_18px_40px_-34px_rgba(15,23,42,0.4)]">
            <p className="whitespace-pre-wrap">{msg.content}</p>
          </div>
          <ChatAvatar role="user" />
        </div>
      </div>
    );
  }

  return (
    <div className="zy-chat-enter-ai flex justify-start">
      <div className="flex max-w-[92%] items-start gap-3">
        <ChatAvatar role="assistant" />
        <div className="zy-chat-enter-body min-w-0 flex-1 pt-1 text-[15px] leading-8 text-slate-700">
          <div className="rounded-[24px] bg-white/72 px-5 py-4 shadow-[0_18px_40px_-34px_rgba(15,23,42,0.28)] backdrop-blur-sm">
            <MarkdownMessage
              content={msg.content}
              className="text-[15px] leading-8 text-slate-700 [&_strong]:text-inherit [&_td]:text-inherit [&_th]:text-inherit"
            />
          </div>
        </div>
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
  mode: "structured" | "html" | "slidev";
  previousSlides: Slide[];
  proposedSlides: Slide[];
  previousHtml: string | null;
  proposedHtml: string | null;
  previousSlidevMarkdown?: string | null;
  proposedSlidevMarkdown?: string | null;
  previousSlidevMeta?: Record<string, unknown> | null;
  proposedSlidevMeta?: Record<string, unknown> | null;
  previousSlidevBuildUrl?: string | null;
  proposedSlidevBuildUrl?: string | null;
  selectedStyleId?: string | null;
  modifications: Record<string, unknown>[];
  saving: boolean;
}

type LoopEvent =
  | {
      type: "assistant_status";
      assistant_status: string;
      summary?: string;
    }
  | ({
      type: "tool_call";
    } & ChatToolCallEvent)
  | ({
      type: "tool_result";
    } & ChatToolResultEvent);

const STATUS_LABELS: Record<string, string> = {
  thinking: "思考中",
  inspecting_context: "读取上下文",
  running_tools: "执行工具",
  applying_change: "正在改稿",
  ready: "已完成",
  error: "出错了",
};

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
  return filtered.slice(-20).map((m) => ({ role: m.role, content: m.content }));
}

export function shouldDisableChatActions(
  isStreaming: boolean,
  hasPendingChange: boolean
): boolean {
  return isStreaming || hasPendingChange;
}

function isEditorVisibleMessage(msg: ChatMessage): boolean {
  return msg.phase !== "planning" && msg.messageKind !== "assistant_status" && msg.messageKind !== "tool_call" && msg.messageKind !== "tool_result";
}

function renderStatusLabel(status: string | null): string {
  if (!status) return "待命";
  return STATUS_LABELS[status] || status;
}

function ProcessTimeline({
  events,
}: {
  events: LoopEvent[];
}) {
  if (events.length === 0) {
    return (
      <div className="rounded-[22px] border border-white/70 bg-white/56 px-4 py-4 text-sm leading-6 text-slate-500">
        这里会显示本轮执行摘要。
      </div>
    );
  }

  return (
    <div className="rounded-[22px] border border-white/70 bg-white/56 px-3 py-3 shadow-[0_18px_40px_-34px_rgba(15,23,42,0.18)]">
      <div className="max-h-[180px] space-y-2 overflow-y-auto pr-1">
        {events.map((event, index) => {
          if (event.type === "assistant_status") {
            return (
              <div
                key={`${event.type}-${event.assistant_status}-${index}`}
                className="flex items-start gap-3 rounded-[18px] bg-slate-50/80 px-3 py-2"
              >
                <Bot className="mt-0.5 h-4 w-4 shrink-0 text-cyan-600" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-800">
                    {renderStatusLabel(event.assistant_status)}
                  </p>
                </div>
              </div>
            );
          }

          if (event.type === "tool_call") {
            return (
              <div
                key={`${event.type}-${event.call_id}-${index}`}
                className="flex items-start gap-3 rounded-[18px] bg-white/78 px-3 py-2"
              >
                <Wrench className="mt-0.5 h-4 w-4 shrink-0 text-slate-600" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-800">{event.summary}</p>
                  <p className="text-xs text-slate-500">{event.tool_name}</p>
                </div>
              </div>
            );
          }

          return (
            <div
              key={`${event.type}-${event.call_id}-${index}`}
              className={cn(
                "flex items-start gap-3 rounded-[18px] px-3 py-2",
                event.ok ? "bg-emerald-50/90" : "bg-rose-50/90"
              )}
            >
              <CheckCircle2
                className={cn(
                  "mt-0.5 h-4 w-4 shrink-0",
                  event.ok ? "text-emerald-600" : "text-rose-600"
                )}
              />
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-800">{event.summary}</p>
                <p className="text-xs text-slate-500">{event.tool_name}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function FloatingChatPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const {
    chatMessages,
    addChatMessage,
    presentation,
    presentationOutputMode,
    presentationHtml,
    presentationSlidevMarkdown,
    presentationSlidevMeta,
    presentationSlidevBuildUrl,
    presentationSlidevDeckArtifact,
    currentSlideIndex,
    currentSessionId,
    updateSlides,
    setPresentation,
    setPresentationHtmlState,
    setPresentationSlidevState,
  } = useAppStore();
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [showSkills, setShowSkills] = useState(false);
  const [skills, setSkills] = useState<{ name: string; description: string; command?: string }[]>([]);
  const [pendingChange, setPendingChange] = useState<PendingSlideChange | null>(null);
  const [noOpReason, setNoOpReason] = useState<string | null>(null);
  const [loopEvents, setLoopEvents] = useState<LoopEvent[]>([]);
  const [assistantStatus, setAssistantStatus] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const streamingMsgRef = useRef<string>("");
  const messageSeqRef = useRef(1);

  const hasPendingChange = pendingChange !== null;
  const disableActions = shouldDisableChatActions(isStreaming, hasPendingChange);
  const visibleChatMessages = chatMessages.filter(isEditorVisibleMessage);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [visibleChatMessages, pendingChange, noOpReason, loopEvents]);

  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) setIsOpen(false);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  const pushLoopEvent = (event: LoopEvent) => {
    setLoopEvents((current) => [...current, event]);
  };

  const handleRollbackPending = () => {
    if (!pendingChange) return;
    const currentPresentation = useAppStore.getState().presentation;
    if (currentPresentation) {
      setPresentation({
        ...currentPresentation,
        slides: cloneSlides(pendingChange.previousSlides),
      });
    } else {
      updateSlides(cloneSlides(pendingChange.previousSlides));
    }
    setPresentationHtmlState(
      pendingChange.mode,
      pendingChange.previousHtml,
      useAppStore.getState().presentationHtmlArtifact
    );
    if (pendingChange.mode === "slidev") {
      setPresentationSlidevState({
        outputMode: "slidev",
        markdown: pendingChange.previousSlidevMarkdown ?? null,
        meta: pendingChange.previousSlidevMeta ?? null,
        deckArtifact: useAppStore.getState().presentationSlidevDeckArtifact,
        buildArtifact: useAppStore.getState().presentationSlidevBuildArtifact,
        buildUrl: pendingChange.previousSlidevBuildUrl ?? null,
      });
    }
    setPendingChange(null);
    const rollbackSeq = messageSeqRef.current++;
    addChatMessage({
      id: `msg-${rollbackSeq}-rollback`,
      role: "assistant",
      content: "已撤回上一次预览改稿，当前页面恢复为撤回前状态。",
      timestamp: rollbackSeq,
      phase: "editor",
      messageKind: "assistant_reply",
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
      if (pendingChange.mode === "html") {
        await saveLatestSessionHtmlPresentation(
          currentSessionId,
          latestPresentation,
          pendingChange.proposedHtml || "",
          "chat"
        );
      } else if (pendingChange.mode === "slidev") {
        await saveLatestSessionSlidevPresentation(
          currentSessionId,
          latestPresentation,
          pendingChange.proposedSlidevMarkdown || "",
          pendingChange.selectedStyleId ?? presentationSlidevDeckArtifact?.selected_style_id ?? null,
          pendingChange.proposedSlidevMeta ?? undefined,
          "chat"
        );
      } else {
        await saveLatestSessionPresentation(currentSessionId, latestPresentation, "chat");
      }
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
    setLoopEvents([]);
    setAssistantStatus("thinking");

    const userSeq = messageSeqRef.current++;
    addChatMessage({
      id: `msg-${userSeq}`,
      role: "user",
      content: text,
      timestamp: userSeq,
      phase: "editor",
      messageKind: "user_turn",
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
      phase: "editor",
      messageKind: "assistant_reply",
    });

    const currentMessages = useAppStore
      .getState()
      .chatMessages.filter(isEditorVisibleMessage);
    const historyForApi = buildHistoryForApi(currentMessages, replyId, text);

    await chatStream(
      {
        message: text,
        session_id: currentSessionId,
        messages: historyForApi,
        presentation_context: presentation
          ? {
              slides: presentation.slides,
              title: presentation.title,
              output_mode: presentationOutputMode,
              html_content: presentationOutputMode === "html" ? presentationHtml : undefined,
              slidev_markdown:
                presentationOutputMode === "slidev" ? presentationSlidevMarkdown : undefined,
              slidev_meta: presentationOutputMode === "slidev" ? presentationSlidevMeta : undefined,
              selected_style_id:
                presentationOutputMode === "slidev"
                  ? presentationSlidevDeckArtifact?.selected_style_id
                  : undefined,
            }
          : undefined,
        current_slide_index: currentSlideIndex,
        action_hint: actionHint,
        skill_id: defaultSkillIdForOutputMode(presentationOutputMode),
      },
      (chunk) => {
        streamingMsgRef.current = sanitizeAssistantText(`${streamingMsgRef.current}${chunk}`);
        useAppStore.setState((state) => ({
          chatMessages: state.chatMessages.map((msg) =>
            msg.id === replyId ? { ...msg, content: streamingMsgRef.current } : msg
          ),
        }));
      },
      () => {
        setIsStreaming(false);
      },
      (err) => {
        console.error("Chat error:", err);
        setAssistantStatus("error");
        pushLoopEvent({ type: "assistant_status", assistant_status: "error" });
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
        const currentHtml = useAppStore.getState().presentationHtml;
        const previousSlidesSnapshot = pendingChange?.previousSlides
          ? cloneSlides(pendingChange.previousSlides)
          : cloneSlides(currentSlides);
        updateSlides(slideUpdate.slides);
        setPendingChange({
          mode: "structured",
          previousSlides: previousSlidesSnapshot,
          proposedSlides: cloneSlides(slideUpdate.slides),
          previousHtml: currentHtml,
          proposedHtml: currentHtml,
          previousSlidevMarkdown: presentationSlidevMarkdown,
          proposedSlidevMarkdown: presentationSlidevMarkdown,
          previousSlidevMeta: presentationSlidevMeta,
          proposedSlidevMeta: presentationSlidevMeta,
          previousSlidevBuildUrl: presentationSlidevBuildUrl,
          proposedSlidevBuildUrl: presentationSlidevBuildUrl,
          modifications: slideUpdate.modifications,
          saving: false,
        });
        toast.info("已生成改稿预览，请确认应用或撤回");
      },
      (noOp) => {
        setNoOpReason(noOp.reason);
        toast.warning(noOp.reason);
      },
      (htmlUpdate) => {
        const currentSlides = useAppStore.getState().presentation?.slides ?? [];
        const currentHtml = useAppStore.getState().presentationHtml;
        const previousSlidesSnapshot = pendingChange?.previousSlides
          ? cloneSlides(pendingChange.previousSlides)
          : cloneSlides(currentSlides);
        setPresentation(htmlUpdate.presentation);
        setPresentationHtmlState(
          "html",
          htmlUpdate.html_content,
          useAppStore.getState().presentationHtmlArtifact
        );
        setPendingChange({
          mode: "html",
          previousSlides: previousSlidesSnapshot,
          proposedSlides: cloneSlides(htmlUpdate.presentation.slides),
          previousHtml: currentHtml,
          proposedHtml: htmlUpdate.html_content,
          previousSlidevMarkdown: presentationSlidevMarkdown,
          proposedSlidevMarkdown: presentationSlidevMarkdown,
          previousSlidevMeta: presentationSlidevMeta,
          proposedSlidevMeta: presentationSlidevMeta,
          previousSlidevBuildUrl: presentationSlidevBuildUrl,
          proposedSlidevBuildUrl: presentationSlidevBuildUrl,
          modifications: htmlUpdate.modifications || [],
          saving: false,
        });
        toast.info("已生成 HTML 改稿预览，请确认应用或撤回");
      },
      (slidevUpdate) => {
        const currentSlides = useAppStore.getState().presentation?.slides ?? [];
        const currentHtml = useAppStore.getState().presentationHtml;
        const previousSlidesSnapshot = pendingChange?.previousSlides
          ? cloneSlides(pendingChange.previousSlides)
          : cloneSlides(currentSlides);
        setPresentation(slidevUpdate.presentation);
        setPresentationSlidevState({
          outputMode: "slidev",
          markdown: slidevUpdate.markdown,
          meta: slidevUpdate.meta,
          deckArtifact: useAppStore.getState().presentationSlidevDeckArtifact,
          buildArtifact: useAppStore.getState().presentationSlidevBuildArtifact,
          buildUrl: slidevUpdate.preview_url,
        });
        setPendingChange({
          mode: "slidev",
          previousSlides: previousSlidesSnapshot,
          proposedSlides: cloneSlides(slidevUpdate.presentation.slides),
          previousHtml: currentHtml,
          proposedHtml: currentHtml,
          previousSlidevMarkdown: presentationSlidevMarkdown,
          proposedSlidevMarkdown: slidevUpdate.markdown,
          previousSlidevMeta: presentationSlidevMeta,
          proposedSlidevMeta: slidevUpdate.meta,
          previousSlidevBuildUrl: presentationSlidevBuildUrl,
          proposedSlidevBuildUrl: slidevUpdate.preview_url,
          selectedStyleId: slidevUpdate.selected_style_id ?? presentationSlidevDeckArtifact?.selected_style_id ?? null,
          modifications: slidevUpdate.modifications || [],
          saving: false,
        });
        toast.info("已生成 Slidev 改稿预览，请确认应用或撤回");
      },
      (event: ChatAssistantStatusEvent) => {
        setAssistantStatus(event.assistant_status);
        pushLoopEvent({ type: "assistant_status", assistant_status: event.assistant_status });
      },
      (event: ChatToolCallEvent) => {
        pushLoopEvent({ type: "tool_call", ...event });
      },
      (event: ChatToolResultEvent) => {
        pushLoopEvent({ type: "tool_result", ...event });
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
          <div className="fixed inset-0 z-40 bg-slate-950/18 md:bg-slate-950/8" onClick={() => setIsOpen(false)} />

          <div className="fixed inset-4 z-50 flex flex-col overflow-hidden rounded-[30px] border border-white/70 bg-white/66 shadow-[0_28px_80px_-48px_rgba(15,23,42,0.52)] backdrop-blur-2xl md:inset-y-4 md:right-4 md:left-auto md:w-[460px]">
            <div className="flex items-center justify-between border-b border-white/70 px-5 py-4">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-[18px] bg-cyan-50 text-cyan-700 ring-1 ring-white/80">
                  <Sparkles className="h-5 w-5" />
                </div>
                <div className="space-y-1">
                  <p className="text-base font-semibold text-slate-900">AI 助手</p>
                  <div className="inline-flex items-center gap-2 rounded-full border border-white/80 bg-white/72 px-2.5 py-1 text-xs font-medium text-slate-600">
                    {isStreaming && <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-600" />}
                    {!isStreaming && assistantStatus === "ready" && (
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                    )}
                    {!isStreaming && !assistantStatus && (
                      <MessageSquareMore className="h-3.5 w-3.5 text-slate-500" />
                    )}
                    <span>{renderStatusLabel(assistantStatus)}</span>
                  </div>
                </div>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="rounded-full p-2 text-slate-500 transition hover:bg-white/70 hover:text-slate-900"
                aria-label="关闭 AI 助手"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-4 pt-5">
              <div className="space-y-6">
                {visibleChatMessages.length === 0 && (
                  <div className="rounded-[24px] border border-white/70 bg-white/58 px-5 py-5 text-sm leading-7 text-slate-500">
                    输入你的修改意图，或者直接点下面的快捷操作。我会先理解当前页，再给出真实改稿预览。
                  </div>
                )}
                {visibleChatMessages.map((msg) => (
                  <MessageBubble key={msg.id} msg={msg} />
                ))}
                <div ref={messagesEndRef} />
              </div>
            </div>

            <div className="border-t border-white/70 px-5 py-4">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-slate-900">本轮执行过程</p>
                </div>
                <ProcessTimeline events={loopEvents} />
              </div>
            </div>

            {pendingChange && (
              <div className="border-t border-amber-200/90 bg-amber-50/85 px-5 py-3">
                <p className="text-sm text-amber-900">
                  已预览 {pendingChange.modifications.length} 处修改，是否应用到当前会话？
                </p>
                <div className="mt-3 flex gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      void handleApplyPending();
                    }}
                    disabled={pendingChange.saving || isStreaming}
                    className="inline-flex flex-1 items-center justify-center rounded-[18px] bg-amber-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-amber-700 disabled:opacity-50"
                  >
                    {pendingChange.saving ? "保存中..." : "应用并保存"}
                  </button>
                  <button
                    type="button"
                    onClick={handleRollbackPending}
                    disabled={pendingChange.saving}
                    className="inline-flex flex-1 items-center justify-center rounded-[18px] border border-amber-300 bg-white/80 px-4 py-2.5 text-sm font-medium text-amber-800 transition hover:bg-white disabled:opacity-50"
                  >
                    撤回
                  </button>
                </div>
              </div>
            )}

            {noOpReason && (
              <div className="border-t border-white/70 bg-slate-50/70 px-5 py-3">
                <p className="text-sm leading-6 text-slate-500">{noOpReason}</p>
              </div>
            )}

            <div className="border-t border-white/70 px-5 pb-5 pt-4">
              {showSkills && skills.length > 0 && (
                <div className="mb-3 max-h-32 overflow-y-auto rounded-[20px] border border-white/80 bg-white/76 shadow-[0_18px_40px_-34px_rgba(15,23,42,0.18)]">
                  {skills.map((skill) => (
                    <button
                      key={skill.name}
                      onClick={() => handleSkillSelect(skill.command || skill.name)}
                      className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm transition hover:bg-slate-50/80"
                    >
                      <span className="font-medium text-slate-800">/{skill.command || skill.name}</span>
                      <span className="truncate text-slate-500">{skill.description}</span>
                    </button>
                  ))}
                </div>
              )}

              <div className="rounded-[28px] border border-white/75 bg-white/62 px-4 py-3 shadow-[0_18px_40px_-34px_rgba(15,23,42,0.24)] backdrop-blur-xl">
                <div className="flex items-end gap-3">
                  <textarea
                    ref={inputRef}
                    className="min-h-[96px] flex-1 resize-none rounded-[20px] border border-transparent bg-transparent px-3 py-2 text-sm leading-7 text-slate-700 outline-none transition placeholder:text-slate-400 focus:border-slate-200 focus:bg-white/50"
                    placeholder={
                      hasPendingChange
                        ? "请先应用或撤回当前预览修改"
                        : "告诉我这一页想怎么改，或输入 / 触发 Skill..."
                    }
                    value={input}
                    onChange={(e) => handleInputChange(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleSend();
                      }
                    }}
                    disabled={disableActions}
                  />
                  <button
                    onClick={handleSend}
                    disabled={!input.trim() || disableActions}
                    className="inline-flex h-11 min-w-[88px] items-center justify-center rounded-[18px] bg-slate-900 px-5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    发送
                  </button>
                </div>
              </div>

              <div className="mt-4 space-y-3">
                {QUICK_ACTIONS.map((group) => (
                  <div key={group.category}>
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                      {group.category}
                    </p>
                    {group.description && (
                      <p className="mt-1 text-sm text-slate-500">{group.description}</p>
                    )}
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      {group.actions.map((action) => {
                        const Icon = action.icon;
                        return (
                          <button
                            key={action.label}
                            onClick={() => handleQuickAction(action)}
                            disabled={disableActions}
                            className="flex items-center gap-2 rounded-[18px] border border-white/80 bg-white/72 px-3 py-2.5 text-sm text-slate-600 shadow-[0_18px_40px_-34px_rgba(15,23,42,0.16)] transition hover:-translate-y-0.5 hover:bg-white hover:text-slate-900 disabled:opacity-50"
                          >
                            <Icon className="h-4 w-4 shrink-0" />
                            {action.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}

      <button
        onClick={() => setIsOpen((current) => !current)}
        className={cn(
          "fixed right-6 bottom-6 z-50 inline-flex h-14 w-14 items-center justify-center rounded-full shadow-[0_24px_64px_-36px_rgba(15,23,42,0.52)] transition hover:scale-[1.03]",
          isOpen ? "bg-white text-slate-600" : "bg-slate-900 text-white"
        )}
        aria-label="打开 AI 助手"
      >
        <Sparkles className="h-5 w-5" />
      </button>
    </>
  );
}

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { GripVertical, Loader2, Plus, Trash2, User } from "lucide-react";
import { toast } from "sonner";
import {
  confirmPlanning,
  planningTurnStream,
  updatePlanningOutline,
  type PlanningOutlineItem,
  type PlanningState,
} from "@/lib/api";
import { getSessionEditorPath } from "@/lib/routes";
import { cn } from "@/lib/utils";
import { useAppStore, type ChatMessage } from "@/lib/store";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

function buildOpeningMessage(): ChatMessage {
  return {
    id: "planning-opening",
    role: "assistant",
    content:
      "你想做一份什么样的演示？\n\n可以直接告诉我主题、受众、目标，或者先勾选左侧素材，我会先帮你把结构理顺，再整理成一版可确认的提纲。",
    timestamp: 0,
    phase: "planning",
    messageKind: "assistant_reply",
  };
}

function isPlanningMessage(msg: ChatMessage): boolean {
  return msg.phase === "planning";
}

function normalizeOutlineItems(items: PlanningOutlineItem[]): PlanningOutlineItem[] {
  return items.map((item, index) => ({
    ...item,
    slide_number: index + 1,
    title: item.title?.trim() || `第 ${index + 1} 页`,
    content_brief: item.content_brief ?? item.note ?? "",
    note: item.note ?? item.content_brief ?? "",
    key_points:
      Array.isArray(item.key_points) && item.key_points.length > 0
        ? item.key_points
        : [(item.note ?? item.content_brief ?? item.title ?? "").trim()].filter(Boolean),
    suggested_slide_role: item.suggested_slide_role || "narrative",
  }));
}

function formatUpdatedAt(value?: string | null): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function getGenerationStatusCopy(
  status: string,
  currentStage?: string | null
): { title: string; description: string } {
  if (status === "completed") {
    return {
      title: "演示初稿已经准备好了",
      description: "可以进入编辑器继续微调排版、文案和页面细节。",
    };
  }

  const stageCopy: Record<string, string> = {
    outline: "正在整理整体结构。",
    layout: "正在安排页面结构。",
    content: "正在生成页面内容。",
    review: "正在检查细节。",
    export: "正在收尾整理。",
  };

  return {
    title: "我开始制作这份演示了",
    description:
      currentStage && stageCopy[currentStage]
        ? stageCopy[currentStage]
        : "正在把这版提纲变成可继续编辑的演示初稿。",
  };
}

function ChatAvatar({ role }: { role: "assistant" | "user" }) {
  if (role === "assistant") {
    return (
      <Avatar size="lg" className="zy-chat-enter-avatar ring-1 ring-white/70">
        <AvatarFallback className="bg-[linear-gradient(135deg,rgba(var(--zy-brand-red),0.96),rgba(var(--zy-brand-blue),0.92))] text-sm font-semibold text-white">
          Z
        </AvatarFallback>
      </Avatar>
    );
  }

  return (
    <Avatar size="lg" className="zy-chat-enter-avatar ring-1 ring-white/70">
      <AvatarFallback className="bg-white/85 text-slate-600 shadow-[0_14px_28px_-22px_rgba(15,23,42,0.45)]">
        <User className="h-4 w-4" />
      </AvatarFallback>
    </Avatar>
  );
}

function TypingDots() {
  return (
    <span className="zy-chat-typing inline-flex items-center gap-1 align-middle">
      <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
      <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
      <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
    </span>
  );
}

function PlanningMessageRow({
  msg,
  isStreaming,
}: {
  msg: ChatMessage;
  isStreaming?: boolean;
}) {
  if (msg.role === "user") {
    return (
      <div className="zy-chat-enter-user flex justify-end">
        <div className="flex max-w-[82%] items-end gap-3">
          <div className="zy-chat-enter-body max-w-[640px] rounded-[24px] bg-white/72 px-5 py-4 text-sm leading-7 text-slate-700 shadow-[0_18px_40px_-34px_rgba(15,23,42,0.32)] backdrop-blur-sm">
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
          {msg.content ? (
            <p className="whitespace-pre-wrap">
              {msg.content}
              {isStreaming && (
                <>
                  {" "}
                  <TypingDots />
                </>
              )}
            </p>
          ) : (
            <TypingDots />
          )}
        </div>
      </div>
    </div>
  );
}

interface OutlineDraftBlockProps {
  items: PlanningOutlineItem[];
  outlineStale: boolean;
  savingOutline: boolean;
  confirming: boolean;
  onPatchItem: (index: number, patch: Partial<PlanningOutlineItem>) => void;
  onPersist: (items: PlanningOutlineItem[]) => Promise<boolean>;
  onMove: (from: number, to: number) => Promise<void>;
  onAdd: () => Promise<void>;
  onRemove: (index: number) => Promise<void>;
  onRefresh: () => Promise<void>;
  onConfirm: () => Promise<void>;
  onFocusComposer: () => void;
}

function OutlineDraftBlock({
  items,
  outlineStale,
  savingOutline,
  confirming,
  onPatchItem,
  onPersist,
  onMove,
  onAdd,
  onRemove,
  onRefresh,
  onConfirm,
  onFocusComposer,
}: OutlineDraftBlockProps) {
  const blockRef = useRef<HTMLDivElement>(null);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [draggingIndex, setDraggingIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const titleInputRefs = useRef<Array<HTMLInputElement | null>>([]);
  const noteInputRefs = useRef<Array<HTMLTextAreaElement | null>>([]);

  const focusField = (index: number, field: "title" | "note") => {
    requestAnimationFrame(() => {
      if (field === "note") {
        noteInputRefs.current[index]?.focus();
        return;
      }
      titleInputRefs.current[index]?.focus();
    });
  };

  const commitActiveEdit = useCallback(
    async (nextIndex?: number | null): Promise<boolean> => {
      if (activeIndex === null) {
        if (typeof nextIndex === "number") {
          setActiveIndex(nextIndex);
        }
        return true;
      }

      const ok = await onPersist(items);
      if (!ok) return false;
      setActiveIndex(nextIndex ?? null);
      return true;
    },
    [activeIndex, items, onPersist]
  );

  const activateItem = async (index: number, field: "title" | "note" = "title") => {
    if (activeIndex !== null && activeIndex !== index) {
      const ok = await commitActiveEdit(index);
      if (!ok) return;
      focusField(index, field);
      return;
    }

    setActiveIndex(index);
    focusField(index, field);
  };

  useEffect(() => {
    if (activeIndex === null) return;

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (!target) return;
      if (blockRef.current?.contains(target)) return;
      void commitActiveEdit();
    };

    document.addEventListener("pointerdown", handlePointerDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [activeIndex, commitActiveEdit]);

  return (
    <div ref={blockRef} className="zy-chat-enter-block space-y-6 border-t border-slate-200/70 pt-5">
      <div className="space-y-2">
        <p className="text-sm font-medium text-slate-900">这版演示结构</p>
        <p className="text-sm leading-6 text-slate-500">
          先看整体顺序，对的话我就继续往下制作；如果哪里不对，你也可以直接改这一页。
        </p>
      </div>

      {outlineStale && (
        <div className="space-y-3 border-l-2 border-amber-300/80 pl-4 text-sm leading-6 text-amber-900">
          <p>我看到你刚更新了素材，建议我先按最新内容刷新一下这版结构。</p>
          <button
            type="button"
            onClick={() => {
              void onRefresh();
            }}
            className="inline-flex rounded-full border border-amber-300 px-3 py-1.5 text-xs font-medium text-amber-900 transition hover:bg-amber-50"
          >
            按新素材刷新提纲
          </button>
        </div>
      )}

      <div className="relative">
        <div className="absolute bottom-0 left-[19px] top-0 w-px bg-[linear-gradient(180deg,rgba(148,163,184,0.18),rgba(148,163,184,0.04))]" />
        {items.map((item, index) => (
          <div
            key={`${item.slide_number}-${index}`}
            onDragOver={(event) => {
              if (draggingIndex === null) return;
              event.preventDefault();
              if (dragOverIndex !== index) {
                setDragOverIndex(index);
              }
            }}
            onDrop={(event) => {
              event.preventDefault();
              if (draggingIndex === null || draggingIndex === index) {
                setDraggingIndex(null);
                setDragOverIndex(null);
                return;
              }
              void onMove(draggingIndex, index);
              setDraggingIndex(null);
              setDragOverIndex(null);
            }}
            onDragEnd={() => {
              setDraggingIndex(null);
              setDragOverIndex(null);
            }}
            className={cn(
              "group relative grid grid-cols-[40px_minmax(0,1fr)_auto] gap-4 py-4 transition",
              index !== items.length - 1 && "border-b border-slate-200/60",
              activeIndex === index && "rounded-[22px] bg-white/46 px-3",
              draggingIndex === index && "opacity-60",
              dragOverIndex === index &&
                draggingIndex !== null &&
                draggingIndex !== index &&
                "rounded-[22px] bg-white/44 px-3 shadow-[inset_0_0_0_1px_rgba(148,163,184,0.22)]"
            )}
          >
            <div className="relative z-10 flex w-10 shrink-0 flex-col items-center pt-1.5 text-slate-400">
              <span className="flex h-7 w-7 items-center justify-center rounded-full border border-white/85 bg-white/92 text-[11px] font-semibold text-slate-600 shadow-[0_10px_22px_-18px_rgba(15,23,42,0.35)]">
                {index + 1}
              </span>
              <button
                type="button"
                draggable
                onDragStart={(event) => {
                  setDraggingIndex(index);
                  setDragOverIndex(index);
                  event.dataTransfer.effectAllowed = "move";
                  event.dataTransfer.setData("text/plain", String(index));
                }}
                className="mt-2 rounded-full p-1 text-slate-400 opacity-70 transition hover:bg-white/70 hover:text-slate-600 hover:opacity-100"
                aria-label={`拖动第 ${index + 1} 页排序`}
              >
                <GripVertical className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="min-w-0 flex-1 space-y-2 pt-0.5">
              {activeIndex === index ? (
                <>
                  <input
                    ref={(node) => {
                      titleInputRefs.current[index] = node;
                    }}
                    value={item.title}
                    onChange={(event) => onPatchItem(index, { title: event.target.value })}
                    className="w-full rounded-xl border border-slate-200/80 bg-white/75 px-3 py-2 text-[15px] font-semibold text-slate-900 outline-none transition focus:border-slate-300"
                  />
                  <textarea
                    ref={(node) => {
                      noteInputRefs.current[index] = node;
                    }}
                    value={item.note ?? item.content_brief ?? ""}
                    onChange={(event) =>
                      onPatchItem(index, {
                        note: event.target.value,
                        content_brief: event.target.value,
                      })
                    }
                    placeholder="这一页主要讲什么，希望观众记住什么。"
                    className="min-h-[72px] w-full rounded-xl border border-slate-200/80 bg-white/75 px-3 py-2 text-sm leading-6 text-slate-600 outline-none transition focus:border-slate-300"
                  />
                </>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => {
                      void activateItem(index, "title");
                    }}
                    className="block w-full text-left"
                  >
                    <span className="block text-[15px] font-semibold leading-7 text-slate-900 transition group-hover:text-slate-950">
                      {item.title}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      void activateItem(index, "note");
                    }}
                    className="block w-full text-left"
                  >
                    <span className="block overflow-hidden text-ellipsis whitespace-nowrap text-sm leading-6 text-slate-500 transition group-hover:text-slate-600">
                      {item.note?.trim() || item.content_brief?.trim() || "点击补充这一页的说明"}
                    </span>
                  </button>
                </>
              )}
            </div>
            <div
              className={cn(
                "flex items-center pt-1 opacity-0 transition",
                activeIndex === index ? "opacity-100" : "group-hover:opacity-100"
              )}
            >
              <button
                type="button"
                onClick={() => {
                  void onRemove(index);
                }}
                disabled={items.length <= 1 || savingOutline}
                className="rounded-full p-2 text-rose-400 transition hover:bg-rose-50 hover:text-rose-600 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => {
              void commitActiveEdit().then((ok) => {
                if (!ok) return;
                void onAdd();
              });
            }}
            disabled={savingOutline}
            className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-3.5 py-2 text-slate-600 transition hover:border-slate-300 hover:bg-white/70 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="h-3.5 w-3.5" />
            添加一页
          </button>
          <button
            type="button"
            onClick={() => {
              void commitActiveEdit().then((ok) => {
                if (!ok) return;
                onFocusComposer();
              });
            }}
            className="inline-flex items-center justify-center rounded-full border border-slate-200 px-4 py-2 text-slate-700 transition hover:border-slate-300 hover:bg-white/70 hover:text-slate-900"
          >
            继续调整
          </button>
        </div>
        <button
          type="button"
          onClick={() => {
            void commitActiveEdit().then((ok) => {
              if (!ok) return;
              void onConfirm();
            });
          }}
          disabled={outlineStale || items.length === 0 || savingOutline || confirming}
          className="inline-flex items-center justify-center gap-2 rounded-full bg-slate-900 px-4 py-2 text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {(confirming || savingOutline) && <Loader2 className="h-4 w-4 animate-spin" />}
          这版可以，开始生成
        </button>
      </div>
    </div>
  );
}

interface GenerationStatusBlockProps {
  status: string;
  currentStage?: string | null;
  sessionTitle: string;
  updatedAt?: string | null;
  onOpenEditor: () => void;
}

function GenerationStatusBlock({
  status,
  currentStage,
  sessionTitle,
  updatedAt,
  onOpenEditor,
}: GenerationStatusBlockProps) {
  const copy = getGenerationStatusCopy(status, currentStage);
  const updatedAtText = formatUpdatedAt(updatedAt);

  return (
    <div className="zy-chat-enter-block space-y-4 border-t border-slate-200/70 pt-5">
      <div className="space-y-2">
        <p className="text-sm font-medium text-slate-900">{copy.title}</p>
        <p className="text-sm leading-6 text-slate-600">{copy.description}</p>
      </div>
      <div className="text-sm leading-6 text-slate-500">
        <p className="text-slate-700">{sessionTitle}</p>
        {updatedAtText && <p>最近更新于 {updatedAtText}</p>}
      </div>
      <button
        type="button"
        onClick={onOpenEditor}
        className="inline-flex items-center justify-center rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800"
      >
        进入编辑器查看
      </button>
    </div>
  );
}

function AssistantBlock({
  children,
  animateClass = "zy-chat-enter-block",
}: {
  children: React.ReactNode;
  animateClass?: string;
}) {
  return (
    <div className={cn(animateClass, "flex justify-start")}>
      <div className="flex max-w-[92%] items-start gap-3">
        <ChatAvatar role="assistant" />
        <div className="min-w-0 flex-1 pt-1">{children}</div>
      </div>
    </div>
  );
}

export default function PlanningPanel() {
  const router = useRouter();
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const {
    chatMessages,
    currentSessionId,
    sessions,
    addChatMessage,
    planningState,
    setPlanningState,
    draftOutline,
    setDraftOutline,
    outlineStale,
    setOutlineStale,
    activeGenerationCard,
    setActiveGenerationCard,
    updateJobState,
    setIsGenerating,
  } = useAppStore();
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [savingOutline, setSavingOutline] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [streamingReplyId, setStreamingReplyId] = useState<string | null>(null);
  const messageSeqRef = useRef(1);

  const planningMessages = useMemo(() => {
    const items = chatMessages.filter(isPlanningMessage);
    return items.length > 0 ? items : [buildOpeningMessage()];
  }, [chatMessages]);

  const currentSessionTitle =
    sessions.find((session) => session.id === currentSessionId)?.title || "未命名会话";
  const generationCard = activeGenerationCard;
  const effectiveStatus = planningState?.status ?? "collecting_requirements";
  const isGeneratingPhase =
    effectiveStatus === "generating" || effectiveStatus === "completed";

  const updateMessageContent = (messageId: string, updater: (content: string) => string) => {
    useAppStore.setState((state) => ({
      chatMessages: state.chatMessages.map((msg) =>
        msg.id === messageId ? { ...msg, content: updater(msg.content) } : msg
      ),
    }));
  };

  const sendPlanningMessage = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || !currentSessionId || isStreaming) return;

    const userSeq = messageSeqRef.current++;
    const userId = `planning-user-${userSeq}`;
    addChatMessage({
      id: userId,
      role: "user",
      content: trimmed,
      timestamp: Date.now(),
      phase: "planning",
      messageKind: "user_turn",
      outlineVersion: planningState?.outline_version ?? null,
    });

    const replySeq = messageSeqRef.current++;
    const replyId = `planning-assistant-${replySeq}`;
    addChatMessage({
      id: replyId,
      role: "assistant",
      content: "",
      timestamp: Date.now() + 1,
      phase: "planning",
      messageKind: "assistant_reply",
      outlineVersion: planningState?.outline_version ?? null,
    });

    setStreamingReplyId(replyId);
    setInput("");
    setIsStreaming(true);
    await planningTurnStream(
      currentSessionId,
      trimmed,
      (event) => {
        if (event.type === "text") {
          const chunk = typeof event.content === "string" ? event.content : "";
          updateMessageContent(replyId, (current) => current + chunk);
          return;
        }
        if (
          (event.type === "outline_drafted" || event.type === "outline_revised") &&
          event.outline &&
          typeof event.outline === "object"
        ) {
          const nextItems = Array.isArray((event.outline as { items?: PlanningOutlineItem[] }).items)
            ? ((event.outline as { items?: PlanningOutlineItem[] }).items as PlanningOutlineItem[])
            : [];
          setDraftOutline(normalizeOutlineItems(nextItems));
          setOutlineStale(false);
          return;
        }
        if (event.type === "planning_state" && event.planning_state) {
          setPlanningState(event.planning_state as PlanningState);
          return;
        }
        if (event.type === "error") {
          const content =
            typeof event.content === "string" ? event.content : "我刚刚整理需求时出了点问题";
          updateMessageContent(replyId, () => content);
          toast.error(content);
        }
      },
      () => {
        setIsStreaming(false);
        setStreamingReplyId(null);
      },
      (err) => {
        updateMessageContent(replyId, () => `刚刚没有成功处理这条消息：${err.message}`);
        setIsStreaming(false);
        setStreamingReplyId(null);
      }
    );
  };

  const persistOutline = async (items: PlanningOutlineItem[]) => {
    if (!currentSessionId) return false;
    const normalizedItems = normalizeOutlineItems(items);
    setSavingOutline(true);
    setDraftOutline(normalizedItems);
    try {
      const nextState = await updatePlanningOutline(currentSessionId, {
        narrative_arc: planningState?.outline?.narrative_arc || "问题→分析→方案→结论",
        items: normalizedItems,
      });
      setPlanningState(nextState);
      setOutlineStale(false);
      return true;
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存提纲失败");
      return false;
    } finally {
      setSavingOutline(false);
    }
  };

  const patchOutlineItem = (index: number, patch: Partial<PlanningOutlineItem>) => {
    const next = draftOutline.map((item, itemIndex) =>
      itemIndex === index ? { ...item, ...patch } : item
    );
    setDraftOutline(normalizeOutlineItems(next));
  };

  const moveOutlineItem = async (from: number, to: number) => {
    if (to < 0 || to >= draftOutline.length || from === to) return;
    const next = [...draftOutline];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    await persistOutline(next);
  };

  const addOutlineItem = async () => {
    const next = [
      ...draftOutline,
      {
        slide_number: draftOutline.length + 1,
        title: `新增页面 ${draftOutline.length + 1}`,
        note: "",
        content_brief: "",
        key_points: ["待补充"],
        suggested_slide_role: "narrative",
      },
    ];
    await persistOutline(next);
  };

  const removeOutlineItem = async (index: number) => {
    const next = draftOutline.filter((_, itemIndex) => itemIndex !== index);
    await persistOutline(next.length > 0 ? next : []);
  };

  const handleConfirm = async () => {
    if (!currentSessionId || outlineStale || draftOutline.length === 0 || confirming) return;
    setConfirming(true);
    try {
      const result = await confirmPlanning(currentSessionId);
      setPlanningState(result.planning_state);
      setActiveGenerationCard({
        jobId: result.job_id,
        status: result.status,
        currentStage: result.current_stage,
        sessionTitle: currentSessionTitle,
        updatedAt: result.planning_state.updated_at,
      });
      updateJobState({
        jobId: result.job_id,
        jobStatus: result.status,
        currentStage: result.current_stage,
        failedSlideIndices: [],
        hardIssueSlideIds: [],
        advisoryIssueCount: 0,
      });
      setIsGenerating(result.status === "running");
      toast.success("我开始制作这份演示了");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "确认提纲失败");
    } finally {
      setConfirming(false);
    }
  };

  const openEditor = () => {
    if (!currentSessionId) return;
    router.push(getSessionEditorPath(currentSessionId));
  };

  return (
    <div className="flex min-w-0 min-h-0 flex-1 flex-col overflow-hidden">
      <div className="min-h-0 flex-1 overflow-y-auto px-8 pb-6 pt-10 lg:px-12">
        <div className="mx-auto flex w-full max-w-[880px] flex-col gap-7">
          {planningMessages.map((msg) => (
            <PlanningMessageRow
              key={msg.id}
              msg={msg}
              isStreaming={Boolean(isStreaming && streamingReplyId === msg.id)}
            />
          ))}

          {draftOutline.length > 0 && !isGeneratingPhase && (
            <AssistantBlock>
              <OutlineDraftBlock
                items={draftOutline}
                outlineStale={outlineStale}
                savingOutline={savingOutline}
                confirming={confirming}
                onPatchItem={patchOutlineItem}
                onPersist={persistOutline}
                onMove={moveOutlineItem}
                onAdd={addOutlineItem}
                onRemove={removeOutlineItem}
                onRefresh={() => sendPlanningMessage("请根据我刚更新的素材，重新整理一版提纲。")}
                onConfirm={handleConfirm}
                onFocusComposer={() => composerRef.current?.focus()}
              />
            </AssistantBlock>
          )}

          {generationCard && isGeneratingPhase && (
            <AssistantBlock>
              <GenerationStatusBlock
                status={generationCard.status}
                currentStage={generationCard.currentStage}
                sessionTitle={generationCard.sessionTitle}
                updatedAt={generationCard.updatedAt}
                onOpenEditor={openEditor}
              />
            </AssistantBlock>
          )}
        </div>
      </div>

      {!isGeneratingPhase && (
        <div className="shrink-0 border-t border-white/60 px-8 pb-7 pt-4 lg:px-12">
          <div className="mx-auto max-w-[880px]">
            <div className="flex items-end gap-3 rounded-[28px] border border-white/75 bg-white/62 px-4 py-3 shadow-[0_18px_40px_-34px_rgba(15,23,42,0.24)] backdrop-blur-xl">
              <textarea
                ref={composerRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder={
                  draftOutline.length > 0
                    ? "继续告诉我这一版结构哪里还要调整..."
                    : "比如：我想做一份给客户看的 AI 产品方案演示，重点讲价值、案例和落地路径。"
                }
                className={cn(
                  "min-h-[92px] flex-1 resize-none rounded-[20px] border border-transparent bg-transparent px-3 py-2 text-sm leading-7 text-slate-700 outline-none transition placeholder:text-slate-400 focus:border-slate-200 focus:bg-white/50"
                )}
              />
              <button
                type="button"
                onClick={() => {
                  void sendPlanningMessage(input);
                }}
                disabled={!input.trim() || isStreaming}
                className="inline-flex h-11 min-w-[88px] items-center justify-center rounded-[18px] bg-slate-900 px-5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isStreaming ? <Loader2 className="h-4 w-4 animate-spin" /> : "发送"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

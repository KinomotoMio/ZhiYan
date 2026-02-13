import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Presentation, Slide } from "@/types/slide";
import type { SourceMeta } from "@/types/source";
import type { SessionSummary, WorkspaceId } from "@/lib/api";

export interface OutlineItem {
  slide_number: number;
  title: string;
  suggested_layout_category: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

interface AppState {
  // Workspace + Session
  workspaceId: WorkspaceId;
  sessions: SessionSummary[];
  currentSessionId: string | null;

  // 编辑器状态
  presentation: Presentation | null;
  currentSlideIndex: number;
  isGenerating: boolean;
  jobId: string | null;
  jobStatus: string | null;
  currentStage: string | null;
  issues: Array<Record<string, unknown>>;
  failedSlideIndices: number[];
  chatMessages: ChatMessage[];

  // 创建视图状态
  sources: SourceMeta[];
  selectedSourceIds: string[];
  topic: string;
  selectedTemplateId: string;
  numPages: number;

  // Session actions
  setWorkspaceId: (id: WorkspaceId) => void;
  setSessions: (sessions: SessionSummary[]) => void;
  upsertSession: (session: SessionSummary) => void;
  removeSessionEntry: (sessionId: string) => void;
  setCurrentSessionId: (id: string | null) => void;
  setSessionData: (payload: {
    sources: SourceMeta[];
    chatMessages: ChatMessage[];
    presentation: Presentation | null;
  }) => void;

  // 编辑器 actions
  setPresentation: (p: Presentation | null) => void;
  updateSlides: (slides: Slide[]) => void;
  setCurrentSlideIndex: (i: number) => void;
  setIsGenerating: (v: boolean) => void;
  updateJobState: (patch: {
    jobId?: string | null;
    jobStatus?: string | null;
    currentStage?: string | null;
    issues?: Array<Record<string, unknown>>;
    failedSlideIndices?: number[];
  }) => void;
  resetJobState: () => void;
  addChatMessage: (msg: ChatMessage) => void;
  setChatMessages: (messages: ChatMessage[]) => void;
  getCurrentSlide: () => Slide | null;

  // 渐进式生成 actions
  initSkeletonPresentation: (title: string, outlineItems: OutlineItem[]) => void;
  updateSlideAtIndex: (index: number, slide: Slide) => void;
  finishGeneration: () => void;

  // 创建视图 actions
  addSource: (source: SourceMeta) => void;
  setSources: (sources: SourceMeta[]) => void;
  updateSource: (id: string, patch: Partial<SourceMeta>) => void;
  removeSource: (id: string) => void;
  clearSources: () => void;
  toggleSourceSelection: (id: string) => void;
  selectAllSources: () => void;
  deselectAllSources: () => void;
  setTopic: (topic: string) => void;
  setSelectedTemplateId: (id: string) => void;
  setNumPages: (n: number) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      // Workspace + Session
      workspaceId: "workspace-local-default",
      sessions: [],
      currentSessionId: null,

      // 编辑器状态
      presentation: null,
      currentSlideIndex: 0,
      isGenerating: false,
      jobId: null,
      jobStatus: null,
      currentStage: null,
      issues: [],
      failedSlideIndices: [],
      chatMessages: [],

      // 创建视图状态
      sources: [],
      selectedSourceIds: [],
      topic: "",
      selectedTemplateId: "default",
      numPages: 5,

      // Session actions
      setWorkspaceId: (id) => set({ workspaceId: id }),
      setSessions: (sessions) => set({ sessions }),
      upsertSession: (session) =>
        set((state) => {
          const exists = state.sessions.some((s) => s.id === session.id);
          const next = exists
            ? state.sessions.map((s) => (s.id === session.id ? session : s))
            : [session, ...state.sessions];
          next.sort((a, b) => {
            if (a.is_pinned !== b.is_pinned) return a.is_pinned ? -1 : 1;
            return b.updated_at.localeCompare(a.updated_at);
          });
          return { sessions: next };
        }),
      removeSessionEntry: (sessionId) =>
        set((state) => ({
          sessions: state.sessions.filter((s) => s.id !== sessionId),
          currentSessionId:
            state.currentSessionId === sessionId ? null : state.currentSessionId,
        })),
      setCurrentSessionId: (id) => set({ currentSessionId: id }),
      setSessionData: ({ sources, chatMessages, presentation }) =>
        set({
          sources,
          selectedSourceIds: sources
            .filter((s) => s.status === "ready")
            .map((s) => s.id),
          chatMessages,
          presentation,
          currentSlideIndex: 0,
        }),

      // 编辑器 actions
      setPresentation: (p) => set({ presentation: p }),
      updateSlides: (slides) =>
        set((state) => {
          if (!state.presentation) return {};
          return {
            presentation: { ...state.presentation, slides },
            currentSlideIndex: Math.min(
              state.currentSlideIndex,
              Math.max(0, slides.length - 1)
            ),
          };
        }),
      setCurrentSlideIndex: (i) => set({ currentSlideIndex: i }),
      setIsGenerating: (v) => set({ isGenerating: v }),
      updateJobState: (patch) =>
        set((state) => ({
          jobId: patch.jobId ?? state.jobId,
          jobStatus: patch.jobStatus ?? state.jobStatus,
          currentStage: patch.currentStage ?? state.currentStage,
          issues: patch.issues ?? state.issues,
          failedSlideIndices: patch.failedSlideIndices ?? state.failedSlideIndices,
        })),
      resetJobState: () =>
        set({
          jobId: null,
          jobStatus: null,
          currentStage: null,
          issues: [],
          failedSlideIndices: [],
        }),
      addChatMessage: (msg) =>
        set((state) => ({ chatMessages: [...state.chatMessages, msg] })),
      setChatMessages: (messages) => set({ chatMessages: messages }),

      getCurrentSlide: () => {
        const { presentation, currentSlideIndex } = get();
        return presentation?.slides[currentSlideIndex] ?? null;
      },

      // 渐进式生成 actions
      initSkeletonPresentation: (title, outlineItems) => {
        const skeletonSlides: Slide[] = outlineItems.map((item) => ({
          slideId: `slide-${item.slide_number}`,
          layoutType: "blank" as Slide["layoutType"],
          layoutId: undefined,
          contentData: { title: item.title, _loading: true },
          components: [],
        }));
        set({
          presentation: {
            presentationId: "pres-skeleton",
            title,
            slides: skeletonSlides,
          },
          currentSlideIndex: 0,
          isGenerating: true,
        });
      },

      updateSlideAtIndex: (index, slide) =>
        set((state) => {
          if (!state.presentation) return {};
          const slides = [...state.presentation.slides];
          if (index >= 0 && index < slides.length) {
            slides[index] = slide;
          }
          return { presentation: { ...state.presentation, slides } };
        }),

      finishGeneration: () => set({ isGenerating: false }),

      // 创建视图 actions
      addSource: (source) =>
        set((state) => ({
          sources: [source, ...state.sources],
          selectedSourceIds:
            source.status === "ready"
              ? [...state.selectedSourceIds, source.id]
              : state.selectedSourceIds,
        })),
      setSources: (sources) =>
        set({
          sources,
          selectedSourceIds: sources
            .filter((s) => s.status === "ready")
            .map((s) => s.id),
        }),
      updateSource: (id, patch) =>
        set((state) => {
          const newSources = state.sources.map((s) =>
            s.id === id ? { ...s, ...patch } : s
          );
          const becameReady =
            patch.status === "ready" && !state.selectedSourceIds.includes(id);
          return {
            sources: newSources,
            selectedSourceIds: becameReady
              ? [...state.selectedSourceIds, id]
              : state.selectedSourceIds,
          };
        }),
      removeSource: (id) =>
        set((state) => ({
          sources: state.sources.filter((s) => s.id !== id),
          selectedSourceIds: state.selectedSourceIds.filter((sid) => sid !== id),
        })),
      clearSources: () => set({ sources: [], selectedSourceIds: [] }),
      toggleSourceSelection: (id) =>
        set((state) => ({
          selectedSourceIds: state.selectedSourceIds.includes(id)
            ? state.selectedSourceIds.filter((sid) => sid !== id)
            : [...state.selectedSourceIds, id],
        })),
      selectAllSources: () =>
        set((state) => ({
          selectedSourceIds: state.sources
            .filter((s) => s.status === "ready")
            .map((s) => s.id),
        })),
      deselectAllSources: () => set({ selectedSourceIds: [] }),
      setTopic: (topic) => set({ topic }),
      setSelectedTemplateId: (id) => set({ selectedTemplateId: id }),
      setNumPages: (n) => set({ numPages: n }),
    }),
    {
      name: "zhiyan-store",
      partialize: (state) => ({
        workspaceId: state.workspaceId,
        currentSessionId: state.currentSessionId,
        topic: state.topic,
        selectedTemplateId: state.selectedTemplateId,
        numPages: state.numPages,
      }),
    }
  )
);

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Presentation, Slide } from "@/types/slide";
import type { SourceMeta } from "@/types/source";
import type { SessionSummary, WorkspaceId } from "@/lib/api";
import {
  buildShellSlides,
  mergeGeneratedSlide,
  mergeOutlineTitles,
  type OutlineTitleItem,
} from "@/components/generation/presentation-shell";

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
  lastJobEventSeq: number;
  issues: Array<Record<string, unknown>>;
  failedSlideIndices: number[];
  chatMessages: ChatMessage[];

  // 创建视图状态
  workspaceSources: SourceMeta[];
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
    lastJobEventSeq?: number;
    issues?: Array<Record<string, unknown>>;
    failedSlideIndices?: number[];
  }) => void;
  resetJobState: () => void;
  addChatMessage: (msg: ChatMessage) => void;
  setChatMessages: (messages: ChatMessage[]) => void;
  getCurrentSlide: () => Slide | null;

  // 渐进式生成 actions
  initGenerationShell: (title: string, pageCount: number) => void;
  setPresentationTitle: (title: string) => void;
  patchSlideTitlesFromOutline: (items: OutlineTitleItem[]) => void;
  initSkeletonPresentation: (title: string, outlineItems: OutlineItem[]) => void;
  updateSlideAtIndex: (index: number, slide: Slide) => void;
  finishGeneration: () => void;

  // 创建视图 actions
  setWorkspaceSources: (sources: SourceMeta[]) => void;
  addWorkspaceSource: (source: SourceMeta) => void;
  updateWorkspaceSource: (id: string, patch: Partial<SourceMeta>) => void;
  removeWorkspaceSource: (id: string) => void;
  clearWorkspaceSources: () => void;
  addSelectedSource: (id: string) => void;
  removeSelectedSource: (id: string) => void;
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
      lastJobEventSeq: 0,
      issues: [],
      failedSlideIndices: [],
      chatMessages: [],

      // 创建视图状态
      workspaceSources: [],
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
          lastJobEventSeq: patch.lastJobEventSeq ?? state.lastJobEventSeq,
          issues: patch.issues ?? state.issues,
          failedSlideIndices: patch.failedSlideIndices ?? state.failedSlideIndices,
        })),
      resetJobState: () =>
        set({
          jobId: null,
          jobStatus: null,
          currentStage: null,
          lastJobEventSeq: 0,
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
      initGenerationShell: (title, pageCount) =>
        set((state) => {
          const safeTitle = title.trim() || "生成中...";
          const currentPresentationId =
            state.presentation?.presentationId || "pres-skeleton";
          return {
            presentation: {
              presentationId: currentPresentationId,
              title: safeTitle,
              slides: buildShellSlides(pageCount, safeTitle),
            },
            currentSlideIndex: 0,
            isGenerating: true,
          };
        }),
      setPresentationTitle: (title) =>
        set((state) => {
          if (!state.presentation) return {};
          const safeTitle = title.trim();
          if (!safeTitle) return {};
          return {
            presentation: {
              ...state.presentation,
              title: safeTitle,
            },
          };
        }),
      patchSlideTitlesFromOutline: (items) =>
        set((state) => {
          if (!state.presentation) return {};
          return {
            presentation: {
              ...state.presentation,
              slides: mergeOutlineTitles(state.presentation.slides, items),
            },
          };
        }),
      initSkeletonPresentation: (title, outlineItems) => {
        const skeletonSlides = mergeOutlineTitles(
          buildShellSlides(outlineItems.length, title),
          outlineItems.map((item) => ({
            slide_number: item.slide_number,
            title: item.title,
          }))
        );
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
          return {
            presentation: {
              ...state.presentation,
              slides: mergeGeneratedSlide(state.presentation.slides, index, slide),
            },
          };
        }),

      finishGeneration: () => set({ isGenerating: false }),

      // 创建视图 actions
      setWorkspaceSources: (workspaceSources) => set({ workspaceSources }),
      addWorkspaceSource: (source) =>
        set((state) => ({
          workspaceSources: [source, ...state.workspaceSources],
          selectedSourceIds:
            source.status === "ready"
              ? [...state.selectedSourceIds, source.id]
              : state.selectedSourceIds,
        })),
      updateWorkspaceSource: (id, patch) =>
        set((state) => {
          const newSources = state.workspaceSources.map((s) =>
            s.id === id ? { ...s, ...patch } : s
          );
          const becameReady =
            patch.status === "ready" && !state.selectedSourceIds.includes(id);
          return {
            workspaceSources: newSources,
            selectedSourceIds: becameReady
              ? [...state.selectedSourceIds, id]
              : state.selectedSourceIds,
          };
        }),
      removeWorkspaceSource: (id) =>
        set((state) => ({
          workspaceSources: state.workspaceSources.filter((s) => s.id !== id),
          selectedSourceIds: state.selectedSourceIds.filter((sid) => sid !== id),
        })),
      clearWorkspaceSources: () => set({ workspaceSources: [], selectedSourceIds: [] }),
      addSelectedSource: (id) =>
        set((state) => ({
          selectedSourceIds: state.selectedSourceIds.includes(id)
            ? state.selectedSourceIds
            : [...state.selectedSourceIds, id],
        })),
      removeSelectedSource: (id) =>
        set((state) => ({
          selectedSourceIds: state.selectedSourceIds.filter((sid) => sid !== id),
        })),
      toggleSourceSelection: (id) =>
        set((state) => ({
          selectedSourceIds: state.selectedSourceIds.includes(id)
            ? state.selectedSourceIds.filter((sid) => sid !== id)
            : [...state.selectedSourceIds, id],
        })),
      selectAllSources: () =>
        set((state) => ({
          selectedSourceIds: state.workspaceSources
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

import { create } from "zustand";
import type { Presentation, Slide } from "@/types/slide";
import type { SourceMeta } from "@/types/source";

interface AppState {
  // 编辑器状态
  presentation: Presentation | null;
  currentSlideIndex: number;
  isGenerating: boolean;
  chatMessages: ChatMessage[];

  // 创建视图状态
  sources: SourceMeta[];
  selectedSourceIds: string[];
  topic: string;
  selectedTemplateId: string;
  numPages: number;

  // 编辑器 actions
  setPresentation: (p: Presentation) => void;
  setCurrentSlideIndex: (i: number) => void;
  setIsGenerating: (v: boolean) => void;
  addChatMessage: (msg: ChatMessage) => void;
  getCurrentSlide: () => Slide | null;

  // 创建视图 actions
  addSource: (source: SourceMeta) => void;
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

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

export const useAppStore = create<AppState>((set, get) => ({
  // 编辑器状态
  presentation: null,
  currentSlideIndex: 0,
  isGenerating: false,
  chatMessages: [],

  // 创建视图状态
  sources: [],
  selectedSourceIds: [],
  topic: "",
  selectedTemplateId: "default",
  numPages: 5,

  // 编辑器 actions
  setPresentation: (p) => set({ presentation: p }),
  setCurrentSlideIndex: (i) => set({ currentSlideIndex: i }),
  setIsGenerating: (v) => set({ isGenerating: v }),
  addChatMessage: (msg) =>
    set((state) => ({ chatMessages: [...state.chatMessages, msg] })),

  getCurrentSlide: () => {
    const { presentation, currentSlideIndex } = get();
    return presentation?.slides[currentSlideIndex] ?? null;
  },

  // 创建视图 actions
  addSource: (source) =>
    set((state) => ({
      sources: [...state.sources, source],
      selectedSourceIds: source.status === "ready"
        ? [...state.selectedSourceIds, source.id]
        : state.selectedSourceIds,
    })),
  updateSource: (id, patch) =>
    set((state) => {
      const newSources = state.sources.map((s) =>
        s.id === id ? { ...s, ...patch } : s
      );
      // 如果状态变为 ready，自动勾选
      const becameReady = patch.status === "ready" && !state.selectedSourceIds.includes(id);
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
}));

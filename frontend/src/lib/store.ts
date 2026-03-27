import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Presentation, Slide } from "@/types/slide";
import type { SourceMeta } from "@/types/source";
import type {
  PlanningOutlineItem,
  PlanningState,
  SessionSummary,
  WorkspaceId,
} from "@/lib/api";
import type { LayoutRole } from "@/lib/layout-role";
import { compactLoadingTitle, DEFAULT_LOADING_TITLE } from "@/lib/loading-title";
import type { IssueDecisionStatus } from "@/lib/verification-issues";
import {
  buildShellSlides,
  mergeGeneratedSlide,
  mergeOutlineTitles,
  type OutlineTitleItem,
} from "@/components/generation/presentation-shell";
import {
  getSessionTopicDraft,
  migrateLegacyTopicDraftState,
  removeSessionTopicDraft,
  setSessionTopicDraft,
  type SessionTopicDrafts,
} from "@/lib/session-topic-drafts";
import { compareUpdatedAt } from "@/lib/sort";

function shouldSyncGeneratedSessionTitle(
  session: SessionSummary | undefined,
): boolean {
  if (!session) return false;
  return !session.title_edited_by_user;
}

export interface OutlineItem {
  slide_number: number;
  title: string;
  suggested_slide_role: LayoutRole;
  // Legacy compatibility for persisted local state or older API payloads.
  suggested_layout_category?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  phase?: "planning" | "editor" | "generation" | string;
  messageKind?: string;
  outlineVersion?: number | null;
  jobId?: string | null;
}

export interface GenerationCardState {
  jobId: string;
  status: string;
  currentStage: string | null;
  sessionTitle: string;
  updatedAt: string | null;
}

interface AppState {
  // Workspace + Session
  workspaceId: WorkspaceId;
  sessions: SessionSummary[];
  currentSessionId: string | null;

  // Editor state
  presentation: Presentation | null;
  currentSlideIndex: number;
  isGenerating: boolean;
  jobId: string | null;
  jobStatus: string | null;
  currentStage: string | null;
  lastJobEventSeq: number;
  issues: Array<Record<string, unknown>>;
  failedSlideIndices: number[];
  hardIssueSlideIds: string[];
  advisoryIssueCount: number;
  fixPreviewSlides: Slide[];
  fixPreviewSourceIds: string[];
  selectedFixPreviewSlideIds: string[];
  issuePanelOpen: boolean;
  issuePanelSlideId: string | null;
  issueDecisionBySlideId: Record<string, IssueDecisionStatus>;
  chatMessages: ChatMessage[];
  planningState: PlanningState | null;
  draftOutline: PlanningOutlineItem[];
  outlineStale: boolean;
  activeGenerationCard: GenerationCardState | null;

  // Create view state
  workspaceSources: SourceMeta[];
  selectedSourceIds: string[];
  topic: string;
  sessionTopicDrafts: SessionTopicDrafts;
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
    planningState?: PlanningState | null;
  }) => void;

  // Editor actions
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
    hardIssueSlideIds?: string[];
    advisoryIssueCount?: number;
    fixPreviewSlides?: Slide[];
    fixPreviewSourceIds?: string[];
    selectedFixPreviewSlideIds?: string[];
  }) => void;
  resetJobState: () => void;
  setFixPreviewSelection: (slideIds: string[]) => void;
  toggleFixPreviewSelection: (slideId: string) => void;
  setIssuePanelOpen: (open: boolean) => void;
  openIssuePanelForSlide: (slideId: string | null) => void;
  setIssueDecision: (slideId: string, status: IssueDecisionStatus) => void;
  markSlidesProcessed: (slideIds: string[], status: Exclude<IssueDecisionStatus, "pending">) => void;
  resetIssueReviewState: () => void;
  clearFixReviewState: () => void;
  addChatMessage: (msg: ChatMessage) => void;
  setChatMessages: (messages: ChatMessage[]) => void;
  setPlanningState: (planningState: PlanningState | null) => void;
  setDraftOutline: (items: PlanningOutlineItem[]) => void;
  setOutlineStale: (value: boolean) => void;
  setActiveGenerationCard: (card: GenerationCardState | null) => void;
  getCurrentSlide: () => Slide | null;

  // Progressive generation actions
  initGenerationShell: (title: string, pageCount: number) => void;
  setPresentationTitle: (title: string) => void;
  patchSlideTitlesFromOutline: (items: OutlineTitleItem[]) => void;
  initSkeletonPresentation: (title: string, outlineItems: OutlineItem[]) => void;
  updateSlideAtIndex: (index: number, slide: Slide) => void;
  finishGeneration: () => void;

  // Create view actions
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

      // Editor state
      presentation: null,
      currentSlideIndex: 0,
      isGenerating: false,
      jobId: null,
      jobStatus: null,
      currentStage: null,
      lastJobEventSeq: 0,
      issues: [],
      failedSlideIndices: [],
      hardIssueSlideIds: [],
      advisoryIssueCount: 0,
      fixPreviewSlides: [],
      fixPreviewSourceIds: [],
      selectedFixPreviewSlideIds: [],
      issuePanelOpen: false,
      issuePanelSlideId: null,
      issueDecisionBySlideId: {},
      chatMessages: [],
      planningState: null,
      draftOutline: [],
      outlineStale: false,
      activeGenerationCard: null,

      // Create view state
      workspaceSources: [],
      selectedSourceIds: [],
      topic: "",
      sessionTopicDrafts: {},
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
            return compareUpdatedAt(a.updated_at, b.updated_at);
          });
          return { sessions: next };
        }),
      removeSessionEntry: (sessionId) =>
        set((state) => {
          const nextCurrentSessionId =
            state.currentSessionId === sessionId ? null : state.currentSessionId;
          const nextSessionTopicDrafts = removeSessionTopicDraft(
            state.sessionTopicDrafts,
            sessionId
          );
          return {
            sessions: state.sessions.filter((s) => s.id !== sessionId),
            currentSessionId: nextCurrentSessionId,
            sessionTopicDrafts: nextSessionTopicDrafts,
            topic: getSessionTopicDraft(nextSessionTopicDrafts, nextCurrentSessionId),
          };
        }),
      setCurrentSessionId: (id) =>
        set((state) => ({
          currentSessionId: id,
          topic: getSessionTopicDraft(state.sessionTopicDrafts, id),
        })),
      setSessionData: ({ sources, chatMessages, presentation, planningState }) =>
        set((state) => ({
          selectedSourceIds: sources
            .filter((s) => s.status === "ready")
            .map((s) => s.id),
          topic: getSessionTopicDraft(
            state.sessionTopicDrafts,
            state.currentSessionId
          ),
          chatMessages,
          presentation,
          planningState: planningState ?? null,
          draftOutline: Array.isArray(planningState?.outline?.items)
            ? planningState.outline.items
            : [],
          outlineStale: Boolean(planningState?.outline_stale),
          activeGenerationCard:
            planningState?.active_job_id && state.currentSessionId
              ? {
                  jobId: planningState.active_job_id,
                  status: planningState.status,
                  currentStage: state.currentStage,
                  sessionTitle:
                    state.sessions.find((session) => session.id === state.currentSessionId)
                      ?.title || "未命名会话",
                  updatedAt: planningState.updated_at || null,
                }
              : null,
          currentSlideIndex: 0,
          hardIssueSlideIds: [],
          advisoryIssueCount: 0,
          fixPreviewSlides: [],
          fixPreviewSourceIds: [],
          selectedFixPreviewSlideIds: [],
          issuePanelOpen: false,
          issuePanelSlideId: null,
          issueDecisionBySlideId: {},
        })),

      // Editor actions
      setPresentation: (p) =>
        set((state) => {
          if (!p) {
            return { presentation: null };
          }
          const currentSession = state.sessions.find(
            (session) => session.id === state.currentSessionId
          );
          const shouldSyncSessionTitle =
            p.title.trim().length > 0 && shouldSyncGeneratedSessionTitle(currentSession);
          return {
            presentation: p,
            sessions:
              shouldSyncSessionTitle && state.currentSessionId
                ? state.sessions.map((session) =>
                    session.id === state.currentSessionId
                      ? { ...session, title: p.title }
                      : session
                  )
                : state.sessions,
          };
        }),
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
          hardIssueSlideIds: patch.hardIssueSlideIds ?? state.hardIssueSlideIds,
          advisoryIssueCount: patch.advisoryIssueCount ?? state.advisoryIssueCount,
          fixPreviewSlides: patch.fixPreviewSlides ?? state.fixPreviewSlides,
          fixPreviewSourceIds: patch.fixPreviewSourceIds ?? state.fixPreviewSourceIds,
          selectedFixPreviewSlideIds:
            patch.selectedFixPreviewSlideIds ?? state.selectedFixPreviewSlideIds,
          activeGenerationCard:
            state.activeGenerationCard &&
            (patch.jobId ?? state.jobId) === state.activeGenerationCard.jobId
              ? {
                  ...state.activeGenerationCard,
                  status: patch.jobStatus ?? state.jobStatus ?? state.activeGenerationCard.status,
                  currentStage:
                    patch.currentStage ?? state.currentStage ?? state.activeGenerationCard.currentStage,
                }
              : state.activeGenerationCard,
        })),
      resetJobState: () =>
        set({
          jobId: null,
          jobStatus: null,
          currentStage: null,
          lastJobEventSeq: 0,
          issues: [],
          failedSlideIndices: [],
          hardIssueSlideIds: [],
          advisoryIssueCount: 0,
          fixPreviewSlides: [],
          fixPreviewSourceIds: [],
          selectedFixPreviewSlideIds: [],
          issuePanelOpen: false,
          issuePanelSlideId: null,
          issueDecisionBySlideId: {},
        }),
      setFixPreviewSelection: (slideIds) =>
        set({
          selectedFixPreviewSlideIds: Array.from(
            new Set(slideIds.filter((id) => id.trim().length > 0))
          ),
        }),
      toggleFixPreviewSelection: (slideId) =>
        set((state) => {
          if (!slideId) return {};
          const exists = state.selectedFixPreviewSlideIds.includes(slideId);
          return {
            selectedFixPreviewSlideIds: exists
              ? state.selectedFixPreviewSlideIds.filter((id) => id !== slideId)
              : [...state.selectedFixPreviewSlideIds, slideId],
          };
        }),
      setIssuePanelOpen: (issuePanelOpen) => set({ issuePanelOpen }),
      openIssuePanelForSlide: (slideId) =>
        set({
          issuePanelOpen: true,
          issuePanelSlideId: slideId,
        }),
      setIssueDecision: (slideId, status) =>
        set((state) => ({
          issueDecisionBySlideId: {
            ...state.issueDecisionBySlideId,
            [slideId]: status,
          },
        })),
      markSlidesProcessed: (slideIds, status) =>
        set((state) => {
          const next = { ...state.issueDecisionBySlideId };
          for (const slideId of slideIds) {
            if (!slideId) continue;
            next[slideId] = status;
          }
          return { issueDecisionBySlideId: next };
        }),
      resetIssueReviewState: () =>
        set({
          issuePanelOpen: false,
          issuePanelSlideId: null,
          issueDecisionBySlideId: {},
        }),
      clearFixReviewState: () =>
        set({
          hardIssueSlideIds: [],
          advisoryIssueCount: 0,
          fixPreviewSlides: [],
          fixPreviewSourceIds: [],
          selectedFixPreviewSlideIds: [],
          issuePanelOpen: false,
          issuePanelSlideId: null,
        }),
      addChatMessage: (msg) =>
        set((state) => ({ chatMessages: [...state.chatMessages, msg] })),
      setChatMessages: (messages) => set({ chatMessages: messages }),
      setPlanningState: (planningState) =>
        set((state) => ({
          planningState,
          draftOutline: Array.isArray(planningState?.outline?.items)
            ? planningState.outline.items
            : [],
          outlineStale: Boolean(planningState?.outline_stale),
          activeGenerationCard:
            planningState?.active_job_id
              ? {
                  jobId: planningState.active_job_id,
                  status: planningState.status,
                  currentStage:
                    state.activeGenerationCard?.jobId === planningState.active_job_id
                      ? state.activeGenerationCard.currentStage
                      : state.currentStage,
                  sessionTitle:
                    state.sessions.find((session) => session.id === state.currentSessionId)
                      ?.title || "未命名会话",
                  updatedAt: planningState.updated_at || null,
                }
              : null,
        })),
      setDraftOutline: (items) =>
        set((state) => ({
          draftOutline: items,
          planningState: state.planningState
            ? {
                ...state.planningState,
                outline: {
                  ...(state.planningState.outline || {}),
                  items,
                },
              }
            : state.planningState,
        })),
      setOutlineStale: (value) =>
        set((state) => ({
          outlineStale: value,
          planningState: state.planningState
            ? { ...state.planningState, outline_stale: value }
            : state.planningState,
        })),
      setActiveGenerationCard: (card) => set({ activeGenerationCard: card }),

      getCurrentSlide: () => {
        const { presentation, currentSlideIndex } = get();
        return presentation?.slides[currentSlideIndex] ?? null;
      },

      // Progressive generation actions
      initGenerationShell: (title, pageCount) =>
        set((state) => {
          const safeTitle = compactLoadingTitle(title, DEFAULT_LOADING_TITLE);
          const currentPresentationId =
            state.presentation?.presentationId || "pres-skeleton";
          const currentSession = state.sessions.find(
            (session) => session.id === state.currentSessionId
          );
          const sessions = shouldSyncGeneratedSessionTitle(currentSession)
            ? state.sessions.map((session) =>
                session.id === state.currentSessionId
                  ? { ...session, title: safeTitle }
                  : session
              )
            : state.sessions;
          return {
            presentation: {
              presentationId: currentPresentationId,
              title: safeTitle,
              slides: buildShellSlides(pageCount, safeTitle),
            },
            currentSlideIndex: 0,
            isGenerating: true,
            sessions,
          };
        }),
      setPresentationTitle: (title) =>
        set((state) => {
          if (!state.presentation) return {};
          const safeTitle = title.trim();
          if (!safeTitle) return {};
          const currentSession = state.sessions.find(
            (session) => session.id === state.currentSessionId
          );
          const shouldSyncSessionTitle =
            safeTitle.length > 0 && shouldSyncGeneratedSessionTitle(currentSession);
          return {
            presentation: {
              ...state.presentation,
              title: safeTitle,
            },
            sessions:
              shouldSyncSessionTitle && state.currentSessionId
                ? state.sessions.map((session) =>
                    session.id === state.currentSessionId
                      ? { ...session, title: safeTitle }
                      : session
                  )
                : state.sessions,
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

      // Create view actions
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
      setTopic: (topic) =>
        set((state) => ({
          topic,
          sessionTopicDrafts: setSessionTopicDraft(
            state.sessionTopicDrafts,
            state.currentSessionId,
            topic
          ),
        })),
      setSelectedTemplateId: (id) => set({ selectedTemplateId: id }),
      setNumPages: (n) => set({ numPages: n }),
    }),
    {
      name: "zhiyan-store",
      version: 2,
      migrate: (persistedState) => migrateLegacyTopicDraftState(persistedState),
      partialize: (state) => ({
        workspaceId: state.workspaceId,
        currentSessionId: state.currentSessionId,
        sessionTopicDrafts: state.sessionTopicDrafts,
        selectedTemplateId: state.selectedTemplateId,
        numPages: state.numPages,
      }),
    }
  )
);

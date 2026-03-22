import type { Presentation, Slide } from "@/types/slide";
import type { SourceMeta } from "@/types/source";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WORKSPACE_STORAGE_KEY = "zhiyan-workspace-id";
const LOCAL_FALLBACK_WORKSPACE_ID = "workspace-local-default";
let providerWorkspaceId: WorkspaceId | null = null;
let currentWorkspacePromise: Promise<WorkspaceInfo> | null = null;

function generateWorkspaceId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `ws-${crypto.randomUUID()}`;
  }
  return `ws-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`;
}

export type WorkspaceId = string;

export function getWorkspaceId(): WorkspaceId {
  if (providerWorkspaceId) return providerWorkspaceId;
  if (typeof window === "undefined") return LOCAL_FALLBACK_WORKSPACE_ID;
  const cached = window.localStorage.getItem(WORKSPACE_STORAGE_KEY);
  if (cached) return cached;
  const created = generateWorkspaceId();
  window.localStorage.setItem(WORKSPACE_STORAGE_KEY, created);
  return created;
}

export interface WorkspaceInfo {
  id: WorkspaceId;
  label?: string | null;
  owner_type?: string | null;
  owner_id?: string | null;
  created_at?: string | null;
  last_seen_at?: string | null;
}

function rememberWorkspaceId(id: WorkspaceId): void {
  providerWorkspaceId = id;
  if (typeof window !== "undefined") {
    window.localStorage.setItem(WORKSPACE_STORAGE_KEY, id);
  }
}

export async function getCurrentWorkspace(forceRefresh = false): Promise<WorkspaceInfo> {
  if (!forceRefresh && currentWorkspacePromise) {
    return currentWorkspacePromise;
  }
  currentWorkspacePromise = (async () => {
    const res = await fetch(`${API_BASE}/api/v1/workspaces/current`, {
      headers: withWorkspaceHeaders(),
    });
    if (!res.ok) {
      const fallback = getWorkspaceId();
      return { id: fallback };
    }
    const payload = (await res.json()) as WorkspaceInfo;
    const nextId = payload.id || getWorkspaceId();
    rememberWorkspaceId(nextId);
    return { ...payload, id: nextId };
  })();

  try {
    return await currentWorkspacePromise;
  } catch {
    const fallback = getWorkspaceId();
    return { id: fallback };
  }
}

function withWorkspaceHeaders(headers: HeadersInit = {}): HeadersInit {
  return {
    ...headers,
    "X-Workspace-Id": getWorkspaceId(),
  };
}

// ---------- Session ----------

export interface SessionSummary {
  id: string;
  workspace_id: string;
  title: string;
  title_edited_by_user: boolean;
  status: string;
  is_pinned: boolean;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  last_opened_at: string | null;
  source_count: number;
  chat_count: number;
  has_presentation: boolean;
}

export interface ChatRecord {
  id: string;
  role: "user" | "assistant" | string;
  content: string;
  created_at: string;
  model_meta: Record<string, unknown>;
}

export interface SnapshotMeta {
  id: string;
  version_no: number;
  is_snapshot: boolean;
  snapshot_label: string | null;
  created_at: string;
}

export interface SessionDetail {
  session: SessionSummary;
  sources: SourceMeta[];
  chat_messages: ChatRecord[];
  latest_generation_job: {
    job_id: string;
    status: JobStatus;
    updated_at: string;
  } | null;
  latest_presentation: {
    id: string;
    version_no: number;
    is_snapshot: boolean;
    snapshot_label: string | null;
    created_at: string;
    presentation: Presentation;
  } | null;
}

export async function createSession(title?: string): Promise<SessionSummary> {
  const res = await fetch(`${API_BASE}/api/v1/sessions`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ title: title || "未命名会话" }),
  });
  if (!res.ok) throw new Error(`创建会话失败: ${res.statusText}`);
  return res.json();
}

export async function listSessions(params?: {
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<SessionSummary[]> {
  const search = new URLSearchParams();
  if (params?.q) search.set("q", params.q);
  if (typeof params?.limit === "number") search.set("limit", String(params.limit));
  if (typeof params?.offset === "number") search.set("offset", String(params.offset));

  const query = search.toString();
  const url = `${API_BASE}/api/v1/sessions${query ? `?${query}` : ""}`;
  const res = await fetch(url, {
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) throw new Error(`获取会话列表失败: ${res.statusText}`);
  return res.json();
}

export async function getSessionDetail(sessionId: string): Promise<SessionDetail> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}`, {
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) throw new Error(`获取会话详情失败: ${res.statusText}`);
  return res.json();
}

export async function updateSession(
  sessionId: string,
  patch: {
    title?: string;
    is_pinned?: boolean;
    status?: string;
    archived?: boolean;
  }
): Promise<SessionSummary> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}`, {
    method: "PATCH",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(`更新会话失败: ${res.statusText}`);
  return res.json();
}

export async function removeSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}`, {
    method: "DELETE",
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) throw new Error(`删除会话失败: ${res.statusText}`);
}

export async function getSessionChat(sessionId: string): Promise<ChatRecord[]> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/chat`, {
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) throw new Error(`获取会话聊天记录失败: ${res.statusText}`);
  return res.json();
}

export async function appendSessionChat(
  sessionId: string,
  payload: { role: "user" | "assistant"; content: string; model_meta?: Record<string, unknown> }
): Promise<ChatRecord> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/chat`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`写入会话聊天失败: ${res.statusText}`);
  return res.json();
}

export async function getLatestSessionPresentation(sessionId: string): Promise<SessionDetail["latest_presentation"]> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/presentations/latest`, {
    headers: withWorkspaceHeaders(),
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`获取会话演示稿失败: ${res.statusText}`);
  return res.json();
}

export async function createSessionSnapshot(
  sessionId: string,
  snapshotLabel: string,
  presentation?: Presentation
): Promise<SnapshotMeta> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/snapshots`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ snapshot_label: snapshotLabel, presentation }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `创建快照失败: ${res.statusText}`);
  }
  return res.json();
}

export async function saveLatestSessionPresentation(
  sessionId: string,
  presentation: Presentation,
  source: "chat" | "editor" = "chat"
): Promise<SnapshotMeta> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/presentations/latest`, {
    method: "PUT",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ presentation, source }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `保存会话演示稿失败: ${res.statusText}`);
  }
  return res.json();
}

// ---------- Session Sources ----------

export async function listSessionSources(sessionId: string): Promise<SourceMeta[]> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/sources`, {
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) throw new Error(`获取来源列表失败: ${res.statusText}`);
  return res.json();
}

export async function getSessionSourceContent(
  sessionId: string,
  sourceId: string
): Promise<{ content: string }> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/sources/${sourceId}/content`, {
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) throw new Error(`获取来源内容失败: ${res.statusText}`);
  return res.json();
}

// ---------- Workspace Sources ----------

export async function listWorkspaceSources(params?: {
  q?: string;
  type?: "file" | "url" | "text";
  status?: "uploading" | "parsing" | "ready" | "error";
  sort?: "created_desc" | "created_asc" | "name_asc" | "name_desc" | "linked_desc";
  limit?: number;
  offset?: number;
}): Promise<SourceMeta[]> {
  const search = new URLSearchParams();
  if (params?.q) search.set("q", params.q);
  if (params?.type) search.set("type", params.type);
  if (params?.status) search.set("status", params.status);
  if (params?.sort) search.set("sort", params.sort);
  if (typeof params?.limit === "number") search.set("limit", String(params.limit));
  if (typeof params?.offset === "number") search.set("offset", String(params.offset));

  const query = search.toString();
  const url = `${API_BASE}/api/v1/workspace/sources${query ? `?${query}` : ""}`;
  const res = await fetch(url, { headers: withWorkspaceHeaders() });
  if (!res.ok) throw new Error(`获取素材库列表失败: ${res.statusText}`);
  return res.json();
}

export async function uploadWorkspaceSource(
  file: File,
  onProgress?: (pct: number) => void
): Promise<SourceMeta> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/v1/workspace/sources/upload`);
    xhr.setRequestHeader("X-Workspace-Id", getWorkspaceId());

    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        reject(new Error(`上传失败: ${xhr.statusText}`));
      }
    };
    xhr.onerror = () => reject(new Error("网络错误"));

    const formData = new FormData();
    formData.append("file", file);
    xhr.send(formData);
  });
}

export async function fetchWorkspaceUrlSource(url: string): Promise<SourceMeta> {
  const res = await fetch(`${API_BASE}/api/v1/workspace/sources/url`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ url }),
  });
  if (!res.ok) throw new Error(`URL 抓取失败: ${res.statusText}`);
  return res.json();
}

export async function addWorkspaceTextSource(name: string, content: string): Promise<SourceMeta> {
  const res = await fetch(`${API_BASE}/api/v1/workspace/sources/text`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ name, content }),
  });
  if (!res.ok) throw new Error(`添加文本失败: ${res.statusText}`);
  return res.json();
}

export async function getWorkspaceSourceContent(sourceId: string): Promise<{ content: string }> {
  const res = await fetch(`${API_BASE}/api/v1/workspace/sources/${sourceId}/content`, {
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) throw new Error(`获取来源内容失败: ${res.statusText}`);
  return res.json();
}

export async function deleteWorkspaceSource(sourceId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/workspace/sources/${sourceId}`, {
    method: "DELETE",
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) throw new Error(`删除来源失败: ${res.statusText}`);
}

export async function bulkDeleteWorkspaceSources(sourceIds: string[]): Promise<{
  deleted_ids: string[];
  not_found_ids: string[];
}> {
  const res = await fetch(`${API_BASE}/api/v1/workspace/sources/bulk-delete`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ source_ids: sourceIds }),
  });
  if (!res.ok) throw new Error(`批量删除来源失败: ${res.statusText}`);
  return res.json();
}

export async function linkSourcesToSession(sessionId: string, sourceIds: string[]): Promise<void> {
  const sid = encodeURIComponent(sessionId);
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sid}/sources/link`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ source_ids: sourceIds }),
  });
  if (!res.ok) throw new Error(`关联来源失败: ${res.statusText}`);
}

export async function unlinkSourceFromSession(sessionId: string, sourceId: string): Promise<void> {
  const sid = encodeURIComponent(sessionId);
  const srcId = encodeURIComponent(sourceId);
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sid}/sources/${srcId}/link`, {
    method: "DELETE",
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok && res.status !== 404) throw new Error(`取消关联失败: ${res.statusText}`);
}

// ---------- Generation v2 ----------

export type GenerationMode = "auto" | "review_outline";
export type JobStatus =
  | "pending"
  | "running"
  | "waiting_outline_review"
  | "waiting_fix_review"
  | "completed"
  | "failed"
  | "cancelled";
export type StageStatus =
  | "parse"
  | "outline"
  | "layout"
  | "slides"
  | "assets"
  | "verify"
  | "fix"
  | "complete";
export type EventType =
  | "job_started"
  | "stage_started"
  | "stage_progress"
  | "outline_ready"
  | "layout_ready"
  | "slide_ready"
  | "job_waiting_fix_review"
  | "fix_preview_ready"
  | "stage_failed"
  | "job_completed"
  | "job_failed"
  | "job_cancelled"
  | "heartbeat";

export type GenerationErrorCode =
  | "STAGE_TIMEOUT"
  | "PROVIDER_TIMEOUT"
  | "PROVIDER_NETWORK"
  | "PROVIDER_RATE_LIMIT"
  | "CANCELLED"
  | "UNKNOWN";

export interface GenerationEventPayload {
  step?: number;
  total_steps?: number;
  duration_ms?: number;
  stage_timeout_seconds?: number;
  started_at?: string;
  error?: string;
  error_code?: GenerationErrorCode;
  error_message?: string;
  retriable?: boolean;
  timeout_seconds?: number | null;
  provider_model?: string | null;
  provider?: string | null;
  stage?: string | null;
  [k: string]: unknown;
}

export interface CreateJobRequest {
  content?: string;
  topic?: string;
  session_id?: string;
  source_ids?: string[];
  template_id?: string;
  num_pages?: number;
  mode?: GenerationMode;
}

export interface CreateJobResponse {
  job_id: string;
  session_id: string | null;
  status: JobStatus;
  created_at: string;
  event_stream_url: string;
}

export interface GenerationIssue {
  slide_id?: string;
  severity?: string;
  category?: string;
  message?: string;
  suggestion?: string;
  tier?: "hard" | "advisory" | string;
  source?: string;
  [k: string]: unknown;
}

export interface GenerationRequestDataLite {
  num_pages?: number;
  title?: string;
}

export interface GenerationJob {
  job_id: string;
  status: JobStatus;
  current_stage: StageStatus | null;
  events_seq?: number;
  request?: GenerationRequestDataLite;
  outline: Record<string, unknown>;
  layouts: Array<Record<string, unknown>>;
  slides: Slide[];
  issues: GenerationIssue[];
  failed_slide_indices: number[];
  hard_issue_slide_ids?: string[];
  advisory_issue_count?: number;
  fix_preview_slides?: Slide[];
  fix_preview_source_ids?: string[];
  error: string | null;
  presentation?: Presentation | null;
  [k: string]: unknown;
}

export interface GenerationEvent {
  seq: number;
  type: EventType;
  job_id: string;
  ts: string;
  stage: StageStatus | null;
  message: string | null;
  payload: GenerationEventPayload;
}

export async function createJob(req: CreateJobRequest): Promise<CreateJobResponse> {
  const res = await fetch(`${API_BASE}/api/v2/generation/jobs`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      content: req.content ?? "",
      topic: req.topic ?? "",
      session_id: req.session_id ?? null,
      source_ids: req.source_ids ?? [],
      template_id: req.template_id ?? null,
      num_pages: req.num_pages ?? 5,
      mode: req.mode ?? "auto",
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `创建任务失败: ${res.statusText}`);
  }
  return res.json();
}

export async function getJob(jobId: string): Promise<GenerationJob> {
  const res = await fetch(`${API_BASE}/api/v2/generation/jobs/${jobId}`, {
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) throw new Error(`获取任务失败: ${res.statusText}`);
  return res.json();
}

export async function runJob(jobId: string): Promise<{ job_id: string; status: JobStatus; current_stage: StageStatus | null }> {
  const res = await fetch(`${API_BASE}/api/v2/generation/jobs/${jobId}/run`, {
    method: "POST",
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `运行任务失败: ${res.statusText}`);
  }
  return res.json();
}

export async function acceptOutline(
  jobId: string,
  outline?: Record<string, unknown>
): Promise<{ job_id: string; status: JobStatus; current_stage: StageStatus | null }> {
  const res = await fetch(`${API_BASE}/api/v2/generation/jobs/${jobId}/outline/accept`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ outline: outline ?? null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `确认大纲失败: ${res.statusText}`);
  }
  return res.json();
}

export async function cancelJob(
  jobId: string
): Promise<{ job_id: string; status: JobStatus; current_stage: StageStatus | null }> {
  const res = await fetch(`${API_BASE}/api/v2/generation/jobs/${jobId}/cancel`, {
    method: "POST",
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `取消任务失败: ${res.statusText}`);
  }
  return res.json();
}

export async function fixPreview(jobId: string, slideIds?: string[]): Promise<GenerationJob> {
  const res = await fetch(`${API_BASE}/api/v2/generation/jobs/${jobId}/fix/preview`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ slide_ids: slideIds && slideIds.length > 0 ? slideIds : null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `生成修复建议失败: ${res.statusText}`);
  }
  return res.json();
}

export async function fixApply(jobId: string, slideIds: string[]): Promise<GenerationJob> {
  const res = await fetch(`${API_BASE}/api/v2/generation/jobs/${jobId}/fix/apply`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ slide_ids: slideIds }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `应用修复失败: ${res.statusText}`);
  }
  return res.json();
}

export async function fixSkip(jobId: string): Promise<GenerationJob> {
  const res = await fetch(`${API_BASE}/api/v2/generation/jobs/${jobId}/fix/skip`, {
    method: "POST",
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `跳过修复失败: ${res.statusText}`);
  }
  return res.json();
}

export interface JobEventCallbacks {
  onEvent?: (event: GenerationEvent) => void;
  onDone?: () => void;
  onError?: (err: Error) => void;
}

export interface SubscribeJobEventsOptions {
  signal?: AbortSignal;
  afterSeq?: number;
}

export function buildJobEventsUrl(jobId: string, afterSeq?: number): string {
  const normalizedAfterSeq =
    typeof afterSeq === "number" && Number.isFinite(afterSeq)
      ? Math.max(0, Math.trunc(afterSeq))
      : 0;
  return normalizedAfterSeq > 0
    ? `${API_BASE}/api/v2/generation/jobs/${jobId}/events?after_seq=${normalizedAfterSeq}`
    : `${API_BASE}/api/v2/generation/jobs/${jobId}/events`;
}

export async function subscribeJobEvents(
  jobId: string,
  callbacks: JobEventCallbacks,
  options?: SubscribeJobEventsOptions
): Promise<void> {
  const { onEvent, onDone, onError } = callbacks;
  const signal = options?.signal;
  const eventsUrl = buildJobEventsUrl(jobId, options?.afterSeq);
  try {
    const res = await fetch(eventsUrl, {
      method: "GET",
      headers: withWorkspaceHeaders(),
      signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `订阅任务事件失败: ${res.statusText}`);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error("无法读取任务事件流");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const data = line.slice(6).trim();
        if (data === "[DONE]") {
          onDone?.();
          return;
        }
        try {
          const parsed = JSON.parse(data) as GenerationEvent;
          onEvent?.(parsed);
        } catch {
          // ignore invalid line
        }
      }
    }

    onDone?.();
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      onDone?.();
      return;
    }
    onError?.(err instanceof Error ? err : new Error(String(err)));
  }
}

// ---------- Export ----------

export type PptxExportMode = "structured" | "fallback-image";

export interface PptxExportResult {
  blob: Blob;
  mode: PptxExportMode;
}

export function parsePptxExportMode(value: string | null): PptxExportMode {
  return value === "fallback-image" ? "fallback-image" : "structured";
}

export async function exportPptx(presentation: Presentation): Promise<PptxExportResult> {
  const res = await fetch(`${API_BASE}/api/v1/export/pptx`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ presentation }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `PPTX 导出失败: ${res.statusText}`);
  }
  return {
    blob: await res.blob(),
    mode: parsePptxExportMode(res.headers.get("X-Zhiyan-Export-Mode")),
  };
}

export async function exportPdf(presentation: Presentation): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/v1/export/pdf`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ presentation }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `PDF 导出失败: ${res.statusText}`);
  }
  return res.blob();
}

// ---------- Chat ----------

interface ChatMessagePayload {
  role: "user" | "assistant";
  content: string;
}

interface ChatRequest {
  message: string;
  session_id?: string;
  messages?: ChatMessagePayload[];
  presentation_context?: Record<string, unknown>;
  current_slide_index?: number;
  action_hint?: ChatActionHint;
}

interface SlideUpdateEvent {
  slides: Slide[];
  modifications: Record<string, unknown>[];
}

export type ChatActionHint =
  | "refresh_layout"
  | "simplify"
  | "add_detail"
  | "enrich_visual"
  | "change_theme"
  | "free_text";

export interface ChatNoOpEvent {
  code: "NO_TOOL_MODIFICATION";
  reason: string;
}

export async function chatStream(
  req: ChatRequest,
  onChunk: (text: string) => void,
  onDone: () => void,
  onError?: (err: Error) => void,
  onSlideUpdate?: (update: SlideUpdateEvent) => void,
  onNoOp?: (event: ChatNoOpEvent) => void
): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/chat`, {
      method: "POST",
      headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(req),
    });

    if (!res.ok) {
      throw new Error(`聊天请求失败: ${res.statusText}`);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error("无法读取响应流");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6).trim();
          if (data === "[DONE]") {
            onDone();
            return;
          }
          try {
            const parsed = JSON.parse(data);
            if (parsed.type === "text" && parsed.content) {
              onChunk(parsed.content);
            } else if (parsed.type === "slide_update" && onSlideUpdate) {
              onSlideUpdate({
                slides: parsed.slides,
                modifications: parsed.modifications,
              });
            } else if (parsed.type === "no_op" && onNoOp) {
              onNoOp({
                code: parsed.code || "NO_TOOL_MODIFICATION",
                reason: parsed.reason || "本次请求未产生可执行修改",
              });
            } else if (parsed.type === "error") {
              onError?.(new Error(parsed.content));
            }
          } catch {
            // 跳过无法解析的行
          }
        }
      }
    }
    onDone();
  } catch (err) {
    onError?.(err instanceof Error ? err : new Error(String(err)));
  }
}

// ---------- Templates ----------

export async function uploadTemplate(file: File): Promise<{ template_id: string; name: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/v1/templates/upload`, {
    method: "POST",
    headers: withWorkspaceHeaders(),
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "模板上传失败");
  }
  return res.json();
}

export async function listTemplates(): Promise<{ templates: Array<{ id: string; name: string; builtin?: boolean; colors?: Record<string, string> }> }> {
  const res = await fetch(`${API_BASE}/api/v1/templates`, {
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) throw new Error("获取模板列表失败");
  return res.json();
}

// ---------- Skills ----------

interface SkillMeta {
  name: string;
  description: string;
  version: string;
  command: string;
}

export async function listSkills(): Promise<{ skills: SkillMeta[] }> {
  const res = await fetch(`${API_BASE}/api/v1/skills`, {
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) throw new Error(`获取 Skills 失败: ${res.statusText}`);
  return res.json();
}

// ---------- Settings ----------

export interface AppSettings {
  openai_api_key: string;
  openai_base_url: string;
  anthropic_api_key: string;
  google_api_key: string;
  deepseek_api_key: string;
  openrouter_api_key: string;
  default_model: string;
  strong_model: string;
  vision_model: string;
  fast_model: string;
  tts_model: string;
  tts_voice: string;
  enable_vision_verification: boolean;
  has_openai_key: boolean;
  has_anthropic_key: boolean;
  has_google_key: boolean;
  has_deepseek_key: boolean;
  has_openrouter_key: boolean;
  default_model_status: ModelStatus;
  strong_model_status: ModelStatus;
  vision_model_status: ModelStatus;
  fast_model_status: ModelStatus;
}

export interface ModelStatus {
  model: string;
  provider: string;
  ready: boolean;
  message: string;
}

export async function getSettings(): Promise<AppSettings> {
  const res = await fetch(`${API_BASE}/api/v1/settings`, {
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) throw new Error(`获取设置失败: ${res.statusText}`);
  return res.json();
}

export async function updateSettings(
  data: Partial<
    Omit<
      AppSettings,
      | "has_openai_key"
      | "has_anthropic_key"
      | "has_google_key"
      | "has_deepseek_key"
      | "has_openrouter_key"
      | "default_model_status"
      | "strong_model_status"
      | "vision_model_status"
      | "fast_model_status"
    >
  >
): Promise<AppSettings> {
  const res = await fetch(`${API_BASE}/api/v1/settings`, {
    method: "PUT",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`更新设置失败: ${res.statusText}`);
  return res.json();
}

export async function validateApiKey(
  provider: string,
  apiKey: string,
  baseUrl?: string
): Promise<{ valid: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/api/v1/settings/validate`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ provider, api_key: apiKey, base_url: baseUrl }),
  });
  if (!res.ok) throw new Error(`验证失败: ${res.statusText}`);
  return res.json();
}
// ---------- TTS ----------

export async function synthesizeSpeech(
  text: string,
  voice?: string,
  signal?: AbortSignal
): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/v1/tts`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ text, voice }),
    signal,
  });
  if (!res.ok) throw new Error(`TTS 失败: ${res.statusText}`);
  return res.blob();
}

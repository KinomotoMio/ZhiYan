import type { Presentation, Slide } from "@/types/slide";
import type { SourceMeta } from "@/types/source";
import { getSharePlaybackPath } from "@/lib/routes";

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

export interface PlanningOutlineItem {
  slide_number: number;
  title: string;
  content_brief?: string;
  key_points?: string[];
  content_hints?: string[];
  source_references?: string[];
  suggested_slide_role?: string;
  note?: string;
}

export interface TopicSuggestion {
  title: string;
  reason?: string;
  prompt?: string;
}

export interface PlanningState {
  session_id: string;
  mode?: string;
  status:
    | "collecting_requirements"
    | "outline_ready"
    | "generating"
    | "completed"
    | string;
  output_mode?: PresentationOutputMode;
  mode_selection_source?: "default" | "button" | "natural_language" | "agent_recommendation" | string;
  brief: Record<string, unknown>;
  outline: {
    narrative_arc?: string;
    items?: PlanningOutlineItem[];
    [key: string]: unknown;
  };
  outline_version: number;
  source_ids: string[];
  source_digest?: string;
  outline_stale: boolean;
  active_job_id: string | null;
  agent_workspace_root?: string | null;
  agent_session_version?: number;
  assistant_status?: string | null;
  topic_suggestions?: TopicSuggestion[];
  updated_at: string;
}

export interface SnapshotMeta {
  id: string;
  version_no: number;
  is_snapshot: boolean;
  snapshot_label: string | null;
  created_at: string;
}

export type PresentationOutputMode = "structured" | "html" | "slidev";

export interface HtmlDeckArtifactMeta {
  version: number;
  slide_count: number;
  updated_at: string;
  storage_path?: string;
  meta_storage_path?: string;
}

export interface SlidevDeckArtifactMeta {
  version: number;
  slide_count: number;
  updated_at: string;
  storage_path?: string;
  meta_storage_path?: string;
  selected_style_id?: string | null;
}

export interface SlidevBuildArtifactMeta {
  version: number;
  slide_count: number;
  updated_at: string;
  build_root?: string;
  entry_storage_path?: string;
  entry_relative_path?: string;
}

export interface LatestPresentationRecord {
  id: string;
  version_no: number;
  is_snapshot: boolean;
  snapshot_label: string | null;
  created_at: string;
  presentation: Presentation;
  output_mode?: PresentationOutputMode;
  artifacts?: {
    html_deck?: HtmlDeckArtifactMeta;
    slidev_deck?: SlidevDeckArtifactMeta;
    slidev_build?: SlidevBuildArtifactMeta;
    [key: string]: unknown;
  };
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
  latest_presentation: LatestPresentationRecord | null;
  planning_state: PlanningState | null;
}

export interface SessionShareLink {
  token: string;
  share_path: string;
  share_url: string;
  created_at: string;
}

export interface PublicSharePlayback {
  title: string;
  outputMode: PresentationOutputMode;
  presentation: Presentation | null;
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

export interface SessionPlanningDetail {
  planning_state: PlanningState | null;
  planning_messages: ChatRecord[];
}

export async function getSessionPlanning(sessionId: string): Promise<SessionPlanningDetail> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/planning`, {
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) throw new Error(`获取 planning 状态失败: ${res.statusText}`);
  return res.json();
}

export async function updatePlanningOutline(
  sessionId: string,
  outline: Record<string, unknown>
): Promise<PlanningState> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/planning/outline`, {
    method: "PATCH",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ outline }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `保存大纲失败: ${res.statusText}`);
  }
  return res.json();
}

export interface PlanningConfirmResult {
  job_id: string;
  status: JobStatus;
  current_stage: StageStatus | null;
  planning_state: PlanningState;
}

export function defaultSkillIdForOutputMode(
  outputMode: PresentationOutputMode
): string | undefined {
  if (outputMode === "slidev") return "slidev-default";
  if (outputMode === "html") return "html-default";
  return undefined;
}

export async function confirmPlanning(
  sessionId: string,
  outputMode: PresentationOutputMode = "slidev",
  skillId?: string
): Promise<PlanningConfirmResult> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/planning/confirm`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      output_mode: outputMode,
      skill_id: skillId ?? defaultSkillIdForOutputMode(outputMode) ?? null,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `确认大纲失败: ${res.statusText}`);
  }
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

export async function getLatestSessionPresentationHtml(sessionId: string): Promise<string | null> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/presentations/latest/html`, {
    headers: withWorkspaceHeaders(),
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`获取 HTML 演示稿失败: ${res.statusText}`);
  return res.text();
}

export async function getLatestSessionPresentationHtmlMeta(
  sessionId: string
): Promise<Record<string, unknown> | null> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/presentations/latest/html/meta`, {
    headers: withWorkspaceHeaders(),
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`获取 HTML 演示稿元数据失败: ${res.statusText}`);
  return res.json();
}

export interface SlidevDeckResponse {
  markdown: string;
  meta: Record<string, unknown>;
  build_url: string;
  assets?: {
    slidev_deck?: SlidevDeckArtifactMeta;
    slidev_build?: SlidevBuildArtifactMeta;
    [key: string]: unknown;
  };
}

export async function getLatestSessionPresentationSlidev(
  sessionId: string
): Promise<SlidevDeckResponse | null> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/presentations/latest/slidev`, {
    headers: withWorkspaceHeaders(),
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`获取 Slidev 演示稿失败: ${res.statusText}`);
  const payload = (await res.json()) as SlidevDeckResponse;
  return {
    ...payload,
    build_url: payload.build_url.startsWith("http") ? payload.build_url : `${API_BASE}${payload.build_url}`,
  };
}

export function buildLatestSessionPresentationSlidevUrl(sessionId: string): string {
  return `${API_BASE}/api/v1/sessions/${sessionId}/presentations/latest/slidev/build`;
}

export async function createOrGetSessionShareLink(sessionId: string): Promise<SessionShareLink> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/share-link`, {
    method: "POST",
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `生成分享链接失败: ${res.statusText}`);
  }
  const payload = (await res.json()) as SessionShareLink;
  const sharePath = payload.share_path || getSharePlaybackPath(payload.token);
  const fallbackUrl =
    typeof window !== "undefined" ? `${window.location.origin}${sharePath}` : sharePath;
  return {
    ...payload,
    share_path: sharePath,
    share_url: payload.share_url || fallbackUrl,
  };
}

export async function getPublicSharePlayback(token: string): Promise<PublicSharePlayback> {
  const res = await fetch(`${API_BASE}/api/v1/public/shares/${encodeURIComponent(token)}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `获取分享播放内容失败: ${res.statusText}`);
  }
  return res.json();
}

export async function getPublicShareHtml(token: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/v1/public/shares/${encodeURIComponent(token)}/html`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `获取分享 HTML 演示稿失败: ${res.statusText}`);
  }
  return res.text();
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

export async function saveLatestSessionHtmlPresentation(
  sessionId: string,
  presentation: Presentation,
  htmlContent: string,
  source: "chat" | "editor" = "chat"
): Promise<SnapshotMeta> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/presentations/latest`, {
    method: "PUT",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      presentation,
      source,
      output_mode: "html",
      html_deck: { html: htmlContent },
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `保存 HTML 演示稿失败: ${res.statusText}`);
  }
  return res.json();
}

export async function saveLatestSessionSlidevPresentation(
  sessionId: string,
  presentation: Presentation,
  markdown: string,
  selectedStyleId?: string | null,
  meta?: Record<string, unknown>,
  source: "chat" | "editor" = "chat"
): Promise<SnapshotMeta> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/presentations/latest`, {
    method: "PUT",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      presentation,
      source,
      output_mode: "slidev",
      slidev_deck: {
        markdown,
        selected_style_id: selectedStyleId ?? null,
        meta: meta ?? null,
      },
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `保存 Slidev 演示稿失败: ${res.statusText}`);
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
  approved_outline?: Record<string, unknown>;
  output_mode?: PresentationOutputMode;
  skill_id?: string;
}

export interface CreateJobResponse {
  job_id: string;
  session_id: string | null;
  status: JobStatus;
  created_at: string;
  event_stream_url: string;
  skill_id?: string | null;
  run_id?: string | null;
  run_metadata?: {
    run_id: string;
    skill_id?: string | null;
    base_skill_id?: string | null;
    activated_skills?: Array<{
      skill_id: string;
      name?: string | null;
      scope?: string | null;
      path?: string | null;
      source: string;
      reason: string;
      default_for_output?: string | null;
      resources?: string[];
      shadowed?: Array<Record<string, unknown>>;
    }>;
    output_mode?: PresentationOutputMode;
    latency_ms?: number | null;
    token_usage?: {
      prompt_tokens?: number;
      completion_tokens?: number;
      total_tokens?: number;
    };
    tool_events?: Array<Record<string, unknown>>;
    artifact_refs?: Record<string, unknown>;
    error_class?: string | null;
  } | null;
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
  topic?: string;
  output_mode?: PresentationOutputMode;
  skill_id?: string | null;
}

export interface GenerationJob {
  job_id: string;
  status: JobStatus;
  current_stage: StageStatus | null;
  events_seq?: number;
  output_mode?: PresentationOutputMode;
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
  run_metadata?: CreateJobResponse["run_metadata"];
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

export async function createJob(sessionId: string, req: CreateJobRequest): Promise<CreateJobResponse> {
  const outputMode = req.output_mode ?? "slidev";
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/generation/jobs`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      content: req.content ?? "",
      topic: req.topic ?? "",
      session_id: sessionId,
      source_ids: req.source_ids ?? [],
      template_id: req.template_id ?? null,
      num_pages: req.num_pages ?? 5,
      mode: req.mode ?? "auto",
      approved_outline: req.approved_outline ?? null,
      output_mode: outputMode,
      skill_id: req.skill_id ?? defaultSkillIdForOutputMode(outputMode) ?? null,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `创建任务失败: ${res.statusText}`);
  }
  return res.json();
}

export async function getJob(sessionId: string, jobId: string): Promise<GenerationJob> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/generation/jobs/${jobId}`, {
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) throw new Error(`获取任务失败: ${res.statusText}`);
  return res.json();
}

export async function runJob(
  sessionId: string,
  jobId: string
): Promise<{ job_id: string; status: JobStatus; current_stage: StageStatus | null }> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/generation/jobs/${jobId}/run`, {
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
  sessionId: string,
  jobId: string,
  outline?: Record<string, unknown>
): Promise<{ job_id: string; status: JobStatus; current_stage: StageStatus | null }> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/generation/jobs/${jobId}/outline/accept`, {
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
  sessionId: string,
  jobId: string
): Promise<{ job_id: string; status: JobStatus; current_stage: StageStatus | null }> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/generation/jobs/${jobId}/cancel`, {
    method: "POST",
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `取消任务失败: ${res.statusText}`);
  }
  return res.json();
}

export async function fixPreview(sessionId: string, jobId: string, slideIds?: string[]): Promise<GenerationJob> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/generation/jobs/${jobId}/fix/preview`, {
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

export async function fixApply(sessionId: string, jobId: string, slideIds: string[]): Promise<GenerationJob> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/generation/jobs/${jobId}/fix/apply`, {
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

export async function fixSkip(sessionId: string, jobId: string): Promise<GenerationJob> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/generation/jobs/${jobId}/fix/skip`, {
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

export function buildJobEventsUrl(sessionId: string, jobId: string, afterSeq?: number): string {
  const normalizedAfterSeq =
    typeof afterSeq === "number" && Number.isFinite(afterSeq)
      ? Math.max(0, Math.trunc(afterSeq))
      : 0;
  return normalizedAfterSeq > 0
    ? `${API_BASE}/api/v1/sessions/${sessionId}/generation/jobs/${jobId}/events?after_seq=${normalizedAfterSeq}`
    : `${API_BASE}/api/v1/sessions/${sessionId}/generation/jobs/${jobId}/events`;
}

export async function subscribeJobEvents(
  sessionId: string,
  jobId: string,
  callbacks: JobEventCallbacks,
  options?: SubscribeJobEventsOptions
): Promise<void> {
  const { onEvent, onDone, onError } = callbacks;
  const signal = options?.signal;
  const eventsUrl = buildJobEventsUrl(sessionId, jobId, options?.afterSeq);
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

export async function exportPptx(presentation: Presentation): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/v1/export/pptx`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ presentation }),
  });
  if (!res.ok) throw new Error(`PPTX 导出失败: ${res.statusText}`);
  return res.blob();
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
  skill_id?: string;
}

interface SlideUpdateEvent {
  slides: Slide[];
  modifications: Record<string, unknown>[];
}

interface HtmlUpdateEvent {
  html_content: string;
  presentation: Presentation;
  modifications?: Record<string, unknown>[];
}

interface SlidevUpdateEvent {
  markdown: string;
  meta: Record<string, unknown>;
  presentation: Presentation;
  selected_style_id?: string | null;
  preview_url: string;
  modifications?: Record<string, unknown>[];
}

export interface ChatAssistantStatusEvent {
  assistant_status:
    | "thinking"
    | "inspecting_context"
    | "running_tools"
    | "applying_change"
    | "ready"
    | "error"
    | string;
}

export interface ChatToolCallEvent {
  tool_name: string;
  call_id: string;
  summary: string;
}

export interface ChatToolResultEvent {
  tool_name: string;
  call_id: string;
  ok: boolean;
  summary: string;
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
  onNoOp?: (event: ChatNoOpEvent) => void,
  onHtmlUpdate?: (update: HtmlUpdateEvent) => void,
  onSlidevUpdate?: (update: SlidevUpdateEvent) => void,
  onAssistantStatus?: (event: ChatAssistantStatusEvent) => void,
  onToolCall?: (event: ChatToolCallEvent) => void,
  onToolResult?: (event: ChatToolResultEvent) => void
): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/chat`, {
      method: "POST",
      headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        ...req,
        skill_id:
          req.skill_id ??
          defaultSkillIdForOutputMode(
            (req.presentation_context?.output_mode as PresentationOutputMode | undefined) ??
              "slidev"
          ) ??
          null,
      }),
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
            } else if (parsed.type === "assistant_status" && onAssistantStatus) {
              onAssistantStatus({
                assistant_status: parsed.assistant_status || "thinking",
              });
            } else if (parsed.type === "tool_call" && onToolCall) {
              onToolCall({
                tool_name: parsed.tool_name || "",
                call_id: parsed.call_id || "",
                summary: parsed.summary || "",
              });
            } else if (parsed.type === "tool_result" && onToolResult) {
              onToolResult({
                tool_name: parsed.tool_name || "",
                call_id: parsed.call_id || "",
                ok: Boolean(parsed.ok),
                summary: parsed.summary || "",
              });
            } else if (parsed.type === "slide_update" && onSlideUpdate) {
              onSlideUpdate({
                slides: parsed.slides,
                modifications: parsed.modifications,
              });
            } else if (parsed.type === "html_update" && onHtmlUpdate) {
              onHtmlUpdate({
                html_content: parsed.html_content,
                presentation: parsed.presentation,
                modifications: parsed.modifications,
              });
            } else if (parsed.type === "slidev_update" && onSlidevUpdate) {
              onSlidevUpdate({
                markdown: parsed.markdown,
                meta: parsed.meta,
                presentation: parsed.presentation,
                selected_style_id: parsed.selected_style_id,
                preview_url:
                  typeof parsed.preview_url === "string" && parsed.preview_url.startsWith("http")
                    ? parsed.preview_url
                    : `${API_BASE}${parsed.preview_url}`,
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

export interface PlanningStreamEvent {
  type:
    | "text"
    | "brief_updated"
    | "outline_drafted"
    | "outline_revised"
    | "outline_updated"
    | "status_changed"
    | "assistant_status"
    | "topic_suggestions"
    | "planning_state"
    | "error";
  [key: string]: unknown;
}

export async function planningTurnStream(
  sessionId: string,
  message: string,
  onEvent: (event: PlanningStreamEvent) => void,
  onDone: () => void,
  onError?: (err: Error) => void
): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/planning/turns`, {
      method: "POST",
      headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ message }),
    });
    if (!res.ok) {
      throw new Error(`planning 请求失败: ${res.statusText}`);
    }
    const reader = res.body?.getReader();
    if (!reader) throw new Error("无法读取 planning 响应流");

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
          onDone();
          return;
        }
        try {
          onEvent(JSON.parse(data) as PlanningStreamEvent);
        } catch {
          // Skip malformed lines.
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
  id?: string;
  name: string;
  description: string;
  version?: string | null;
  command?: string | null;
  scope?: string;
  path?: string;
  default_for_output?: string;
  allowed_tools?: string;
  resources?: string[];
  shadowed?: Array<Record<string, unknown>>;
  shadowed_count?: number;
}

export async function listSkills(): Promise<{
  skills: SkillMeta[];
  defaults?: Record<string, string>;
}> {
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
  tts_provider: string;
  tts_api_key: string;
  tts_base_url: string;
  tts_model: string;
  tts_voice_id: string;
  enable_vision_verification: boolean;
  has_openai_key: boolean;
  has_anthropic_key: boolean;
  has_google_key: boolean;
  has_deepseek_key: boolean;
  has_openrouter_key: boolean;
  has_tts_key: boolean;
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
      | "has_tts_key"
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
export interface SpeakerNotesGenerateResponse {
  presentation: Presentation;
  updatedSlideIds: string[];
  workspaceRoot: string;
}

export interface SpeakerAudioEnsureResponse {
  slideId: string;
  speakerAudio: NonNullable<Slide["speakerAudio"]>;
  playbackPath: string;
}

export async function generateSpeakerNotes(
  sessionId: string,
  payload: {
    presentation: Presentation;
    scope: "current" | "all";
    currentSlideIndex: number;
  }
): Promise<SpeakerNotesGenerateResponse> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/speaker-notes/generate`, {
    method: "POST",
    headers: withWorkspaceHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `生成演讲者注解失败: ${res.statusText}`);
  }
  return res.json();
}

export async function ensureSpeakerAudio(
  sessionId: string,
  slideId: string
): Promise<SpeakerAudioEnsureResponse> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/slides/${slideId}/speaker-audio`, {
    method: "POST",
    headers: withWorkspaceHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `生成录音失败: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchSpeakerAudio(
  sessionId: string,
  slideId: string,
  signal?: AbortSignal
): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/slides/${slideId}/speaker-audio`, {
    headers: withWorkspaceHeaders(),
    signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `获取录音失败: ${res.statusText}`);
  }
  return res.blob();
}

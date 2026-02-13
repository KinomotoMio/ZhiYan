import type { Presentation, Slide } from "@/types/slide";
import type { SourceMeta } from "@/types/source";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------- Generation v2 ----------

export type GenerationMode = "auto" | "review_outline";
export type JobStatus =
  | "pending"
  | "running"
  | "waiting_outline_review"
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
  | "stage_failed"
  | "job_completed"
  | "job_failed"
  | "job_cancelled"
  | "heartbeat";

export interface CreateJobRequest {
  content?: string;
  topic?: string;
  source_ids?: string[];
  template_id?: string;
  num_pages?: number;
  mode?: GenerationMode;
}

export interface CreateJobResponse {
  job_id: string;
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
  [k: string]: unknown;
}

export interface GenerationJob {
  job_id: string;
  status: JobStatus;
  current_stage: StageStatus | null;
  outline: Record<string, unknown>;
  layouts: Array<Record<string, unknown>>;
  slides: Slide[];
  issues: GenerationIssue[];
  failed_slide_indices: number[];
  error: string | null;
  [k: string]: unknown;
}

export interface GenerationEvent {
  seq: number;
  type: EventType;
  job_id: string;
  ts: string;
  stage: StageStatus | null;
  message: string | null;
  payload: Record<string, unknown>;
}

export async function createJob(req: CreateJobRequest): Promise<CreateJobResponse> {
  const res = await fetch(`${API_BASE}/api/v2/generation/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content: req.content ?? "",
      topic: req.topic ?? "",
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
  const res = await fetch(`${API_BASE}/api/v2/generation/jobs/${jobId}`);
  if (!res.ok) throw new Error(`获取任务失败: ${res.statusText}`);
  return res.json();
}

export async function runJob(jobId: string): Promise<{ job_id: string; status: JobStatus; current_stage: StageStatus | null }> {
  const res = await fetch(`${API_BASE}/api/v2/generation/jobs/${jobId}/run`, {
    method: "POST",
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
    headers: { "Content-Type": "application/json" },
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
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `取消任务失败: ${res.statusText}`);
  }
  return res.json();
}

export interface JobEventCallbacks {
  onEvent?: (event: GenerationEvent) => void;
  onDone?: () => void;
  onError?: (err: Error) => void;
}

export async function subscribeJobEvents(
  jobId: string,
  callbacks: JobEventCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const { onEvent, onDone, onError } = callbacks;
  try {
    const res = await fetch(`${API_BASE}/api/v2/generation/jobs/${jobId}/events`, {
      method: "GET",
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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ presentation }),
  });
  if (!res.ok) throw new Error(`PPTX 导出失败: ${res.statusText}`);
  return res.blob();
}

export async function exportPdf(presentation: Presentation): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/v1/export/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ presentation }),
  });
  if (!res.ok) throw new Error(`PDF 导出失败: ${res.statusText}`);
  return res.blob();
}

// ---------- Chat ----------

interface ChatMessagePayload {
  role: "user" | "assistant";
  content: string;
}

interface ChatRequest {
  message: string;
  messages?: ChatMessagePayload[];
  presentation_context?: Record<string, unknown>;
  current_slide_index?: number;
}

interface SlideUpdateEvent {
  slides: Slide[];
  modifications: Record<string, unknown>[];
}

export async function chatStream(
  req: ChatRequest,
  onChunk: (text: string) => void,
  onDone: () => void,
  onError?: (err: Error) => void,
  onSlideUpdate?: (update: SlideUpdateEvent) => void
): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "模板上传失败");
  }
  return res.json();
}

export async function listTemplates(): Promise<{ templates: Array<{ id: string; name: string; builtin?: boolean; colors?: Record<string, string> }> }> {
  const res = await fetch(`${API_BASE}/api/v1/templates`);
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
  const res = await fetch(`${API_BASE}/api/v1/skills`);
  if (!res.ok) throw new Error(`获取 Skills 失败: ${res.statusText}`);
  return res.json();
}

// ---------- Sources ----------

export async function uploadSource(
  file: File,
  onProgress?: (pct: number) => void
): Promise<SourceMeta> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/v1/sources/upload`);

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

export async function fetchUrlSource(url: string): Promise<SourceMeta> {
  const res = await fetch(`${API_BASE}/api/v1/sources/url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) throw new Error(`URL 抓取失败: ${res.statusText}`);
  return res.json();
}

export async function addTextSource(
  name: string,
  content: string
): Promise<SourceMeta> {
  const res = await fetch(`${API_BASE}/api/v1/sources/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, content }),
  });
  if (!res.ok) throw new Error(`添加文本失败: ${res.statusText}`);
  return res.json();
}

export async function listSources(): Promise<SourceMeta[]> {
  const res = await fetch(`${API_BASE}/api/v1/sources/`);
  if (!res.ok) throw new Error(`获取来源列表失败: ${res.statusText}`);
  return res.json();
}

export async function deleteSource(sourceId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/sources/${sourceId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`删除来源失败: ${res.statusText}`);
}

export async function getSourceContent(
  sourceId: string
): Promise<{ content: string }> {
  const res = await fetch(`${API_BASE}/api/v1/sources/${sourceId}/content`);
  if (!res.ok) throw new Error(`获取来源内容失败: ${res.statusText}`);
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
  const res = await fetch(`${API_BASE}/api/v1/settings`);
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
    headers: { "Content-Type": "application/json" },
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
    headers: { "Content-Type": "application/json" },
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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, voice }),
    signal,
  });
  if (!res.ok) throw new Error(`TTS 失败: ${res.statusText}`);
  return res.blob();
}

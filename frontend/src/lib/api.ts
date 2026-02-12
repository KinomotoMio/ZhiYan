import type { Presentation } from "@/types/slide";
import type { SourceMeta } from "@/types/source";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------- Generate ----------

interface GenerateRequest {
  content?: string;
  topic?: string;
  source_ids?: string[];
  template_id?: string;
  num_pages?: number;
}

interface GenerateResponse {
  presentation: Presentation;
}

export async function generatePresentation(
  req: GenerateRequest
): Promise<GenerateResponse> {
  const res = await fetch(`${API_BASE}/api/v1/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`生成失败: ${res.statusText}`);
  return res.json();
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
  slides: Record<string, unknown>[];
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

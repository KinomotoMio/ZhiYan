// Source 数据模型 — 与后端 models/source.py 保持同步

export type SourceType = "file" | "url" | "text";

export type SourceStatus = "uploading" | "parsing" | "ready" | "error";

export type FileCategory =
  | "pdf"
  | "docx"
  | "markdown"
  | "pptx"
  | "image"
  | "text"
  | "unknown";

export interface SourceMeta {
  id: string;
  name: string;
  type: SourceType;
  fileCategory?: FileCategory;
  size?: number;
  status: SourceStatus;
  previewSnippet?: string;
  error?: string;
}

import type { SourceMeta, FileCategory } from "@/types/source";

export type AssetSort = "created_desc" | "name_asc" | "linked_desc";
export type AssetTypeFilter = "all" | "file" | "url" | "text";
export type AssetStatusFilter = "all" | "ready" | "error" | "parsing" | "uploading";

export type AssetRetryPayload =
  | { kind: "file"; file: File }
  | { kind: "url"; url: string }
  | { kind: "text"; name: string; content: string };

export interface AssetListEntry {
  key: string;
  source: SourceMeta;
  isTemp?: boolean;
  progress?: number | null;
  retryPayload?: AssetRetryPayload;
}

const FILE_CATEGORY_BY_EXTENSION: Record<string, FileCategory> = {
  pdf: "pdf",
  doc: "docx",
  docx: "docx",
  md: "markdown",
  markdown: "markdown",
  ppt: "pptx",
  pptx: "pptx",
  png: "image",
  jpg: "image",
  jpeg: "image",
  gif: "image",
  webp: "image",
  txt: "text",
  csv: "text",
  json: "text",
};

function detectFileCategory(name: string): FileCategory | undefined {
  const match = /\.([^.]+)$/.exec(name.trim().toLowerCase());
  if (!match) return undefined;
  return FILE_CATEGORY_BY_EXTENSION[match[1]];
}

function buildTempId(prefix: string): string {
  return `temp-${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

export function createTempFileEntry(file: File): AssetListEntry {
  const now = new Date().toISOString();
  const id = buildTempId("file");
  return {
    key: id,
    isTemp: true,
    progress: 0,
    retryPayload: { kind: "file", file },
    source: {
      id,
      name: file.name,
      type: "file",
      fileCategory: detectFileCategory(file.name),
      size: file.size,
      status: "uploading",
      created_at: now,
    },
  };
}

export function createTempUrlEntry(url: string): AssetListEntry {
  const now = new Date().toISOString();
  const id = buildTempId("url");
  return {
    key: id,
    isTemp: true,
    retryPayload: { kind: "url", url },
    source: {
      id,
      name: url,
      type: "url",
      status: "parsing",
      created_at: now,
    },
  };
}

export function createTempTextEntry(name: string, content: string): AssetListEntry {
  const now = new Date().toISOString();
  const id = buildTempId("text");
  return {
    key: id,
    isTemp: true,
    retryPayload: { kind: "text", name, content },
    source: {
      id,
      name,
      type: "text",
      fileCategory: "text",
      size: new TextEncoder().encode(content).length,
      status: "parsing",
      previewSnippet: content.trim().slice(0, 200) || undefined,
      created_at: now,
    },
  };
}

export function updateTempEntryProgress(
  entries: AssetListEntry[],
  key: string,
  progress: number
): AssetListEntry[] {
  return entries.map((entry) =>
    entry.key === key
      ? {
          ...entry,
          progress,
        }
      : entry
  );
}

export function markTempEntryError(
  entries: AssetListEntry[],
  key: string,
  error: string
): AssetListEntry[] {
  return entries.map((entry) =>
    entry.key === key
      ? {
          ...entry,
          progress: null,
          source: {
            ...entry.source,
            status: "error",
            error,
          },
        }
      : entry
  );
}

export function removeAssetEntry(entries: AssetListEntry[], key: string): AssetListEntry[] {
  return entries.filter((entry) => entry.key !== key);
}

export function upsertPersistedSource(items: SourceMeta[], source: SourceMeta): SourceMeta[] {
  const next = items.filter((item) => item.id !== source.id);
  return [source, ...next];
}

export function describeAssetEntryStatus(entry: AssetListEntry): string | undefined {
  if (entry.source.status === "uploading") {
    if (typeof entry.progress === "number" && entry.progress > 0) {
      return `上传中 ${entry.progress}%`;
    }
    return "上传中...";
  }
  if (entry.source.status === "parsing") {
    return entry.source.type === "text" ? "正在保存文本..." : "解析中...";
  }
  return undefined;
}

function matchesQuery(source: SourceMeta, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  return (
    source.name.toLowerCase().includes(normalized) ||
    (source.previewSnippet || "").toLowerCase().includes(normalized)
  );
}

function matchesType(source: SourceMeta, typeFilter: AssetTypeFilter): boolean {
  return typeFilter === "all" ? true : source.type === typeFilter;
}

function matchesStatus(source: SourceMeta, statusFilter: AssetStatusFilter): boolean {
  return statusFilter === "all" ? true : source.status === statusFilter;
}

function toTimestamp(source: SourceMeta): number {
  if (!source.created_at) return 0;
  const parsed = Date.parse(source.created_at);
  return Number.isFinite(parsed) ? parsed : 0;
}

function compareBySort(a: AssetListEntry, b: AssetListEntry, sort: AssetSort): number {
  if (sort === "name_asc") {
    return a.source.name.localeCompare(b.source.name, "zh-CN", { sensitivity: "base" });
  }
  if (sort === "linked_desc") {
    const linkedDiff =
      (b.source.linked_session_count ?? 0) - (a.source.linked_session_count ?? 0);
    if (linkedDiff !== 0) return linkedDiff;
  }
  return toTimestamp(b.source) - toTimestamp(a.source);
}

export function mergeAssetEntries(params: {
  persistedItems: SourceMeta[];
  tempEntries: AssetListEntry[];
  query: string;
  typeFilter: AssetTypeFilter;
  statusFilter: AssetStatusFilter;
  sort: AssetSort;
}): AssetListEntry[] {
  const persistedEntries = params.persistedItems.map((source) => ({
    key: source.id,
    source,
  }));
  const combined = [...params.tempEntries, ...persistedEntries];
  return combined
    .filter((entry) => matchesQuery(entry.source, params.query))
    .filter((entry) => matchesType(entry.source, params.typeFilter))
    .filter((entry) => matchesStatus(entry.source, params.statusFilter))
    .sort((a, b) => compareBySort(a, b, params.sort));
}

export function getDeletableIds(entries: AssetListEntry[]): string[] {
  return entries.filter((entry) => !entry.isTemp).map((entry) => entry.source.id);
}

import type { SourceMeta } from "@/types/source";

export type SourcePreviewKind = "image" | "text";

export function canHoverPreviewSource(
  source: Pick<SourceMeta, "fileCategory" | "previewSnippet" | "status">
): boolean {
  if (source.status !== "ready") return false;
  if (source.fileCategory === "image") return true;
  return Boolean(source.previewSnippet);
}

export function getSourcePreviewKind(
  source: Pick<SourceMeta, "fileCategory" | "status">
): SourcePreviewKind {
  if (source.status === "ready" && source.fileCategory === "image") {
    return "image";
  }
  return "text";
}

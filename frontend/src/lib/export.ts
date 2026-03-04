/**
 * @deprecated Legacy export helpers are frozen.
 * Use `@/lib/api` exportPptx/exportPdf in active code paths.
 */

import type { Presentation } from "@/types/slide";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function downloadExport(
  presentation: Presentation,
  format: "pptx" | "pdf",
  fileName?: string,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/export/${format}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ presentation }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `${format.toUpperCase()} 导出失败: ${res.statusText}`);
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName || `${presentation.title || "presentation"}.${format}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * @deprecated Frozen compatibility wrapper.
 */
export async function exportPptxClient(
  presentation: Presentation,
  options?: { fileName?: string },
): Promise<void> {
  return downloadExport(presentation, "pptx", options?.fileName);
}

/**
 * @deprecated Frozen compatibility wrapper.
 */
export async function exportPptxServer(
  presentationId: string, // kept for legacy signature compatibility
  options?: { fileName?: string; presentation?: Presentation },
): Promise<void> {
  const presentation = options?.presentation;
  if (!presentation) {
    throw new Error(
      `Legacy exportPptxServer(${presentationId}) 已冻结。请改用 @/lib/api.exportPptx(presentation)。`,
    );
  }
  return downloadExport(presentation, "pptx", options?.fileName);
}

/**
 * @deprecated Frozen compatibility wrapper.
 */
export async function exportPptx(
  presentation: Presentation,
  options?: { fileName?: string; preferServer?: boolean },
): Promise<void> {
  void options?.preferServer;
  return downloadExport(presentation, "pptx", options?.fileName);
}

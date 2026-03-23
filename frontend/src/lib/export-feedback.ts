import type { PptxExportMode } from "@/lib/api";

export function getExportSuccessMessage(
  format: "pptx" | "pdf",
  pptxMode: PptxExportMode = "structured"
): string {
  if (format === "pdf") {
    return "PDF 导出成功";
  }

  if (pptxMode === "fallback-image") {
    return "PPTX 已按图片兜底导出，视觉保真优先，但不保证可编辑性";
  }

  return "PPTX 导出成功";
}

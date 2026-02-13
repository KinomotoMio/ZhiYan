/**
 * PPTX 导出模块 — 使用 dom-to-pptx 将 DOM 元素导出为 .pptx
 *
 * 主要方案：客户端 dom-to-pptx（高保真，所见即所得）
 * 回退方案：服务端 python-pptx（通过 /api/v1/export/pptx）
 */

import type { Presentation } from "@/types/slide";

/**
 * 客户端 dom-to-pptx 导出
 *
 * 要求页面中已渲染所有 slides 为 1280x720 DOM 元素，
 * 并使用 `data-slide-export` 属性标记。
 */
export async function exportPptxClient(
  presentation: Presentation,
  options?: { fileName?: string },
): Promise<void> {
  const { exportToPptx } = await import("dom-to-pptx");

  const slideElements = document.querySelectorAll<HTMLElement>(
    "[data-slide-export]",
  );

  if (slideElements.length === 0) {
    throw new Error("未找到可导出的幻灯片 DOM 元素");
  }

  const fileName =
    options?.fileName || `${presentation.title || "演示文稿"}.pptx`;

  await exportToPptx(Array.from(slideElements), {
    fileName,
  });
}

/**
 * 服务端 python-pptx 导出（回退方案）
 */
export async function exportPptxServer(
  presentationId: string,
  options?: { fileName?: string },
): Promise<void> {
  const response = await fetch(
    `/api/v1/export/pptx?presentation_id=${encodeURIComponent(presentationId)}`,
    { method: "GET" },
  );

  if (!response.ok) {
    throw new Error(`导出失败: ${response.statusText}`);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = options?.fileName || "presentation.pptx";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * 统一导出入口 — 优先客户端，失败回退服务端
 */
export async function exportPptx(
  presentation: Presentation,
  options?: { fileName?: string; preferServer?: boolean },
): Promise<void> {
  if (options?.preferServer) {
    return exportPptxServer(presentation.presentationId, options);
  }

  try {
    await exportPptxClient(presentation, options);
  } catch (err) {
    console.warn("客户端 PPTX 导出失败，回退到服务端:", err);
    return exportPptxServer(presentation.presentationId, options);
  }
}

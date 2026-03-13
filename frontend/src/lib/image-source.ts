import type { ImageRef, ImageSource } from "@/types/layout-data";

type ImageLike = Partial<ImageRef> | Record<string, unknown> | null | undefined;

function asText(value: unknown): string {
  if (typeof value === "string") {
    const text = value.trim();
    if (text) return text;
  }
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

export function getImageSource(image: ImageLike): ImageSource {
  const source = asText(image && typeof image === "object" ? (image as Record<string, unknown>).source : undefined);
  if (source === "ai" || source === "user" || source === "existing") {
    return source;
  }

  const url = asText(image && typeof image === "object" ? (image as Record<string, unknown>).url : undefined);
  if (url) return "existing";

  const prompt = asText(image && typeof image === "object" ? (image as Record<string, unknown>).prompt : undefined);
  if (prompt) return "ai";

  return "user";
}

export function getImagePlaceholderCopy(image: ImageLike): { title: string; detail: string } {
  const source = getImageSource(image);
  const prompt = asText(image && typeof image === "object" ? (image as Record<string, unknown>).prompt : undefined);
  if (source === "ai") {
    return { title: prompt || "AI 图片待生成", detail: "" };
  }
  if (source === "user") {
    return { title: "待用户补图/上传", detail: prompt };
  }
  return { title: "待绑定现有素材", detail: prompt };
}

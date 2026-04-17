export type AddSourceMode = "file" | "url" | "text";

export interface AddSourceAreaDrafts {
  mode: AddSourceMode;
  urlValue: string;
  textName: string;
  textContent: string;
}

const AUTO_TEXT_SOURCE_NAME_MAX_LENGTH = 48;

function collapseWhitespace(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

export function getAvailableAddSourceModes(hasTextSubmit: boolean): AddSourceMode[] {
  return hasTextSubmit ? ["file", "url", "text"] : ["file", "url"];
}

export function canSubmitUrlSource(urlValue: string): boolean {
  return urlValue.trim().length > 0;
}

export function canSubmitTextSource(name: string, content: string): boolean {
  return content.trim().length > 0;
}

export function resolveTextSourceName(name: string, content: string): string {
  const normalizedName = collapseWhitespace(name);
  if (normalizedName.length > 0) {
    return normalizedName;
  }

  const fallback =
    content
      .split(/\r?\n/)
      .map(collapseWhitespace)
      .find((line) => line.length > 0) ?? "";

  if (!fallback) {
    return "未命名文本素材";
  }

  if (fallback.length <= AUTO_TEXT_SOURCE_NAME_MAX_LENGTH) {
    return fallback;
  }

  return `${fallback.slice(0, AUTO_TEXT_SOURCE_NAME_MAX_LENGTH).trimEnd()}...`;
}

export function resetAddSourceAreaDrafts(): AddSourceAreaDrafts {
  return {
    mode: "file",
    urlValue: "",
    textName: "",
    textContent: "",
  };
}

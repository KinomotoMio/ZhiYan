export type AddSourceMode = "file" | "url" | "text";

export interface AddSourceAreaDrafts {
  mode: AddSourceMode;
  urlValue: string;
  textName: string;
  textContent: string;
}

export function getAvailableAddSourceModes(hasTextSubmit: boolean): AddSourceMode[] {
  return hasTextSubmit ? ["file", "url", "text"] : ["file", "url"];
}

export function canSubmitUrlSource(urlValue: string): boolean {
  return urlValue.trim().length > 0;
}

export function canSubmitTextSource(name: string, content: string): boolean {
  return name.trim().length > 0 && content.trim().length > 0;
}

export function resetAddSourceAreaDrafts(): AddSourceAreaDrafts {
  return {
    mode: "file",
    urlValue: "",
    textName: "",
    textContent: "",
  };
}

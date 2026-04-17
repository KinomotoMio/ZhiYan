export interface SlidevPreviewStateInput {
  buildUrl?: string | null;
  renderStatus?: string | null;
  renderError?: string | null;
}

export interface ResolvedSlidevPreviewState {
  buildUrl: string | null;
  renderStatus: string | null;
  renderError: string | null;
  previewReady: boolean;
  buildFailed: boolean;
  showBuildingState: boolean;
}

function normalizeString(value: string | null | undefined): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function resolveSlidevPreviewState(
  input: SlidevPreviewStateInput
): ResolvedSlidevPreviewState {
  const buildUrl = normalizeString(input.buildUrl);
  const renderError = normalizeString(input.renderError);
  const rawRenderStatus = normalizeString(input.renderStatus);
  const renderStatus = buildUrl ? "ready" : rawRenderStatus;
  const previewReady = Boolean(buildUrl);
  const buildFailed = !previewReady && renderStatus === "failed";

  return {
    buildUrl,
    renderStatus,
    renderError,
    previewReady,
    buildFailed,
    showBuildingState: !previewReady && !buildFailed,
  };
}

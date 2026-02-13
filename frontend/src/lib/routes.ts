export function getSessionEditorPath(sessionId: string): string {
  return `/sessions/${sessionId}/editor`;
}

export function canShowContinueEditorEntry(
  currentSessionId: string | null,
  isGenerating: boolean,
  hasPresentation: boolean
): boolean {
  return Boolean(currentSessionId) && !isGenerating && hasPresentation;
}

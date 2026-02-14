export function getSessionEditorPath(sessionId: string): string {
  return `/sessions/${sessionId}/editor`;
}

interface CreateRouteSession {
  id: string;
  has_presentation: boolean;
}

export function canShowContinueEditorEntry(
  currentSessionId: string | null,
  isGenerating: boolean,
  hasPresentation: boolean
): boolean {
  return Boolean(currentSessionId) && !isGenerating && hasPresentation;
}

export function shouldAutoRedirectToEditor(
  hasPresentation: boolean,
  fromExplicitSessionParam: boolean
): boolean {
  return fromExplicitSessionParam && hasPresentation;
}

export function pickCreateLandingSessionId(
  sessions: CreateRouteSession[],
  currentSessionId: string | null
): string | null {
  if (currentSessionId) {
    const current = sessions.find((item) => item.id === currentSessionId);
    if (current && !current.has_presentation) {
      return current.id;
    }
  }
  const editable = sessions.find((item) => !item.has_presentation);
  return editable?.id ?? null;
}

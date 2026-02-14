import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { canShowContinueEditorEntry } from "@/lib/routes";

function SessionEntryProbe({
  currentSessionId,
  isGenerating,
  hasPresentation,
}: {
  currentSessionId: string | null;
  isGenerating: boolean;
  hasPresentation: boolean;
}) {
  if (!canShowContinueEditorEntry(currentSessionId, isGenerating, hasPresentation)) {
    return <span>hidden</span>;
  }
  return <button type="button">继续编辑当前结果</button>;
}

test("shows continue editor entry when session exists and not generating", () => {
  const html = renderToStaticMarkup(
    <SessionEntryProbe
      currentSessionId="session-1"
      isGenerating={false}
      hasPresentation
    />
  );
  assert.match(html, /继续编辑当前结果/);
});

test("hides continue editor entry while generating", () => {
  const html = renderToStaticMarkup(
    <SessionEntryProbe
      currentSessionId="session-1"
      isGenerating
      hasPresentation
    />
  );
  assert.match(html, /hidden/);
});

test("hides continue editor entry when session has no result", () => {
  const html = renderToStaticMarkup(
    <SessionEntryProbe
      currentSessionId="session-1"
      isGenerating={false}
      hasPresentation={false}
    />
  );
  assert.match(html, /hidden/);
});

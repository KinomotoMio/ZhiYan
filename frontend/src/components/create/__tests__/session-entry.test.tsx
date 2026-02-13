import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { canShowContinueEditorEntry } from "@/lib/routes";

function SessionEntryProbe({
  currentSessionId,
  isGenerating,
}: {
  currentSessionId: string | null;
  isGenerating: boolean;
}) {
  if (!canShowContinueEditorEntry(currentSessionId, isGenerating)) {
    return <span>hidden</span>;
  }
  return <button type="button">继续编辑当前结果</button>;
}

test("shows continue editor entry when session exists and not generating", () => {
  const html = renderToStaticMarkup(
    <SessionEntryProbe currentSessionId="session-1" isGenerating={false} />
  );
  assert.match(html, /继续编辑当前结果/);
});

test("hides continue editor entry while generating", () => {
  const html = renderToStaticMarkup(
    <SessionEntryProbe currentSessionId="session-1" isGenerating />
  );
  assert.match(html, /hidden/);
});


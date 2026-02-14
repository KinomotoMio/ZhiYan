import assert from "node:assert/strict";
import test from "node:test";

import {
  getSessionEditorPath,
  pickCreateLandingSessionId,
  shouldAutoRedirectToEditor,
} from "@/lib/routes";

test("getSessionEditorPath returns canonical session editor route", () => {
  assert.equal(getSessionEditorPath("abc"), "/sessions/abc/editor");
});

test("getSessionEditorPath appends one-based slide query when provided", () => {
  assert.equal(getSessionEditorPath("abc", { slide: 3 }), "/sessions/abc/editor?slide=3");
});

test("pickCreateLandingSessionId prefers current editable session", () => {
  const picked = pickCreateLandingSessionId(
    [
      { id: "sess-result", has_presentation: true },
      { id: "sess-draft", has_presentation: false },
    ],
    "sess-draft"
  );
  assert.equal(picked, "sess-draft");
});

test("pickCreateLandingSessionId falls back to first editable session", () => {
  const picked = pickCreateLandingSessionId(
    [
      { id: "sess-result", has_presentation: true },
      { id: "sess-draft", has_presentation: false },
    ],
    "sess-result"
  );
  assert.equal(picked, "sess-draft");
});

test("pickCreateLandingSessionId returns null when all sessions have presentation", () => {
  const picked = pickCreateLandingSessionId(
    [
      { id: "sess-a", has_presentation: true },
      { id: "sess-b", has_presentation: true },
    ],
    null
  );
  assert.equal(picked, null);
});

test("shouldAutoRedirectToEditor only redirects for explicit session route", () => {
  assert.equal(shouldAutoRedirectToEditor(true, false), false);
  assert.equal(shouldAutoRedirectToEditor(true, true), true);
  assert.equal(shouldAutoRedirectToEditor(false, true), false);
});

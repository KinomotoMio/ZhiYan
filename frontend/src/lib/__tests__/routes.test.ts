import assert from "node:assert/strict";
import test from "node:test";

import {
  canResumeGenerationJob,
  getCreateSessionPath,
  getSharePlaybackPath,
  getSessionEditorPath,
  pickCreateLandingSessionId,
  resolvePostCreateEditorPath,
  shouldAutoRedirectToEditor,
} from "@/lib/routes";

test("getSessionEditorPath returns canonical session editor route", () => {
  assert.equal(getSessionEditorPath("abc"), "/sessions/abc/editor");
});

test("getSessionEditorPath appends one-based slide query when provided", () => {
  assert.equal(getSessionEditorPath("abc", { slide: 3 }), "/sessions/abc/editor?slide=3");
});

test("getSharePlaybackPath returns canonical public share route", () => {
  assert.equal(getSharePlaybackPath("share-token"), "/share/share-token");
  assert.equal(getSharePlaybackPath("a/b?c"), "/share/a%2Fb%3Fc");
});

test("getCreateSessionPath returns bare create route without session", () => {
  assert.equal(getCreateSessionPath(), "/create");
  assert.equal(getCreateSessionPath(null), "/create");
});

test("getCreateSessionPath preserves the target create session", () => {
  assert.equal(getCreateSessionPath("sess-123"), "/create?session=sess-123");
});

test("getCreateSessionPath can preserve session while suppressing editor bounce-back", () => {
  assert.equal(
    getCreateSessionPath("sess-123", { fromEditor: true }),
    "/create?session=sess-123&from=editor"
  );
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

test("resolvePostCreateEditorPath prefers created session id", () => {
  const path = resolvePostCreateEditorPath("sess-created", "sess-current", "sess-fallback");
  assert.equal(path, "/sessions/sess-created/editor");
});

test("resolvePostCreateEditorPath falls back to current and fallback session", () => {
  assert.equal(
    resolvePostCreateEditorPath(null, "sess-current", "sess-fallback"),
    "/sessions/sess-current/editor"
  );
  assert.equal(
    resolvePostCreateEditorPath(null, null, "sess-fallback"),
    "/sessions/sess-fallback/editor"
  );
  assert.equal(resolvePostCreateEditorPath(null, null, null), null);
});

test("canResumeGenerationJob is true only for failed/cancelled jobs", () => {
  assert.equal(canResumeGenerationJob("job-1", "failed"), true);
  assert.equal(canResumeGenerationJob("job-1", "cancelled"), true);
  assert.equal(canResumeGenerationJob("job-1", "running"), false);
  assert.equal(canResumeGenerationJob(null, "failed"), false);
});

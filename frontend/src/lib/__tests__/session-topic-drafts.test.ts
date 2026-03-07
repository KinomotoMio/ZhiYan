import assert from "node:assert/strict";
import test from "node:test";

import {
  getSessionTopicDraft,
  migrateLegacyTopicDraftState,
  normalizeSessionTopicDrafts,
  removeSessionTopicDraft,
  setSessionTopicDraft,
} from "@/lib/session-topic-drafts";

test("getSessionTopicDraft returns empty string for missing session draft", () => {
  assert.equal(getSessionTopicDraft({}, null), "");
  assert.equal(getSessionTopicDraft({}, "session-1"), "");
});

test("setSessionTopicDraft scopes drafts per session and clears empty values", () => {
  const drafts = setSessionTopicDraft({}, "session-1", "Quarterly review");
  assert.deepEqual(drafts, { "session-1": "Quarterly review" });

  const updated = setSessionTopicDraft(drafts, "session-2", "Product launch");
  assert.deepEqual(updated, {
    "session-1": "Quarterly review",
    "session-2": "Product launch",
  });

  const cleared = setSessionTopicDraft(updated, "session-1", "");
  assert.deepEqual(cleared, { "session-2": "Product launch" });
});

test("removeSessionTopicDraft drops only the targeted session", () => {
  const drafts = {
    "session-1": "Quarterly review",
    "session-2": "Product launch",
  };

  assert.deepEqual(removeSessionTopicDraft(drafts, "session-1"), {
    "session-2": "Product launch",
  });
  assert.deepEqual(removeSessionTopicDraft(drafts, "session-3"), drafts);
});

test("normalizeSessionTopicDrafts keeps only non-empty string entries", () => {
  assert.deepEqual(
    normalizeSessionTopicDrafts({
      "session-1": "Topic A",
      "session-2": "",
      "": "Topic C",
      "session-3": 42,
    }),
    { "session-1": "Topic A" }
  );
});

test("migrateLegacyTopicDraftState converts legacy global topic into current session draft", () => {
  assert.deepEqual(
    migrateLegacyTopicDraftState({
      currentSessionId: "session-1",
      topic: "Legacy draft topic",
      selectedTemplateId: "default",
    }),
    {
      currentSessionId: "session-1",
      selectedTemplateId: "default",
      sessionTopicDrafts: {
        "session-1": "Legacy draft topic",
      },
    }
  );
});

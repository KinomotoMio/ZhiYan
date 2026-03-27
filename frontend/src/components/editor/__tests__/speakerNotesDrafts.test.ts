import assert from "node:assert/strict";
import test from "node:test";

import { mergeSpeakerNotesDrafts } from "@/components/editor/speakerNotesDrafts";

test("keeps an actual unsaved draft when canonical notes change", () => {
  const merged = mergeSpeakerNotesDrafts({
    currentDrafts: { slide1: "Draft from user" },
    previousSlides: [{ slideId: "slide1", speakerNotes: "Old canonical" }],
    currentSlides: [{ slideId: "slide1", speakerNotes: "New canonical" }],
  });

  assert.deepEqual(merged, { slide1: "Draft from user" });
});

test("replaces stale draft values when only canonical notes changed in the background", () => {
  const merged = mergeSpeakerNotesDrafts({
    currentDrafts: { slide1: "Old canonical" },
    previousSlides: [{ slideId: "slide1", speakerNotes: "Old canonical" }],
    currentSlides: [{ slideId: "slide1", speakerNotes: "New canonical" }],
  });

  assert.deepEqual(merged, { slide1: "New canonical" });
});

test("drops drafts for slides that no longer exist", () => {
  const merged = mergeSpeakerNotesDrafts({
    currentDrafts: { removed: "draft", kept: "still here" },
    previousSlides: [
      { slideId: "removed", speakerNotes: "draft" },
      { slideId: "kept", speakerNotes: "Old canonical" },
    ],
    currentSlides: [{ slideId: "kept", speakerNotes: "New canonical" }],
  });

  assert.deepEqual(merged, { kept: "still here" });
});

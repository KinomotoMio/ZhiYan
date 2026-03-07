import assert from "node:assert/strict";
import test from "node:test";

import {
  buildRevealPreviewSrc,
  getRevealPreviewSlideIndex,
} from "@/components/slides/RevealPreview";

test("buildRevealPreviewSrc keeps the blob URL unchanged for the first slide", () => {
  assert.equal(buildRevealPreviewSrc("blob:test-url", 0), "blob:test-url");
});

test("buildRevealPreviewSrc appends a reveal hash for later slides", () => {
  assert.equal(buildRevealPreviewSrc("blob:test-url", 1), "blob:test-url#/1");
});

test("buildRevealPreviewSrc normalizes invalid slide indexes", () => {
  assert.equal(buildRevealPreviewSrc("blob:test-url", -3), "blob:test-url");
  assert.equal(buildRevealPreviewSrc("blob:test-url", 2.8), "blob:test-url#/2");
});

test("getRevealPreviewSlideIndex accepts only reveal slidechange messages", () => {
  assert.equal(
    getRevealPreviewSlideIndex({ type: "reveal-preview-slidechange", slideIndex: 3.9 }),
    3
  );
  assert.equal(getRevealPreviewSlideIndex({ type: "other", slideIndex: 3 }), null);
  assert.equal(getRevealPreviewSlideIndex({ type: "reveal-preview-slidechange" }), null);
  assert.equal(getRevealPreviewSlideIndex(null), null);
});

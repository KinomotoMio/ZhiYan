import assert from "node:assert/strict";
import test from "node:test";

import {
  buildRevealPreviewHtml,
  buildRevealPreviewSrc,
  focusRevealPreviewFrame,
  getRevealPreviewSlideIndex,
  resolveRevealPreviewBehavior,
} from "@/components/slides/RevealPreview";

test("buildRevealPreviewSrc keeps the blob URL unchanged for the first slide", () => {
  assert.equal(
    buildRevealPreviewSrc("blob:test-url", { startSlide: 0 }),
    "blob:test-url?slide=0&mode=interactive"
  );
});

test("buildRevealPreviewSrc uses query params for slide selection and thumbnail mode", () => {
  assert.equal(
    buildRevealPreviewSrc("blob:test-url", { startSlide: 1, thumbnailMode: true }),
    "blob:test-url?slide=1&mode=thumbnail"
  );
});

test("buildRevealPreviewSrc normalizes invalid slide indexes", () => {
  assert.equal(
    buildRevealPreviewSrc("blob:test-url", { startSlide: -3 }),
    "blob:test-url?slide=0&mode=interactive"
  );
  assert.equal(
    buildRevealPreviewSrc("blob:test-url", { startSlide: 2.8 }),
    "blob:test-url?slide=2&mode=interactive"
  );
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

test("buildRevealPreviewHtml leaves document content intact", () => {
  const html = buildRevealPreviewHtml(
    "<!DOCTYPE html><html><head></head><body><div>deck</div></body></html>",
    { thumbnailMode: true }
  );

  assert.equal(html, "<!DOCTYPE html><html><head></head><body><div>deck</div></body></html>");
});

test("resolveRevealPreviewBehavior disables focus and slide sync for thumbnails", () => {
  assert.deepEqual(
    resolveRevealPreviewBehavior({
      thumbnailMode: true,
      autoFocusOnLoad: true,
      listenForSlideChange: true,
      hasSlideChangeHandler: true,
    }),
    {
      autoFocusOnLoad: false,
      listenForSlideChange: false,
    }
  );
});

test("focusRevealPreviewFrame focuses the iframe and its content window when available", () => {
  const calls: string[] = [];

  focusRevealPreviewFrame({
    focus: () => calls.push("frame"),
    contentWindow: {
      focus: () => calls.push("window"),
    },
  });

  assert.deepEqual(calls, ["frame", "window"]);
});

test("focusRevealPreviewFrame tolerates missing focus targets", () => {
  assert.doesNotThrow(() => focusRevealPreviewFrame(null));
  assert.doesNotThrow(() => focusRevealPreviewFrame({}));
  assert.doesNotThrow(() =>
    focusRevealPreviewFrame({
      focus: () => {
        throw new Error("blocked");
      },
      contentWindow: null,
    })
  );
});

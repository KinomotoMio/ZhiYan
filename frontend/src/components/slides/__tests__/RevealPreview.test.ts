import assert from "node:assert/strict";
import test from "node:test";

import {
  buildRevealPreviewHtml,
  buildRevealPreviewSrc,
  flushRevealPreviewUrlCleanupQueue,
  focusRevealPreviewFrame,
  getRevealPreviewSlideIndex,
  queueRevealPreviewUrlCleanup,
  resolveRevealPreviewBehavior,
  resolveRevealPreviewConfig,
} from "@/components/slides/RevealPreview";

test("buildRevealPreviewSrc keeps the blob URL unchanged for the first slide", () => {
  assert.equal(
    buildRevealPreviewSrc("blob:test-url", { startSlide: 0 }),
    "blob:test-url"
  );
});

test("resolveRevealPreviewConfig normalizes slide selection and thumbnail mode", () => {
  assert.deepEqual(resolveRevealPreviewConfig({ startSlide: 1, thumbnailMode: true }), {
    slide: 1,
    mode: "thumbnail",
  });
});

test("buildRevealPreviewSrc keeps Safari-safe bare blob URLs for later slides", () => {
  assert.equal(
    buildRevealPreviewSrc("blob:test-url", { startSlide: 1, thumbnailMode: true }),
    "blob:test-url"
  );
});

test("resolveRevealPreviewConfig normalizes invalid slide indexes", () => {
  assert.deepEqual(resolveRevealPreviewConfig({ startSlide: -3 }), {
    slide: 0,
    mode: "interactive",
  });
  assert.deepEqual(resolveRevealPreviewConfig({ startSlide: 2.8 }), {
    slide: 2,
    mode: "interactive",
  });
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

test("buildRevealPreviewHtml injects preview config into the document", () => {
  const html = buildRevealPreviewHtml(
    "<!DOCTYPE html><html><head></head><body><div>deck</div></body></html>",
    { startSlide: 4, thumbnailMode: true }
  );

  assert.match(html, /window\.__ZY_REVEAL_PREVIEW__/);
  assert.match(html, /"slide":4/);
  assert.match(html, /"mode":"thumbnail"/);
  assert.match(html, /<div>deck<\/div>/);
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

test("reveal preview URL cleanup keeps the active URL until the next document finishes loading", () => {
  const queued = queueRevealPreviewUrlCleanup([], "blob:old", "blob:new");
  assert.deepEqual(queued, ["blob:old"]);

  const revoked: string[] = [];
  const afterFlush = flushRevealPreviewUrlCleanupQueue(queued, "blob:new", (url) => {
    revoked.push(url);
  });

  assert.deepEqual(revoked, ["blob:old"]);
  assert.deepEqual(afterFlush, []);
});

test("reveal preview URL cleanup never revokes the active URL", () => {
  const revoked: string[] = [];
  const afterFlush = flushRevealPreviewUrlCleanupQueue(["blob:active"], "blob:active", (url) => {
    revoked.push(url);
  });

  assert.deepEqual(revoked, []);
  assert.deepEqual(afterFlush, ["blob:active"]);
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

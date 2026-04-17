import assert from "node:assert/strict";
import test from "node:test";

import {
  canHoverPreviewSource,
  getSourcePreviewKind,
  resolveHoverPreviewLayout,
} from "@/components/create/source-preview";

test("ready image sources use image preview mode", () => {
  assert.equal(
    getSourcePreviewKind({
      fileCategory: "image",
      status: "ready",
    }),
    "image"
  );
});

test("non-image or non-ready sources fall back to text preview mode", () => {
  assert.equal(
    getSourcePreviewKind({
      fileCategory: "pdf",
      status: "ready",
    }),
    "text"
  );
  assert.equal(
    getSourcePreviewKind({
      fileCategory: "image",
      status: "parsing",
    }),
    "text"
  );
});

test("hover preview is enabled for ready images and text snippets only", () => {
  assert.equal(
    canHoverPreviewSource({
      fileCategory: "image",
      previewSnippet: undefined,
      status: "ready",
    }),
    true
  );
  assert.equal(
    canHoverPreviewSource({
      fileCategory: "pdf",
      previewSnippet: "摘要",
      status: "ready",
    }),
    true
  );
  assert.equal(
    canHoverPreviewSource({
      fileCategory: "pdf",
      previewSnippet: undefined,
      status: "ready",
    }),
    false
  );
  assert.equal(
    canHoverPreviewSource({
      fileCategory: "image",
      previewSnippet: undefined,
      status: "parsing",
    }),
    false
  );
});

test("right placement keeps the hover preview on the trigger's right side", () => {
  const layout = resolveHoverPreviewLayout({
    triggerRect: {
      top: 280,
      left: 20,
      right: 380,
      bottom: 376,
      width: 360,
    },
    viewportWidth: 1600,
    viewportHeight: 900,
    placement: "right",
  });

  assert.equal(layout.left, 388);
  assert.equal(layout.top, 280);
  assert.equal(layout.width, 380);
  assert.equal(layout.maxHeight, 876);
});

test("right placement clamps horizontally when the viewport is tight", () => {
  const layout = resolveHoverPreviewLayout({
    triggerRect: {
      top: 120,
      left: 40,
      right: 290,
      bottom: 216,
      width: 250,
    },
    viewportWidth: 560,
    viewportHeight: 700,
    placement: "right",
  });

  assert.equal(layout.left, 248);
  assert.equal(layout.width, 300);
});

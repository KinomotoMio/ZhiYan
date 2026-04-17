import assert from "node:assert/strict";
import test from "node:test";

import {
  canHoverPreviewSource,
  getSourcePreviewKind,
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

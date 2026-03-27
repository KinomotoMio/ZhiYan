import assert from "node:assert/strict";
import test from "node:test";

import { resolveAspectContainSize } from "@/components/slides/HtmlPreviewSurface";

test("resolveAspectContainSize uses full height when the container is wider than 16:9", () => {
  assert.deepEqual(resolveAspectContainSize(1600, 600), {
    width: 1066,
    height: 600,
  });
});

test("resolveAspectContainSize uses full width when the container is taller than 16:9", () => {
  assert.deepEqual(resolveAspectContainSize(900, 900), {
    width: 900,
    height: 506,
  });
});

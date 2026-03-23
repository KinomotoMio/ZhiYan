import assert from "node:assert/strict";
import test from "node:test";

import { exportPptx, parsePptxExportMode } from "@/lib/api";
import type { Presentation } from "@/types/slide";

const samplePresentation: Presentation = {
  presentationId: "pres-1",
  title: "Demo",
  slides: [],
};

test("parsePptxExportMode defaults unknown values to structured", () => {
  assert.equal(parsePptxExportMode("fallback-image"), "fallback-image");
  assert.equal(parsePptxExportMode("structured"), "structured");
  assert.equal(parsePptxExportMode("unexpected"), "structured");
  assert.equal(parsePptxExportMode(null), "structured");
});

test("exportPptx returns blob with parsed export mode", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    new Response("pptx-bytes", {
      status: 200,
      headers: { "X-Zhiyan-Export-Mode": "fallback-image" },
    })) as typeof fetch;

  try {
    const result = await exportPptx(samplePresentation);
    assert.equal(result.mode, "fallback-image");
    assert.equal(await result.blob.text(), "pptx-bytes");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("exportPptx surfaces backend error detail for failed export", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    new Response(JSON.stringify({ detail: "uv run playwright install chromium" }), {
      status: 503,
      headers: { "Content-Type": "application/json" },
    })) as typeof fetch;

  try {
    await assert.rejects(
      () => exportPptx(samplePresentation),
      /uv run playwright install chromium/
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

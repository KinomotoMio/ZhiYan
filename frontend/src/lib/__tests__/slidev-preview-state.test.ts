import assert from "node:assert/strict";
import test from "node:test";

import { resolveSlidevPreviewState } from "@/lib/slidev-preview-state";

test("build url wins over stale pending render status", () => {
  const state = resolveSlidevPreviewState({
    buildUrl: "http://localhost:3000/api/v1/sessions/demo/presentations/latest/slidev/build",
    renderStatus: "pending",
    renderError: null,
  });

  assert.equal(state.previewReady, true);
  assert.equal(state.renderStatus, "ready");
  assert.equal(state.buildFailed, false);
  assert.equal(state.showBuildingState, false);
});

test("failed render without build stays on markdown fallback", () => {
  const state = resolveSlidevPreviewState({
    buildUrl: null,
    renderStatus: "failed",
    renderError: "Slidev build failed: broken css",
  });

  assert.equal(state.previewReady, false);
  assert.equal(state.renderStatus, "failed");
  assert.equal(state.buildFailed, true);
  assert.equal(state.showBuildingState, false);
  assert.match(state.renderError ?? "", /broken css/);
});

test("pending render without build stays in building state", () => {
  const state = resolveSlidevPreviewState({
    buildUrl: null,
    renderStatus: "pending",
    renderError: null,
  });

  assert.equal(state.previewReady, false);
  assert.equal(state.buildFailed, false);
  assert.equal(state.showBuildingState, true);
});

test("helper models first-load hydration where slidev payload is newer than session detail", () => {
  const detailRenderStatus = "pending";
  const slidevPayload = {
    build_url: "/api/v1/sessions/demo/presentations/latest/slidev/build",
    render_status: "pending",
    render_error: null,
  };

  const state = resolveSlidevPreviewState({
    buildUrl: slidevPayload.build_url,
    renderStatus: slidevPayload.render_status ?? detailRenderStatus,
    renderError: slidevPayload.render_error,
  });

  assert.equal(state.previewReady, true);
  assert.equal(state.renderStatus, "ready");
});

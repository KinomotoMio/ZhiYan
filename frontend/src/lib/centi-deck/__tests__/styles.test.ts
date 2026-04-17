import assert from "node:assert/strict";
import test from "node:test";

import { getCentiDeckRuntimeStyles } from "@/lib/centi-deck/styles";

test("centi-deck runtime styles hide inactive slides and expose active slide", () => {
  const css = getCentiDeckRuntimeStyles();

  assert.match(css, /\.centi-deck-slide\s*\{/);
  assert.match(css, /opacity:\s*0/);
  assert.match(css, /\.centi-deck-slide\.is-active\s*\{/);
  assert.match(css, /pointer-events:\s*auto/);
  assert.match(css, /\.centi-deck-slide\.is-exiting\s*\{/);
});

test("centi-deck runtime styles disable transition effects in thumbnail-like modes", () => {
  const css = getCentiDeckRuntimeStyles();

  assert.match(css, /data-centi-mode="thumbnail"/);
  assert.match(css, /data-centi-mode="presenter"/);
  assert.match(css, /data-centi-mode="print"/);
  assert.match(css, /transition:\s*none !important/);
});

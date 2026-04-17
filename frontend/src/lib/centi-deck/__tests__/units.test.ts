import assert from "node:assert/strict";
import test from "node:test";

import { rewriteViewportUnits } from "@/lib/centi-deck/units";

test("rewriteViewportUnits rewrites bare vh/vw/vmin/vmax to container-query units", () => {
  assert.equal(rewriteViewportUnits("height: 100vh;"), "height: 100cqh;");
  assert.equal(rewriteViewportUnits("width: 50vw;"), "width: 50cqw;");
  assert.equal(rewriteViewportUnits("font-size: 3vmin;"), "font-size: 3cqmin;");
  assert.equal(rewriteViewportUnits("gap: 2vmax;"), "gap: 2cqmax;");
});

test("rewriteViewportUnits preserves decimal values and handles calc()", () => {
  assert.equal(
    rewriteViewportUnits("padding: calc(100vh - 40px);"),
    "padding: calc(100cqh - 40px);"
  );
  assert.equal(rewriteViewportUnits("height: 1.5vh;"), "height: 1.5cqh;");
});

test("rewriteViewportUnits rewrites every occurrence inside a <style> block", () => {
  const input = `.cover { min-height: 100vh; width: 80vw; }
.title { font-size: 4vmin; letter-spacing: 0.5vmax; }`;
  const expected = `.cover { min-height: 100cqh; width: 80cqw; }
.title { font-size: 4cqmin; letter-spacing: 0.5cqmax; }`;
  assert.equal(rewriteViewportUnits(input), expected);
});

test("rewriteViewportUnits does not touch look-alike identifiers", () => {
  // dvh / lvh / svh are distinct dynamic/large/small viewport units — but our slides
  // almost never use them, and the current runtime doesn't claim to rewrite them.
  assert.equal(rewriteViewportUnits("height: 100dvh;"), "height: 100dvh;");
  assert.equal(rewriteViewportUnits("height: 100svh;"), "height: 100svh;");
  assert.equal(rewriteViewportUnits("height: 100lvh;"), "height: 100lvh;");

  // The bare word `vh` without a leading digit must stay intact (class name, custom ident).
  assert.equal(rewriteViewportUnits(".vh-helper { color: red; }"), ".vh-helper { color: red; }");
  assert.equal(rewriteViewportUnits("--vh-offset: 12px;"), "--vh-offset: 12px;");
});

test("rewriteViewportUnits on empty / non-string input is a no-op", () => {
  assert.equal(rewriteViewportUnits(""), "");
});

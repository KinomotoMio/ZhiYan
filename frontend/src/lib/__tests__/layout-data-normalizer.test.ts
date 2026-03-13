import assert from "node:assert/strict";
import test from "node:test";

import { normalizeLayoutData } from "@/lib/layout-data-normalizer";

test("normalizeLayoutData repairs outline-slide items alias and pads to four sections", () => {
  const result = normalizeLayoutData("outline-slide", {
    title: "Agenda",
    items: [
      { title: "Background", description: "Context" },
      { label: "Method" },
      "Findings",
    ],
  });

  assert.equal(result.recoverable, true);
  assert.equal(result.changed, true);
  assert.equal(result.reason, "normalize outline shape");
  assert.equal((result.data.sections as unknown[]).length, 4);
  assert.deepEqual(result.data.sections, [
    { title: "Background", description: "Context" },
    { title: "Method" },
    { title: "Findings" },
    { title: "结论" },
  ]);
});

test("normalizeLayoutData trims outline-slide sections to six entries", () => {
  const result = normalizeLayoutData("outline-slide", {
    title: "Agenda",
    sections: [
      { title: "One" },
      { title: "Two" },
      { title: "Three" },
      { title: "Four" },
      { title: "Five" },
      { title: "Six" },
      { title: "Seven" },
    ],
  });

  assert.equal(result.recoverable, true);
  assert.equal((result.data.sections as unknown[]).length, 6);
  assert.deepEqual(result.data.sections, [
    { title: "One" },
    { title: "Two" },
    { title: "Three" },
    { title: "Four" },
    { title: "Five" },
    { title: "Six" },
  ]);
});
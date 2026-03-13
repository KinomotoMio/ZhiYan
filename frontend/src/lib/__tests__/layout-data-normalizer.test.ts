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
test("normalizeLayoutData repairs executive-summary metrics-slide items without losing the new fields", () => {
  const result = normalizeLayoutData("metrics-slide", {
    title: "Quarterly Snapshot",
    conclusion: "Enterprise adoption is no longer the bottleneck.",
    conclusionBrief: "Review latency is now the next constraint.",
    metrics: [
      { metric: "92%", title: "Adoption", detail: "active team usage" },
      { value: "14d", label: "Lead Time", description: "from brief to deck" },
    ],
  });

  assert.equal(result.recoverable, true);
  assert.equal(result.changed, true);
  assert.equal(result.reason, "normalize metrics-slide shape");
  assert.deepEqual(result.data, {
    title: "Quarterly Snapshot",
    conclusion: "Enterprise adoption is no longer the bottleneck.",
    conclusionBrief: "Review latency is now the next constraint.",
    metrics: [
      { value: "92%", label: "Adoption", description: "active team usage" },
      { value: "14d", label: "Lead Time", description: "from brief to deck" },
    ],
  });
});

test("normalizeLayoutData keeps legacy metrics-slide readable without fabricating summary copy", () => {
  const result = normalizeLayoutData("metrics-slide", {
    title: "Legacy Snapshot",
    metrics: [
      { value: "88%", label: "Coverage", description: "workspace adoption" },
      { value: "11d", label: "Lead Time", description: "last quarter average" },
    ],
  });

  assert.equal(result.recoverable, true);
  assert.equal(result.changed, false);
  assert.equal("conclusion" in result.data, false);
  assert.equal("conclusionBrief" in result.data, false);
});

test("normalizeLayoutData keeps bullet-with-icons items when identical text is real content", () => {
  const result = normalizeLayoutData("bullet-with-icons", {
    title: "Team habits",
    items: [
      { title: "Same text", description: "Same text" },
      { title: "Also same", description: "Also same" },
      { title: "Third same", description: "Third same" },
      { title: "Fourth same", description: "Fourth same" },
    ],
  });

  assert.equal(result.recoverable, true);
  assert.equal(result.changed, true);
  assert.deepEqual(result.data, {
    title: "Team habits",
    items: [
      { icon: { query: "star" }, title: "Same text", description: "Same text" },
      { icon: { query: "star" }, title: "Also same", description: "Also same" },
      { icon: { query: "star" }, title: "Third same", description: "Third same" },
      { icon: { query: "star" }, title: "Fourth same", description: "Fourth same" },
    ],
  });
});

test("normalizeLayoutData collapses placeholder-only bullet-with-icons items into status state", () => {
  const result = normalizeLayoutData("bullet-with-icons", {
    title: "Auto fallback",
    items: [
      { title: "内容生成中", description: "内容生成中" },
      { title: "待补充", description: "待补充" },
    ],
  });

  assert.equal(result.recoverable, true);
  assert.equal(result.changed, true);
  assert.deepEqual(result.data, {
    title: "Auto fallback",
    items: [],
    status: {
      title: "内容暂未就绪",
      message: "该页正在生成或已回退，可稍后重试。",
    },
  });
});

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { LayoutCatalogClientPage } from "@/app/dev/layout-catalog/LayoutCatalogClient";
import { getLayoutVariant } from "@/lib/layout-variant";
import { getAllLayouts, getLayout } from "@/lib/template-registry";

const sharedLayoutMetadata = JSON.parse(
  readFileSync(
    new URL("../../../../shared/layout-metadata.json", import.meta.url),
    "utf8",
  ),
) as {
  layouts: Record<
    string,
    {
      group: string;
      subGroup: string;
      variant: {
        composition: string;
        tone: string;
        style: string;
        density: string;
      };
      notes: {
        purpose: string;
        structure_signal: string;
        design_signal: string;
        use_when: string;
        avoid_when: string;
        usage_bias: string;
      };
    }
  >;
};

test("template registry exposes usage metadata for built-in layouts", () => {
  const outline = getLayout("outline-slide");
  assert.ok(outline);
  assert.equal(outline.group, "agenda");
  assert.equal(outline.subGroup, "default");
  assert.deepEqual(outline.variant, {
    composition: "card-grid",
    tone: "formal",
    style: "card-based",
    density: "medium",
  });
  assert.equal(
    outline.notes.purpose,
    "用于交代整份演示的章节骨架，不负责深入解释单个章节内容。",
  );
  assert.match(outline.description, /章节骨架/);
  assert.deepEqual(outline.usage, [
    "academic-report",
    "business-report",
    "training-workshop",
    "conference-keynote",
    "project-status",
    "investor-pitch",
  ]);

  const layouts = getAllLayouts();
  const metrics = layouts.find((entry) => entry.id === "metrics-slide");
  assert.ok(metrics);
  assert.equal(metrics.group, "evidence");
  assert.equal(metrics.subGroup, "default");
  assert.deepEqual(metrics.variant, {
    composition: "stat-grid",
    tone: "formal",
    style: "data-first",
    density: "medium",
  });
  assert.equal(metrics.usage.includes("academic-report"), true);
  assert.equal(metrics.usage.includes("project-status"), true);

  const narrative = layouts.find((entry) => entry.id === "bullet-with-icons");
  assert.ok(narrative);
  assert.equal(narrative.group, "narrative");
  assert.equal(narrative.subGroup, "icon-points");
  assert.deepEqual(narrative.variant, {
    composition: "icon-columns",
    tone: "assertive",
    style: "icon-led",
    density: "medium",
  });
});

test("legacy layout variant helper remains available as a compatibility wrapper", () => {
  assert.equal(getLayoutVariant("bullet-with-icons"), "icon-points");
  assert.equal(getLayoutVariant("outline-slide"), "default");
});

test("template registry matches shared metadata for all layouts", () => {
  const allSharedLayoutIds = Object.keys(sharedLayoutMetadata.layouts);
  const allRuntimeLayoutIds = getAllLayouts().map((entry) => entry.id);

  assert.deepEqual(
    allRuntimeLayoutIds.sort(),
    allSharedLayoutIds.sort(),
    "Mismatch between layouts in frontend registry and shared metadata",
  );

  for (const layoutId of allSharedLayoutIds) {
    const runtime = getLayout(layoutId);
    assert.ok(runtime, `Layout '${layoutId}' should be available in registry`);

    const expected = sharedLayoutMetadata.layouts[layoutId];
    assert.equal(runtime.group, expected.group);
    assert.equal(runtime.subGroup, expected.subGroup);
    assert.deepEqual(runtime.variant, expected.variant);
    assert.deepEqual(runtime.notes, expected.notes);
    assert.equal(runtime.description, expected.notes.purpose);
  }
});

test("layout catalog renders template previews and variable information", () => {
  const html = renderToStaticMarkup(createElement(LayoutCatalogClientPage));

  assert.doesNotMatch(html, /<th[^>]*>Group<\/th>/);
  assert.doesNotMatch(html, /<th[^>]*>Runtime Variant<\/th>/);
  assert.doesNotMatch(html, /<th[^>]*>Reviewed Sub-group<\/th>/);
  assert.doesNotMatch(html, /<th[^>]*>Reviewed Variant<\/th>/);
  assert.doesNotMatch(html, /Role Contract/);
  assert.doesNotMatch(html, /Narrative Variant Pilot/);
  assert.doesNotMatch(html, /Reviewed Taxonomy Baseline/);
  assert.match(html, /<th[^>]*>Usage<\/th>/);
  assert.match(html, /学术汇报/);
  assert.match(html, /商业汇报/);
  assert.match(html, /融资路演/);
  assert.match(html, /Runtime notes/);
  assert.match(html, /shared metadata six-slot contract/);
  assert.match(html, /Purpose/);
  assert.match(html, /Structure/);
  assert.match(html, /Design/);
  assert.match(html, /Use when/);
  assert.match(html, /Avoid when/);
  assert.match(html, /Usage bias/);
  assert.match(html, /用于建立演示开场身份与主题/);
  assert.match(html, /当内容天然是 3-4 个并列卖点、能力点或结论点时使用/);
  assert.match(html, /Built-in slide layouts/);
  assert.match(
    html,
    /Use it as a compact template directory rather than a taxonomy migration workspace\./,
  );
  assert.match(html, /frontend\/src\/components\/slide-layouts\/IntroSlideLayout\.tsx/);
  assert.match(html, /title/);
  assert.match(html, /sections\[4-6\]/);

  assert.notEqual(html.indexOf("bullet-icons-only"), -1);
  assert.notEqual(html.indexOf("bullet-with-icons"), -1);
  assert.notEqual(html.indexOf("image-and-description"), -1);
});

import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { LayoutCatalogClientPage } from "@/app/dev/layout-catalog/LayoutCatalogClient";
import { getAllLayouts, getLayout } from "@/lib/template-registry";

test("template registry exposes usage metadata for built-in layouts", () => {
  const outline = getLayout("outline-slide");
  assert.ok(outline);
  assert.equal(outline.group, "agenda");
  assert.equal(outline.variant, "default");
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
  assert.equal(metrics.variant, "default");
  assert.equal(metrics.usage.includes("academic-report"), true);
  assert.equal(metrics.usage.includes("project-status"), true);

  const narrative = layouts.find((entry) => entry.id === "bullet-with-icons");
  assert.ok(narrative);
  assert.equal(narrative.group, "narrative");
  assert.equal(narrative.variant, "icon-points");
});

test("layout catalog renders role-based group and variant metadata", () => {
  const html = renderToStaticMarkup(createElement(LayoutCatalogClientPage));

  assert.match(html, /<th[^>]*>Group<\/th>/);
  assert.match(html, /<th[^>]*>Variant<\/th>/);
  assert.match(html, /Role Contract/);
  assert.match(html, /Narrative Variant Pilot/);
  assert.match(html, /封面/);
  assert.match(html, /目录/);
  assert.match(html, /Variant pilot/);
  assert.match(html, /图标要点/);
  assert.match(html, /图文说明/);
  assert.match(html, /能力网格/);
  assert.match(html, /icon-points/);
  assert.match(html, /default/);
  assert.match(html, /section-divider/);
  assert.match(html, /agenda/);
  assert.match(html, /evidence/);
  assert.match(html, /<th[^>]*>Usage<\/th>/);
  assert.match(html, /学术汇报/);
  assert.match(html, /商业汇报/);
  assert.match(html, /融资路演/);

  const bulletIconsOnly = html.indexOf("bullet-icons-only");
  const bulletWithIcons = html.indexOf("bullet-with-icons");
  const imageAndDescription = html.indexOf("image-and-description");

  assert.notEqual(bulletIconsOnly, -1);
  assert.notEqual(bulletWithIcons, -1);
  assert.notEqual(imageAndDescription, -1);
  assert.ok(imageAndDescription < bulletWithIcons);
  assert.ok(bulletWithIcons < bulletIconsOnly);
});

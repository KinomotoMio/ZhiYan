import assert from "node:assert/strict";
import test from "node:test";

import { presentationToRevealHTML } from "@/lib/slide-to-reveal";
import type { Presentation } from "@/types/slide";

const basePresentation: Presentation = {
  presentationId: "pres-1",
  title: "Demo",
  slides: [
    {
      slideId: "slide-1",
      layoutType: "intro-slide",
      layoutId: "intro-slide",
      contentData: {
        title: "Cover",
        subtitle: "Subtitle",
      },
      components: [],
    },
    {
      slideId: "slide-2",
      layoutType: "metrics-slide",
      layoutId: "metrics-slide",
      contentData: {
        title: "Metrics",
        metrics: [{ value: "10%", label: "Growth" }],
      },
      components: [],
    },
  ],
};

test("presentationToRevealHTML keeps reveal section positioning intact and emits slide change updates", () => {
  const html = presentationToRevealHTML(basePresentation, { startSlide: 1 });

  assert.match(html, /<section data-slide-id="slide-1">/);
  assert.doesNotMatch(html, /<section data-slide-id="slide-1" style=/);
  assert.match(html, /class="slide-shell"/);
  assert.ok(html.includes("hash: true"));
  assert.ok(html.includes("reveal-preview-slidechange"));
  assert.ok(html.includes("deck.on('ready', notifySlideChange)"));
  assert.ok(html.includes("deck.on('slidechanged', notifySlideChange)"));
  assert.doesNotMatch(html, /const initialSlideIndex = 1/);
  assert.doesNotMatch(html, /deck.slide(initialSlideIndex)/);
  assert.doesNotMatch(html, /reveal-preview-close/);
});

test("presentationToRevealHTML normalizes malformed compare layout data", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [
      {
        slideId: "slide-compare",
        layoutType: "two-column-compare",
        layoutId: "two-column-compare",
        contentData: {
          title: "Compare",
          items: [
            { title: "Point One", description: "Desc One" },
            { title: "Point Two", description: "Desc Two" },
          ],
        },
        components: [],
      },
    ],
  });

  assert.ok(html.includes("Compare"));
  assert.ok(html.includes("A"));
  assert.ok(html.includes("B"));
});

test("presentationToRevealHTML renders a fallback message for unrecoverable layout data", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [
      {
        slideId: "slide-table",
        layoutType: "table-info",
        layoutId: "table-info",
        contentData: {
          title: "Broken table",
          rows: [],
        },
        components: [],
      },
    ],
  });

  assert.ok(html.includes("????"));
  assert.ok(html.includes("????????"));
});

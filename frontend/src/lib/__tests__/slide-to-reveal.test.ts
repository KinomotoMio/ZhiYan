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
  const html = presentationToRevealHTML(basePresentation);

  assert.match(html, /<section data-slide-id="slide-1">/);
  assert.doesNotMatch(html, /<section data-slide-id="slide-1" style=/);
  assert.match(html, /class="slide-shell"/);
  assert.ok(html.includes("hash: true"));
  assert.ok(html.includes("reveal-preview-slidechange"));
  assert.ok(html.includes("deck.on('ready', notifySlideChange)"));
  assert.ok(html.includes("deck.on('slidechanged', notifySlideChange)"));
  assert.ok(html.includes("window.location.origin"));
  assert.doesNotMatch(html, /const initialSlideIndex = 1/);
  assert.doesNotMatch(html, /deck.slide(initialSlideIndex)/);
  assert.doesNotMatch(html, /reveal-preview-close/);
});

test("presentationToRevealHTML escapes slide identifiers and sanitizes theme colors", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    theme: {
      primaryColor: "red; </style><script>alert(1)</script><style>",
      backgroundColor: "#12345z",
    },
    slides: [
      {
        ...basePresentation.slides[0],
        slideId: '"><script>alert(1)</script>',
      },
    ],
  });

  assert.ok(html.includes('data-slide-id="&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;"'));
  assert.ok(html.includes("--primary-color: #3b82f6;"));
  assert.ok(html.includes("--background-color: #ffffff;"));
  assert.ok(!html.includes("<script>alert(1)</script>"));
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

  assert.ok(html.includes("Slide data is unavailable in presentation mode."));
});

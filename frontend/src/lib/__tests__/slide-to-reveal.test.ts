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
  assert.ok(html.includes("margin: 0,"));
  assert.ok(html.includes("center: false,"));
  assert.ok(html.includes("padding: 0 !important;"));
  assert.ok(html.includes("<div class=\"reveal\" tabindex=\"-1\">"));
  assert.ok(html.includes("const revealElement = document.querySelector('.reveal');"));
  assert.ok(html.includes("reveal-preview-slidechange"));
  assert.ok(html.includes("window.requestAnimationFrame(focusRevealSurface)"));
  assert.ok(html.includes("deck.on('ready', () => {"));
  assert.ok(html.includes("deck.on('slidechanged', notifySlideChange)"));
  assert.ok(html.includes("window.location.origin"));
  assert.doesNotMatch(html, /margin: 0\.04,/);
  assert.doesNotMatch(html, /const initialSlideIndex = 1/);
  assert.doesNotMatch(html, /deck.slide\(initialSlideIndex\)/);
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
        slideId: '\"><script>alert(1)</script>',
      },
    ],
  });

  assert.ok(html.includes('data-slide-id="&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;"'));
  assert.ok(html.includes("--primary-color: #3b82f6;"));
  assert.ok(html.includes("--background-color: #ffffff;"));
  assert.ok(!html.includes("<script>alert(1)</script>"));
});

test("presentationToRevealHTML keeps intro-slide title on background text colors", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [basePresentation.slides[0]],
  });

  assert.match(html, /font-size:52px;font-weight:700;line-height:1\.2;color:var\(--background-text,#111827\)/);
  assert.doesNotMatch(html, /font-size:52px;font-weight:700;line-height:1\.2;color:var\(--primary-color,#3b82f6\)/);
  assert.match(html, /color:color-mix\(in srgb, var\(--background-text,#111827\) 60%, transparent\)/);
});

test("presentationToRevealHTML renders inline svg icons for bullet-with-icons layouts", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [
      {
        slideId: "slide-icons",
        layoutType: "bullet-with-icons",
        layoutId: "bullet-with-icons",
        contentData: {
          title: "Capabilities",
          items: [
            {
              icon: { query: "zap" },
              title: "Automation",
              description: "Automates repeated work",
            },
          ],
        },
        components: [],
      },
    ],
  });

  assert.match(html, /Capabilities/);
  assert.match(html, /Automation/);
  assert.match(html, /Automates repeated work/);
  assert.match(html, /<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg" width="28" height="28"/);
  assert.doesNotMatch(html, /<p style="font-size:22px;font-weight:600;margin-bottom:8px;">Automation<\/p>/);
});

test("presentationToRevealHTML preserves icon-bearing compare columns and section decorations", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [
      {
        slideId: "slide-section",
        layoutType: "section-header",
        layoutId: "section-header",
        contentData: {
          title: "Roadmap",
          subtitle: "What comes next",
        },
        components: [],
      },
      {
        slideId: "slide-compare",
        layoutType: "two-column-compare",
        layoutId: "two-column-compare",
        contentData: {
          title: "Compare",
          left: {
            heading: "Current",
            icon: { query: "target" },
            items: ["Manual workflow"],
          },
          right: {
            heading: "Future",
            icon: { query: "rocket" },
            items: ["Automated workflow"],
          },
        },
        components: [],
      },
    ],
  });

  assert.match(html, /width:48px;height:4px;border-radius:9999px;background:var\(--primary-color,#3b82f6\);margin-bottom:32px;/);
  assert.match(html, /Roadmap/);
  assert.match(html, /What comes next/);
  assert.match(html, /Current/);
  assert.match(html, /Future/);
  assert.ok((html.match(/<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg" width="24" height="24"/g) ?? []).length >= 2);
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
  assert.match(html, /(Point A|要点 A)/);
  assert.match(html, /(Point B|要点 B)/);
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

test("presentationToRevealHTML renders outline-slide as a two-column agenda layout", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [
      {
        slideId: "slide-outline",
        layoutType: "outline-slide",
        layoutId: "outline-slide",
        contentData: {
          title: "Presentation Outline",
          subtitle: "A quick way to preview the report structure.",
          sections: [
            { title: "Background", description: "Why this matters" },
            { title: "Method", description: "How we approached it" },
            { title: "Findings", description: "What we observed" },
            { title: "Results", description: "What changed" },
            { title: "Next Steps", description: "How to proceed" },
          ],
        },
        components: [],
      },
    ],
  });

  assert.match(html, /Presentation Outline/);
  assert.match(html, /Background/);
  assert.match(html, /Next Steps/);
  assert.match(html, /display:flex;gap:56px;flex:1;margin-top:48px;/);
  assert.ok(html.includes(">01<"));
  assert.ok(html.includes(">05<"));
  assert.doesNotMatch(html, /grid-template-columns:repeat\(3,minmax\(0,1fr\)\)/);
  assert.doesNotMatch(html, /shadow-\[/);
});
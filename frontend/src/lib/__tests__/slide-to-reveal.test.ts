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

test("presentationToRevealHTML renders outline-slide as a two-column agenda layout", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [
      {
        slideId: "slide-outline",
        layoutType: "outline-slide",
        layoutId: "outline-slide",
        contentData: {
          title: "Report Outline",
          subtitle: "Background, method, findings, results, and conclusions.",
          sections: [
            { title: "Background", description: "Context and problem framing" },
            { title: "Method", description: "Approach and data collection" },
            { title: "Findings", description: "Patterns and notable changes" },
            { title: "Results", description: "Business impact and recommendations" },
          ],
        },
        components: [],
      },
    ],
  });

  assert.match(html, /Report Outline/);
  assert.match(html, /display:flex;gap:56px;flex:1;margin-top:48px;/);
  assert.match(html, /grid-template-rows:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(html, /Context and problem framing/);
  assert.match(html, /border-top:1px solid/);
  assert.match(html, /Background/);
  assert.match(html, /Results/);
});
test("presentationToRevealHTML keeps bullet-with-icons columns aligned with the preview layout", () => {
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
  assert.match(html, /font-size:36px;font-weight:700;line-height:1\.3/);
  assert.match(html, /Automation[\s\S]*Automates repeated work[\s\S]*01/);
  assert.match(html, /grid-template-columns:repeat\(3,minmax\(0,1fr\)\)/);
  assert.match(html, /position:absolute;left:0;top:50%/);
  assert.match(html, /height:50%/);
  assert.match(html, /width:40px;height:40px;border-radius:9999px;background:color-mix\(in srgb, var\(--primary-color,#3b82f6\) 12%, transparent\)/);
  assert.match(html, /<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg" width="20" height="20"/);
  assert.match(html, /font-size:21px;font-weight:700;line-height:1\.08;letter-spacing:-0\.04em;color:var\(--primary-color,#3b82f6\)/);
  assert.match(html, /background:color-mix\(in srgb, var\(--primary-color,#3b82f6\) 7%, transparent\);border-radius:3px;padding:0\.05em 0\.22em 0\.12em;box-decoration-break:clone/);
  assert.doesNotMatch(html, /width:56px;height:56px/);
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

test("presentationToRevealHTML renders bullet-icons-only as a denser matrix with oversized icon blocks", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [
      {
        slideId: "slide-icons-only",
        layoutType: "bullet-icons-only",
        layoutId: "bullet-icons-only",
        contentData: {
          title: "Platform Capabilities",
          items: [
            { icon: { query: "database" }, label: "Unified Data Layer" },
            { icon: { query: "shield" }, label: "Access Control" },
            { icon: { query: "bot" }, label: "Agent Orchestration" },
            { icon: { query: "workflow" }, label: "Process Automation" },
          ],
        },
        components: [],
      },
    ],
  });

  assert.match(html, /Platform Capabilities/);
  assert.match(html, /grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(html, /column-gap:40px;row-gap:22px/);
  assert.match(html, /min-height:92px/);
  assert.match(html, /width:72px;height:72px/);
  assert.match(html, /width="40" height="40"/);
  assert.match(html, /letter-spacing:0.24em/);
  assert.match(html, /Unified Data Layer/);
  assert.match(html, /Agent Orchestration/);
  assert.match(html, />01<\/div>/);
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

test("presentationToRevealHTML distinguishes ai, user, and existing image placeholders", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [
      {
        slideId: "slide-ai",
        layoutType: "metrics-with-image",
        layoutId: "metrics-with-image",
        contentData: {
          title: "AI Image",
          metrics: [{ value: "92%", label: "Match" }],
          image: { source: "ai", prompt: "modern office with analytics dashboard" },
        },
        components: [],
      },
      {
        slideId: "slide-user",
        layoutType: "image-and-description",
        layoutId: "image-and-description",
        contentData: {
          title: "User Image",
          description: "Needs a real-world photo.",
          image: { source: "user", prompt: "\u8bf7\u4e0a\u4f20\u95e8\u5e97\u5b9e\u62cd\u7167\u7247" },
        },
        components: [],
      },
      {
        slideId: "slide-existing",
        layoutType: "image-and-description",
        layoutId: "image-and-description",
        contentData: {
          title: "Existing Asset",
          description: "Should bind an existing gallery asset.",
          image: { source: "existing", prompt: "\u4f7f\u7528\u54c1\u724c\u56fe\u5e93\u5c01\u9762\u56fe" },
        },
        components: [],
      },
    ],
  });

  assert.match(html, /\u5f85\u7528\u6237\u8865\u56fe\/\u4e0a\u4f20/);
  assert.match(html, /\u8bf7\u4e0a\u4f20\u95e8\u5e97\u5b9e\u62cd\u7167\u7247/);
  assert.match(html, /\u5f85\u7ed1\u5b9a\u73b0\u6709\u7d20\u6750/);
  assert.match(html, /\u4f7f\u7528\u54c1\u724c\u56fe\u5e93\u5c01\u9762\u56fe/);
  assert.match(html, /modern office with analytics dashboard/);
});

test("presentationToRevealHTML prioritizes image urls over source placeholders", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [
      {
        slideId: "slide-url",
        layoutType: "metrics-with-image",
        layoutId: "metrics-with-image",
        contentData: {
          title: "Resolved Image",
          metrics: [{ value: "42", label: "Score" }],
          image: {
            source: "user",
            prompt: "\u8fd9\u884c\u6587\u6848\u4e0d\u5e94\u663e\u793a",
            url: "https://example.com/image.png",
          },
        },
        components: [],
      },
    ],
  });

  assert.match(html, /<img src="https:\/\/example\.com\/image\.png"/);
  assert.doesNotMatch(html, /\u5f85\u7528\u6237\u8865\u56fe\/\u4e0a\u4f20/);
});

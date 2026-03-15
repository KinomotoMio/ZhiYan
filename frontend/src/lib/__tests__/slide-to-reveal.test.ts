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

test("presentationToRevealHTML renders bullet-with-icons status panels", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [
      {
        slideId: "slide-status",
        layoutType: "bullet-with-icons",
        layoutId: "bullet-with-icons",
        contentData: {
          title: "关键发现",
          items: [],
          status: {
            title: "内容暂未就绪",
            message: "该页正在生成或已回退，可稍后重试。",
          },
        },
        components: [],
      },
    ],
  });

  assert.match(html, /关键发现/);
  assert.match(html, /内容暂未就绪/);
  assert.match(html, /该页正在生成或已回退，可稍后重试。/);
  assert.doesNotMatch(html, /grid-template-columns:repeat\(0,minmax\(0,1fr\)\)/);
});

test("presentationToRevealHTML canonicalizes legacy fallback placeholder aliases", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [
      {
        slideId: "slide-compare-alias",
        layoutType: "two-column-compare",
        layoutId: "two-column-compare",
        contentData: {
          title: "Compare",
          items: ["Content unavailable", "Pending"],
        },
        components: [],
      },
      {
        slideId: "slide-challenge-alias",
        layoutType: "challenge-outcome",
        layoutId: "challenge-outcome",
        contentData: {
          title: "问题与方案",
          items: [{ challenge: "Content unavailable", outcome: "Pending" }],
        },
        components: [],
      },
    ],
  });

  assert.match(html, /内容生成中/);
  assert.match(html, /待补充/);
  assert.doesNotMatch(html, /Content unavailable/);
  assert.doesNotMatch(html, /Fallback generated/);
});

test("presentationToRevealHTML preserves legitimate english pending content", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [
      {
        slideId: "slide-pending-compare",
        layoutType: "two-column-compare",
        layoutId: "two-column-compare",
        contentData: {
          title: "Workflow",
          items: ["Security review", "Pending"],
        },
        components: [],
      },
      {
        slideId: "slide-pending-bullet",
        layoutType: "bullet-with-icons",
        layoutId: "bullet-with-icons",
        contentData: {
          title: "Status",
          items: [
            { icon: { query: "clock-3" }, title: "Pending", description: "Awaiting approval" },
            { icon: { query: "shield" }, title: "Approved", description: "Security cleared" },
            { icon: { query: "rocket" }, title: "Ready", description: "Queued for launch" },
          ],
        },
        components: [],
      },
    ],
  });

  assert.match(html, /Security review/);
  assert.match(html, />Pending</);
  assert.match(html, /Awaiting approval/);
  assert.doesNotMatch(html, /待补充/);
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

test("presentationToRevealHTML renders metrics-slide executive summary and legacy fallback", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [
      {
        slideId: "slide-metrics-summary",
        layoutType: "metrics-slide",
        layoutId: "metrics-slide",
        contentData: {
          title: "Quarterly Snapshot",
          conclusion: "Enterprise adoption is no longer the bottleneck.",
          conclusionBrief: "Coverage expanded across the org, so review latency is the next constraint.",
          metrics: [
            { value: "92%", label: "Adoption", description: "active team usage" },
            { value: "14d", label: "Lead Time", description: "from brief to deck" },
          ],
        },
        components: [],
      },
      {
        slideId: "slide-metrics-legacy",
        layoutType: "metrics-slide",
        layoutId: "metrics-slide",
        contentData: {
          title: "Legacy Snapshot",
          metrics: [
            { value: "3.6x", label: "Reuse", description: "template leverage" },
            { value: "11", label: "Teams", description: "pilot rollout" },
          ],
        },
        components: [],
      },
    ],
  });

  assert.match(html, /Enterprise adoption is no longer the bottleneck\./);
  assert.match(html, /Coverage expanded across the org, so review latency is the next constraint\./);
  assert.match(html, /min-height:168px/);
  assert.match(html, /Legacy Snapshot/);
  assert.match(html, /grid-template-columns:repeat\(2,minmax\(0,1fr\)\);gap:32px/);
  assert.match(html, /template leverage/);
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

test("presentationToRevealHTML uses a generic alt fallback for metrics-with-image urls", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [
      {
        slideId: "slide-metrics-url-alt",
        layoutType: "metrics-with-image",
        layoutId: "metrics-with-image",
        contentData: {
          title: "Resolved Image",
          metrics: [{ value: "42", label: "Score" }],
          image: {
            source: "ai",
            prompt: "",
            url: "https://example.com/metrics-image.png",
          },
        },
        components: [],
      },
    ],
  });

  assert.match(html, /<img src="https:\/\/example\.com\/metrics-image\.png" alt="Image"/);
});

test("presentationToRevealHTML uses a generic alt fallback for image-and-description urls", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [
      {
        slideId: "slide-description-url-alt",
        layoutType: "image-and-description",
        layoutId: "image-and-description",
        contentData: {
          title: "Resolved Image",
          description: "Has a real image URL.",
          image: {
            source: "ai",
            prompt: "",
            url: "https://example.com/description-image.png",
          },
        },
        components: [],
      },
    ],
  });

  assert.match(html, /<img src="https:\/\/example\.com\/description-image\.png" alt="Image"/);
});

test("presentationToRevealHTML wraps scene slides with page-level background metadata", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [
      {
        slideId: "slide-cover-bg",
        layoutType: "intro-slide",
        layoutId: "intro-slide",
        background: {
          kind: "scene",
          preset: "hero-glow",
          emphasis: "immersive",
          colorToken: "primary",
        },
        contentData: {
          title: "Cover",
          subtitle: "Scene-first opener",
        },
        components: [],
      },
      {
        slideId: "slide-thanks-bg",
        layoutType: "thank-you",
        layoutId: "thank-you",
        background: {
          kind: "scene",
          preset: "closing-wash",
          emphasis: "immersive",
          colorToken: "secondary",
        },
        contentData: {
          title: "Thanks",
          contact: "team@example.com",
        },
        components: [],
      },
      {
        slideId: "slide-plain",
        layoutType: "metrics-slide",
        layoutId: "metrics-slide",
        contentData: {
          title: "Metrics",
          metrics: [{ value: "10", label: "Growth" }],
        },
        components: [],
      },
    ],
  });

  assert.match(html, /data-scene-preset="hero-glow"/);
  assert.match(html, /data-scene-preset="closing-wash"/);
  assert.match(html, /data-scene-emphasis="immersive"/);
  assert.equal((html.match(/data-scene-background="scene"/g) ?? []).length, 2);
});

test("presentationToRevealHTML keeps outline backgrounds restrained and quote backgrounds distinct", () => {
  const html = presentationToRevealHTML({
    ...basePresentation,
    slides: [
      {
        slideId: "slide-outline-bg",
        layoutType: "outline-slide",
        layoutId: "outline-slide",
        background: {
          kind: "scene",
          preset: "outline-grid",
          emphasis: "balanced",
          colorToken: "neutral",
        },
        contentData: {
          title: "Agenda",
          sections: [
            { title: "Context" },
            { title: "Method" },
            { title: "Findings" },
            { title: "Next Steps" },
          ],
        },
        components: [],
      },
      {
        slideId: "slide-quote-bg",
        layoutType: "quote-slide",
        layoutId: "quote-slide",
        background: {
          kind: "scene",
          preset: "quote-focus",
          emphasis: "balanced",
          colorToken: "secondary",
        },
        contentData: {
          quote: "Design for clarity, then add atmosphere.",
          author: "Design Team",
        },
        components: [],
      },
    ],
  });

  assert.match(html, /data-scene-preset="outline-grid"/);
  assert.match(html, /data-scene-preset="quote-focus"/);
  assert.match(html, /data-scene-emphasis="balanced"/);
  assert.doesNotMatch(html, /padding:56px 64px;background:linear-gradient\(180deg,#ffffff 0%,#f8fafc 100%\)/);
});

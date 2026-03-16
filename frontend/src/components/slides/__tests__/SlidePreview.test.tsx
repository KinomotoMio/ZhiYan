import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import SlidePreview from "@/components/slides/SlidePreview";
import type { Slide } from "@/types/slide";

test("two-column-compare malformed content does not crash", () => {
  const malformedSlide: Slide = {
    slideId: "slide-1",
    layoutType: "two-column-compare",
    layoutId: "two-column-compare",
    contentData: {
      title: "核心框架",
      items: [
        { title: "要点一", description: "描述一" },
        { title: "要点二", description: "描述二" },
      ],
    },
    components: [],
  };

  let html = "";
  assert.doesNotThrow(() => {
    html = renderToStaticMarkup(<SlidePreview slide={malformedSlide} />);
  });
  assert.match(html, /核心框架|要点 A|要点 B/);
});

test("outline-slide renders a two-column agenda page", () => {
  const slide: Slide = {
    slideId: "slide-outline",
    layoutType: "outline-slide",
    layoutId: "outline-slide",
    contentData: {
      title: "汇报目录",
      subtitle: "本次汇报从背景、方法、结果到结论逐步展开。",
      sections: [
        { title: "背景", description: "问题定义与业务场景" },
        { title: "方法", description: "研究方法与分析框架" },
        { title: "结果", description: "关键发现与数据表现" },
        { title: "结论", description: "建议动作与后续计划" },
      ],
    },
    components: [],
  };

  const html = renderToStaticMarkup(<SlidePreview slide={slide} />);
  assert.match(html, /汇报目录/);
  assert.match(html, /grid-cols-2/);
  assert.match(html, /grid-template-rows:repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(html, /问题定义与业务场景/);
  assert.match(html, />01<\/div>/);
});

test("outline-slide malformed sections do not crash preview rendering", () => {
  const malformedSlide: Slide = {
    slideId: "slide-outline-broken",
    layoutType: "outline-slide",
    layoutId: "outline-slide",
    contentData: {
      title: "Agenda broken",
      sections: "not-an-array",
    } as unknown as Slide["contentData"],
    components: [],
  };

  let html = "";
  assert.doesNotThrow(() => {
    html = renderToStaticMarkup(<SlidePreview slide={malformedSlide} />);
  });
  assert.doesNotMatch(html, /该页数据异常，可重新生成/);
  assert.match(html, /Agenda broken/);
  assert.match(html, /\u80cc\u666f/);
  assert.match(html, /\u5206\u6790/);
  assert.match(html, /\u65b9\u6848/);
  assert.match(html, /\u7ed3\u8bba/);
});

test("outline-slide-rail keeps up to three sections in a single rail column through SlidePreview", () => {
  const slide: Slide = {
    slideId: "slide-outline-rail-single",
    layoutType: "outline-slide-rail",
    layoutId: "outline-slide-rail",
    contentData: {
      title: "Delivery Roadmap",
      subtitle: "Three stages stay in one rail without overflow.",
      sections: [
        { title: "Context", description: "Why the work matters" },
        { title: "Model", description: "How the system is shaped" },
        { title: "Runtime", description: "How the renderer resolves data" },
      ],
    },
    components: [],
  };

  const html = renderToStaticMarkup(<SlidePreview slide={slide} />);
  assert.match(html, /Chapter Rail/);
  assert.match(html, /grid-template-rows:repeat\(3, minmax\(0, 1fr\)\)/);
  assert.doesNotMatch(html, /grid-cols-2/);
  assert.match(html, />03<\/div>/);
  assert.doesNotMatch(html, />04<\/div>/);
});

test("outline-slide-rail switches to balanced two columns after three sections", () => {
  const slide: Slide = {
    slideId: "slide-outline-rail-double",
    layoutType: "outline-slide-rail",
    layoutId: "outline-slide-rail",
    contentData: {
      title: "Delivery Roadmap",
      sections: [
        { title: "Context" },
        { title: "Model" },
        { title: "Runtime" },
        { title: "Templates" },
        { title: "QA" },
      ],
    },
    components: [],
  };

  const html = renderToStaticMarkup(<SlidePreview slide={slide} />);
  assert.match(html, /grid-cols-2/);
  assert.match(html, /grid-template-rows:repeat\(3, minmax\(0, 1fr\)\)/);
  assert.match(html, />05<\/div>/);
});

test("unrecoverable layout data renders fallback card", () => {
  const brokenSlide: Slide = {
    slideId: "slide-2",
    layoutType: "table-info",
    layoutId: "table-info",
    contentData: { title: "坏数据", rows: [] },
    components: [],
  };

  const html = renderToStaticMarkup(<SlidePreview slide={brokenSlide} />);
  assert.match(html, /该页数据异常，可重新生成/);
});

test("two-column-compare string columns are repaired", () => {
  const brokenByChatSlide: Slide = {
    slideId: "slide-3",
    layoutType: "two-column-compare",
    layoutId: "two-column-compare",
    contentData: {
      title: "比较维度",
      left: "**左栏**\n- 要点一\n- 要点二",
      right: "| 栏目 | 新增内容 |\n|---|---|\n| 方法 | 细化步骤 |",
    },
    components: [],
  };

  const html = renderToStaticMarkup(<SlidePreview slide={brokenByChatSlide} />);
  assert.doesNotMatch(html, /该页数据异常，可重新生成/);
  assert.match(html, /比较维度|要点 A|要点 B/);
});

test("bullet-with-icons uses editorial columns with bottom indices", () => {
  const slide: Slide = {
    slideId: "slide-4",
    layoutType: "bullet-with-icons",
    layoutId: "bullet-with-icons",
    contentData: {
      title: "核心能力",
      items: [
        { icon: { query: "zap" }, title: "自动化协同", description: "减少重复动作并提升稳定性" },
        { icon: { query: "shield" }, title: "治理与安全", description: "统一流程与权限边界" },
        { icon: { query: "rocket" }, title: "交付效率", description: "" },
      ],
    },
    components: [],
  };

  const html = renderToStaticMarkup(<SlidePreview slide={slide} />);
  assert.match(html, /核心能力/);
  assert.match(html, /font-size:36px;font-weight:700;line-height:1\.3/);
  assert.match(html, /mb-10 text-\[var\(--background-text,#111827\)\]/);
  assert.match(html, /自动化协同[\s\S]*减少重复动作并提升稳定性[\s\S]*01/);
  assert.match(html, /01/);
  assert.match(html, /02/);
  assert.match(html, /03/);
  assert.match(html, /自动化协同/);
  assert.match(html, /absolute left-0 top-1\/2/);
  assert.match(html, /height:50%/);
  assert.match(html, /mb-4 flex h-10 w-10 items-center justify-center rounded-full/);
  assert.match(html, /h-5 w-5 text-\[var\(--primary-color,#3b82f6\)\]/);
  assert.match(html, /background-color:color-mix\(in srgb, var\(--primary-color,#3b82f6\) 7%, white\)/);
  assert.match(html, /box-decoration-break:clone/);
  assert.match(html, /font-weight:700/);
  assert.match(html, /text-\[var\(--primary-color,#3b82f6\)\]/);
});

test("bullet-with-icons placeholder cards collapse into an explicit status panel", () => {
  const placeholderSlide: Slide = {
    slideId: "slide-4-status",
    layoutType: "bullet-with-icons",
    layoutId: "bullet-with-icons",
    contentData: {
      title: "关键发现",
      items: [
        {
          icon: { query: "star" },
          title: "内容生成中",
          description: "内容生成中",
        },
        {
          icon: { query: "star" },
          title: "内容生成中",
          description: "内容生成中",
        },
      ],
    },
    components: [],
  };

  const html = renderToStaticMarkup(<SlidePreview slide={placeholderSlide} />);
  assert.match(html, /内容暂未就绪/);
  assert.match(html, /该页正在生成或已回退，可稍后重试/);
  assert.equal((html.match(/内容生成中/g) ?? []).length, 0);
});

test("bullet-icons-only uses a denser two-column matrix with larger icon anchors", () => {
  const slide: Slide = {
    slideId: "slide-5",
    layoutType: "bullet-icons-only",
    layoutId: "bullet-icons-only",
    contentData: {
      title: "技术栈一览",
      items: [
        { icon: { query: "database" }, label: "数据中台" },
        { icon: { query: "shield" }, label: "权限治理" },
        { icon: { query: "bot" }, label: "智能助手编排" },
        { icon: { query: "workflow" }, label: "流程自动化" },
      ],
    },
    components: [],
  };

  const html = renderToStaticMarkup(<SlidePreview slide={slide} />);
  assert.match(html, /技术栈一览/);
  assert.match(html, /grid-template-columns:repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(html, /column-gap:40px/);
  assert.match(html, /row-gap:22px/);
  assert.match(html, /min-h-\[92px\]/);
  assert.match(html, /h-\[72px\] w-\[72px\]/);
  assert.match(html, /h-10 w-10 text-\[var\(--primary-color,#3b82f6\)\]/);
  assert.match(html, />01<\/div>/);
  assert.match(html, /智能助手编排/);
});

test("metrics-slide preview renders executive summary and keeps legacy slides readable", () => {
  const executiveSlide: Slide = {
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
  };
  const legacySlide: Slide = {
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
  };
  const html = renderToStaticMarkup(
    <div>
      <SlidePreview slide={executiveSlide} />
      <SlidePreview slide={legacySlide} />
    </div>
  );
  assert.match(html, /Enterprise adoption is no longer the bottleneck\./);
  assert.match(html, /Coverage expanded across the org, so review latency is the next constraint\./);
  assert.match(html, /Legacy Snapshot/);
  assert.match(html, /template leverage/);
  assert.doesNotMatch(html, /\u8be5\u9875\u6570\u636e\u5f02\u5e38\uff0c\u53ef\u91cd\u65b0\u751f\u6210/);
});
test("image source placeholders render explicit user guidance", () => {
  const userSlide: Slide = {
    slideId: "slide-user-image",
    layoutType: "image-and-description",
    layoutId: "image-and-description",
    contentData: {
      title: "\u7528\u6237\u8865\u56fe",
      description: "\u9700\u8981\u7ebf\u4e0b\u5b9e\u62cd\u3002",
      image: { source: "user", prompt: "\u8bf7\u4e0a\u4f20\u95e8\u5e97\u5b9e\u62cd\u7167\u7247" },
    },
    components: [],
  };

  const existingSlide: Slide = {
    slideId: "slide-existing-image",
    layoutType: "metrics-with-image",
    layoutId: "metrics-with-image",
    contentData: {
      title: "\u73b0\u6709\u7d20\u6750",
      metrics: [{ value: "12", label: "Assets" }],
      image: { source: "existing", prompt: "\u4f7f\u7528\u54c1\u724c\u56fe\u5e93\u5c01\u9762\u56fe" },
    },
    components: [],
  };

  const html = renderToStaticMarkup(
    <div>
      <SlidePreview slide={userSlide} />
      <SlidePreview slide={existingSlide} />
    </div>
  );

  assert.match(html, /\u5f85\u7528\u6237\u8865\u56fe\/\u4e0a\u4f20/);
  assert.match(html, /\u8bf7\u4e0a\u4f20\u95e8\u5e97\u5b9e\u62cd\u7167\u7247/);
  assert.match(html, /\u5f85\u7ed1\u5b9a\u73b0\u6709\u7d20\u6750/);
  assert.match(html, /\u4f7f\u7528\u54c1\u724c\u56fe\u5e93\u5c01\u9762\u56fe/);
});

test("scene backgrounds render as page-level wrappers in preview", () => {
  const html = renderToStaticMarkup(
    <div>
      <SlidePreview
        slide={{
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
            title: "Launch Plan",
            subtitle: "Scene-first opener",
          },
          components: [],
        }}
      />
      <SlidePreview
        slide={{
          slideId: "slide-plain-body",
          layoutType: "metrics-slide",
          layoutId: "metrics-slide",
          contentData: {
            title: "Plain body",
            metrics: [{ value: "10", label: "Growth" }],
          },
          components: [],
        }}
      />
    </div>
  );

  assert.match(html, /data-scene-background="scene"/);
  assert.match(html, /data-scene-preset="hero-glow"/);
  assert.match(html, /data-scene-emphasis="immersive"/);
  assert.equal((html.match(/data-scene-background="scene"/g) ?? []).length, 1);
});

test("outline and quote scene backgrounds stay layout-aware in preview", () => {
  const html = renderToStaticMarkup(
    <div>
      <SlidePreview
        slide={{
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
              { title: "Approach" },
              { title: "Findings" },
              { title: "Next Steps" },
            ],
          },
          components: [],
        }}
      />
      <SlidePreview
        slide={{
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
        }}
      />
    </div>
  );

  assert.match(html, /data-scene-preset="outline-grid"/);
  assert.match(html, /data-scene-preset="quote-focus"/);
  assert.equal((html.match(/data-scene-emphasis="balanced"/g) ?? []).length, 2);
  assert.doesNotMatch(html, /data-scene-emphasis="immersive"/);
  assert.doesNotMatch(html, /bg-\[linear-gradient\(180deg,var\(--slide-bg-start,#ffffff\)_0%,var\(--slide-bg-end,#f8fafc\)_100%\)\]/);
});

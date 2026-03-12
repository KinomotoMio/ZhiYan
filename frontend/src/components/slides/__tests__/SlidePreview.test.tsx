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

test("outline-slide renders a grid navigation page", () => {
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
  assert.match(html, /grid-template-columns:repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(html, /问题定义与业务场景/);
  assert.match(html, />01<\/div>/);
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

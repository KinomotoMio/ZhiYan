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

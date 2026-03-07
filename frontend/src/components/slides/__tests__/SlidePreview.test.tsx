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
      title: "Core frame",
      items: [
        { title: "Point A", description: "Desc A" },
        { title: "Point B", description: "Desc B" },
      ],
    },
    components: [],
  };

  let html = "";
  assert.doesNotThrow(() => {
    html = renderToStaticMarkup(<SlidePreview slide={malformedSlide} />);
  });
  assert.match(html, /Core frame|Point A|Point B/);
});

test("unrecoverable layout data renders fallback card", () => {
  const brokenSlide: Slide = {
    slideId: "slide-2",
    layoutType: "table-info",
    layoutId: "table-info",
    contentData: { title: "Broken data", rows: [] },
    components: [],
  };

  const html = renderToStaticMarkup(<SlidePreview slide={brokenSlide} />);
  assert.match(html, /该页数据异常，可重新生成/);
  assert.match(html, /table-info/);
});

test("two-column-compare string columns are repaired", () => {
  const brokenByChatSlide: Slide = {
    slideId: "slide-3",
    layoutType: "two-column-compare",
    layoutId: "two-column-compare",
    contentData: {
      title: "Compare axis",
      left: "**Left**\n- Point A\n- Point B",
      right: "| Column | Value |\n|---|---|\n| Method | Detailed steps |",
    },
    components: [],
  };

  const html = renderToStaticMarkup(<SlidePreview slide={brokenByChatSlide} />);
  assert.doesNotMatch(html, /该页数据异常，可重新生成/);
  assert.match(html, /Compare axis|Point A|Point B/);
});

test("active slide preview keeps ring and shadow classes", () => {
  const loadingSlide: Slide = {
    slideId: "slide-4",
    layoutType: "blank",
    layoutId: "blank",
    contentData: {
      _loading: true,
      title: "Loading",
    },
    components: [],
  };

  const html = renderToStaticMarkup(
    <SlidePreview slide={loadingSlide} isActive className="w-full" />
  );

  assert.match(html, /ring-2 ring-primary shadow-lg/);
  assert.match(html, /w-full/);
  assert.doesNotMatch(html, /hover:shadow-md/);
});

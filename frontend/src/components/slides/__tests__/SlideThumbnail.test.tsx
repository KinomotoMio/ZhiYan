import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import SlideThumbnail from "@/components/slides/SlideThumbnail";
import type { Slide } from "@/types/slide";

const baseSlide: Slide = {
  slideId: "slide-thumb-1",
  layoutType: "intro-slide",
  layoutId: "intro-slide",
  contentData: {
    title: "缩略图测试",
  },
  components: [],
};

test("thumbnail row stays shrinkable inside sidebar", () => {
  const html = renderToStaticMarkup(
    <SlideThumbnail
      slide={baseSlide}
      index={0}
      isActive={false}
      onClick={() => {}}
    />
  );

  assert.match(html, /class="flex w-full min-w-0 gap-2 items-start"/);
  assert.match(html, /class="relative min-w-0 flex-1"/);
  assert.doesNotMatch(html, /class="relative w-full"/);
});

test("thumbnail renders issue badge without changing sidebar structure", () => {
  const html = renderToStaticMarkup(
    <SlideThumbnail
      slide={baseSlide}
      index={1}
      isActive
      onClick={() => {}}
      issueMeta={{
        hard: 1,
        advisory: 2,
        total: 3,
        decision: "pending",
      }}
      onIssueClick={() => {}}
    />
  );

  assert.match(html, />2</);
  assert.match(html, /title="hard 1 \/ advisory 2"/);
  assert.match(html, /class="flex flex-col items-center gap-1 w-4 shrink-0"/);
  assert.match(html, /class="relative min-w-0 flex-1"/);
});

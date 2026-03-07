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

  assert.match(html, /class="(?=.*\bflex\b)(?=.*\bw-full\b)(?=.*\bmin-w-0\b)(?=.*\bgap-2\b)(?=.*\bitems-start\b)[^"]*"/);
  assert.match(html, /class="(?=.*\brelative\b)(?=.*\bmin-w-0\b)(?=.*\bflex-1\b)[^"]*"/);
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
  assert.match(html, /class="(?=.*\bflex\b)(?=.*\bflex-col\b)(?=.*\bitems-center\b)(?=.*\bgap-1\b)(?=.*\bw-4\b)(?=.*\bshrink-0\b)[^"]*"/);
  assert.match(html, /class="(?=.*\brelative\b)(?=.*\bmin-w-0\b)(?=.*\bflex-1\b)[^"]*"/);
});

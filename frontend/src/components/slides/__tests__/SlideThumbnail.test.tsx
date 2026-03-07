import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import SlideThumbnail from "@/components/slides/SlideThumbnail";
import type { Slide } from "@/types/slide";

const baseSlide: Slide = {
  slideId: "slide-thumbnail-1",
  layoutType: "blank",
  components: [],
};

test("thumbnail row uses shrink-safe width classes inside the sidebar rail", () => {
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
});

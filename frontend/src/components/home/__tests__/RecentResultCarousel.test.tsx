import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import RecentResultCarousel from "@/components/home/RecentResultCarousel";
import type { Presentation } from "@/types/slide";

const basePresentation: Presentation = {
  presentationId: "pres-home-html",
  title: "HTML Home Preview",
  slides: [
    { slideId: "slide-1", layoutType: "blank", components: [] },
    { slideId: "slide-2", layoutType: "blank", components: [] },
  ],
};

test("html mode uses reveal preview for main stage and thumbnails", () => {
  const html = renderToStaticMarkup(
    <RecentResultCarousel
      presentation={basePresentation}
      outputMode="html"
      htmlContent="<!DOCTYPE html><html><head></head><body><section>HTML</section><section>HTML 2</section></body></html>"
      previewSlideIndex={0}
      setPreviewSlideIndex={() => {}}
      isPreviewHovered={false}
      setIsPreviewHovered={() => {}}
      onOpenCurrentSlide={() => {}}
    />
  );

  assert.match(html, /data-preview-mode="interactive"/);
  assert.match(html, /data-preview-mode="thumbnail"/);
  assert.doesNotMatch(html, /该页数据异常，可重新生成/);
});

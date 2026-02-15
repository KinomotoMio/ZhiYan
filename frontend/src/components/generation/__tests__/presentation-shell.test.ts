import assert from "node:assert/strict";
import test from "node:test";

import {
  buildShellSlides,
  mergeGeneratedSlide,
  mergeOutlineTitles,
} from "@/components/generation/presentation-shell";

test("buildShellSlides returns fixed number of loading slides", () => {
  const slides = buildShellSlides(5, "生成中...");
  assert.equal(slides.length, 5);
  assert.equal(
    Boolean((slides[0].contentData as Record<string, unknown>)?._loading),
    true
  );
});

test("mergeOutlineTitles keeps slide count and only patches matched titles", () => {
  const shell = buildShellSlides(5, "生成中...");
  const merged = mergeOutlineTitles(shell, [
    { slide_number: 1, title: "封面" },
    { slide_number: 3, title: "方案" },
    { slide_number: 8, title: "越界" },
  ]);
  assert.equal(merged.length, 5);
  assert.equal((merged[0].contentData as Record<string, unknown>).title, "封面");
  assert.equal((merged[2].contentData as Record<string, unknown>).title, "方案");
});

test("mergeGeneratedSlide replaces exact index slide", () => {
  const shell = buildShellSlides(5, "生成中...");
  const next = mergeGeneratedSlide(shell, 2, {
    slideId: "slide-3",
    layoutType: "intro-slide",
    layoutId: "intro-slide",
    contentData: { title: "真实内容" },
    components: [],
  });
  assert.equal(next.length, 5);
  assert.equal(next[2].layoutType, "intro-slide");
  assert.equal((next[2].contentData as Record<string, unknown>).title, "真实内容");
});

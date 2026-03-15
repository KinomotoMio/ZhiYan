import assert from "node:assert/strict";
import test from "node:test";

import {
  getSceneBackgroundRule,
  normalizeSceneBackground,
  normalizeSlideSceneBackground,
  supportsSceneBackgroundLayout,
} from "@/lib/scene-background";
import type { Slide } from "@/types/slide";

test("eligible scene layouts expose their background defaults", () => {
  assert.deepEqual(getSceneBackgroundRule("intro-slide"), {
    preset: "hero-glow",
    emphasis: "immersive",
    allowedEmphasis: ["balanced", "immersive"],
  });
  assert.deepEqual(getSceneBackgroundRule("outline-slide"), {
    preset: "outline-grid",
    emphasis: "subtle",
    allowedEmphasis: ["subtle", "balanced"],
  });
  assert.equal(supportsSceneBackgroundLayout("thank-you"), true);
  assert.equal(supportsSceneBackgroundLayout("metrics-slide"), false);
});

test("normalizeSceneBackground repairs partial and mismatched eligible payloads", () => {
  assert.deepEqual(normalizeSceneBackground("intro-slide", { kind: "scene" }), {
    kind: "scene",
    preset: "hero-glow",
    emphasis: "immersive",
    colorToken: "primary",
  });

  assert.deepEqual(
    normalizeSceneBackground("outline-slide", {
      kind: "scene",
      preset: "hero-glow",
      emphasis: "immersive",
      colorToken: "neutral",
    }),
    {
      kind: "scene",
      preset: "outline-grid",
      emphasis: "balanced",
      colorToken: "neutral",
    }
  );
});

test("normalizeSceneBackground removes ineligible usage and nulls invalid structures", () => {
  assert.equal(
    normalizeSceneBackground("metrics-slide", {
      kind: "scene",
      preset: "hero-glow",
    }),
    undefined
  );
  assert.equal(
    normalizeSceneBackground("quote-slide", {
      kind: "image",
      preset: "quote-focus",
    }),
    null
  );
});

test("normalizeSlideSceneBackground preserves slide typing while repairing metadata", () => {
  const eligibleSlide: Slide = {
    slideId: "slide-1",
    layoutType: "thank-you",
    layoutId: "thank-you",
    background: {
      kind: "scene",
      preset: "closing-wash",
    },
    contentData: { title: "Thanks" },
    components: [],
  };
  const ineligibleSlide: Slide = {
    slideId: "slide-2",
    layoutType: "metrics-slide",
    layoutId: "metrics-slide",
    background: {
      kind: "scene",
      preset: "hero-glow",
      emphasis: "immersive",
      colorToken: "secondary",
    },
    contentData: { title: "KPIs", metrics: [{ value: "10", label: "Growth" }] },
    components: [],
  };

  assert.deepEqual(normalizeSlideSceneBackground(eligibleSlide).background, {
    kind: "scene",
    preset: "closing-wash",
    emphasis: "immersive",
    colorToken: "primary",
  });

  const repairedIneligibleSlide = normalizeSlideSceneBackground(ineligibleSlide);
  assert.equal("background" in repairedIneligibleSlide, false);
});

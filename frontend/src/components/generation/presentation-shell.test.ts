import assert from "node:assert/strict";
import test from "node:test";

import { buildShellSlides, mergeGeneratedSlide, mergeOutlineTitles } from "./presentation-shell";
import type { Slide } from "@/types/slide";

function withMeta(
  slide: Slide,
  meta: { tier_rank: number; seq: number; tier?: string; engine_id?: string },
): Slide {
  return {
    ...slide,
    contentData: {
      ...(slide.contentData ?? {}),
      _generation: {
        tier: meta.tier ?? "content",
        tier_rank: meta.tier_rank,
        seq: meta.seq,
        engine_id: meta.engine_id,
      },
    },
  };
}

test("mergeOutlineTitles upgrades shell tier to outline tier", () => {
  const slides = buildShellSlides(2, "T");
  const merged = mergeOutlineTitles(slides, [{ slide_number: 1, title: "S1" }]);
  const meta = (merged[0]?.contentData as any)?._generation;
  assert.equal(meta.tier_rank, 5);
});

test("mergeGeneratedSlide rejects lower tier_rank even with higher seq", () => {
  const slides = buildShellSlides(1, "T");
  const prev = withMeta(
    { ...slides[0], layoutType: "bullet-with-icons", contentData: { title: "A" } },
    { tier_rank: 20, seq: 10 },
  );
  const incoming = withMeta(
    { ...prev, contentData: { title: "B" } },
    { tier_rank: 5, seq: 11 },
  );
  const next = mergeGeneratedSlide([prev], 0, incoming)[0];
  assert.equal((next.contentData as any).title, "A");
});

test("mergeGeneratedSlide is idempotent for same tier_rank when seq is not increasing", () => {
  const slides = buildShellSlides(1, "T");
  const prev = withMeta(
    { ...slides[0], layoutType: "bullet-with-icons", contentData: { title: "A" } },
    { tier_rank: 20, seq: 10 },
  );
  const incoming = withMeta(
    { ...prev, contentData: { title: "B" } },
    { tier_rank: 20, seq: 10 },
  );
  const next = mergeGeneratedSlide([prev], 0, incoming)[0];
  assert.equal((next.contentData as any).title, "A");
});

test("mergeGeneratedSlide accepts same tier_rank when seq increases", () => {
  const slides = buildShellSlides(1, "T");
  const prev = withMeta(
    { ...slides[0], layoutType: "bullet-with-icons", contentData: { title: "A" } },
    { tier_rank: 20, seq: 10 },
  );
  const incoming = withMeta(
    { ...prev, contentData: { title: "B" } },
    { tier_rank: 20, seq: 11 },
  );
  const next = mergeGeneratedSlide([prev], 0, incoming)[0];
  assert.equal((next.contentData as any).title, "B");
});

test("mergeGeneratedSlide never lets a loading slide override a materialized slide", () => {
  const slides = buildShellSlides(1, "T");
  const prev: Slide = {
    ...slides[0],
    layoutType: "bullet-with-icons",
    contentData: { title: "A", _loading: false, _generation: { tier: "content", tier_rank: 20, seq: 10 } },
  };
  const incoming: Slide = {
    ...slides[0],
    layoutType: "blank",
    contentData: { title: "Loading", _loading: true, _generation: { tier: "shell", tier_rank: 0, seq: 99 } },
  };
  const next = mergeGeneratedSlide([prev], 0, incoming)[0];
  assert.equal((next.contentData as any).title, "A");
});


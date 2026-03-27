import assert from "node:assert/strict";
import test from "node:test";

import {
  applySpeakerAudioMetaToSlides,
  applySpeakerNotesDraftToSlides,
} from "@/components/editor/speaker-notes-flow";

test("applySpeakerNotesDraftToSlides clears stale speaker audio when notes change", () => {
  const slides = [
    {
      slideId: "slide-1",
      layoutId: "intro-slide",
      layoutType: "intro-slide",
      contentData: { title: "封面" },
      speakerNotes: "旧注解",
      speakerAudio: {
        provider: "minimax",
        model: "speech-2.8-hd",
        voiceId: "male-qn-qingse",
        textHash: "old-hash",
        storagePath: "/tmp/old.mp3",
        mimeType: "audio/mpeg",
        generatedAt: "2026-03-27T12:00:00Z",
      },
    },
  ];

  const next = applySpeakerNotesDraftToSlides(slides, 0, "新注解");

  assert.equal(next[0]?.speakerNotes, "新注解");
  assert.equal(next[0]?.speakerAudio, undefined);
});

test("applySpeakerAudioMetaToSlides patches only the target slide", () => {
  const slides = [
    {
      slideId: "slide-1",
      layoutId: "intro-slide",
      layoutType: "intro-slide",
      contentData: { title: "封面" },
    },
    {
      slideId: "slide-2",
      layoutId: "summary",
      layoutType: "summary",
      contentData: { title: "总结" },
    },
  ];

  const next = applySpeakerAudioMetaToSlides(slides, "slide-2", {
    provider: "minimax",
    model: "speech-2.8-hd",
    voiceId: "male-qn-qingse",
    textHash: "hash-2",
    storagePath: "/tmp/slide-2.mp3",
    mimeType: "audio/mpeg",
    generatedAt: "2026-03-27T12:00:00Z",
  });

  assert.equal(next[0]?.speakerAudio, undefined);
  assert.equal(next[1]?.speakerAudio?.textHash, "hash-2");
});

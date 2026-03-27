import assert from "node:assert/strict";
import test from "node:test";

import { normalizeHtmlDeckMeta } from "@/lib/html-deck";

test("normalizeHtmlDeckMeta normalizes legacy slide fields through the slide helper", () => {
  const meta = normalizeHtmlDeckMeta({
    title: "Deck",
    slides: [
      {
        index: 2.8,
        slide_id: " cover ",
        title: "  Cover  ",
        speaker_notes: "Opening",
        speaker_audio: {
          provider: "openai",
          model: "gpt-4o-mini-tts",
          voiceId: "alloy",
          textHash: "abc",
          storagePath: "speaker/cover.mp3",
          mimeType: "audio/mpeg",
          generatedAt: "2026-03-27T10:00:00Z",
        },
      },
      {
        slideId: "",
        title: "Should be skipped",
      },
    ],
  });

  assert.deepEqual(meta, {
    title: "Deck",
    slideCount: 1,
    slides: [
      {
        index: 2,
        slideId: "cover",
        title: "Cover",
        speakerNotes: "Opening",
        speakerAudio: {
          provider: "openai",
          model: "gpt-4o-mini-tts",
          voiceId: "alloy",
          textHash: "abc",
          storagePath: "speaker/cover.mp3",
          mimeType: "audio/mpeg",
          generatedAt: "2026-03-27T10:00:00Z",
        },
      },
    ],
  });
});

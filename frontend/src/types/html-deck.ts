import type { SpeakerAudio } from "@/types/slide";

export interface HtmlDeckSlideMeta {
  index: number;
  slideId: string;
  title: string;
  speakerNotes?: string;
  speakerAudio?: SpeakerAudio;
}

export interface HtmlDeckMeta {
  title: string;
  slideCount: number;
  slides: HtmlDeckSlideMeta[];
}

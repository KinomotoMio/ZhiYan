// Slide data model. Keep in sync with shared/schemas/slide.schema.json.

export type ComponentType = "text" | "image" | "chart" | "shape";

export type ComponentRole =
  | "title"
  | "subtitle"
  | "body"
  | "caption"
  | "decoration"
  | "illustration";

export type LayoutType =
  | "title-slide"
  | "title-content"
  | "title-content-image"
  | "two-column"
  | "image-full"
  | "section-header"
  | "blank"
  | "intro-slide"
  | "intro-slide-left"
  | "outline-slide"
  | "outline-slide-rail"
  | "bullet-with-icons"
  | "bullet-with-icons-cards"
  | "numbered-bullets"
  | "numbered-bullets-track"
  | "metrics-slide"
  | "metrics-slide-band"
  | "metrics-with-image"
  | "chart-with-bullets"
  | "table-info"
  | "two-column-compare"
  | "image-and-description"
  | "timeline"
  | "quote-slide"
  | "quote-banner"
  | "bullet-icons-only"
  | "challenge-outcome"
  | "thank-you"
  | "thank-you-contact"
  | "section-header-side";

export type SceneBackgroundPreset =
  | "hero-glow"
  | "section-band"
  | "outline-grid"
  | "quote-focus"
  | "closing-wash";

export type SceneBackgroundEmphasis = "subtle" | "balanced" | "immersive";

export type SceneBackgroundColorToken = "primary" | "secondary" | "neutral";

export interface SceneBackground {
  kind: "scene";
  preset: SceneBackgroundPreset;
  emphasis?: SceneBackgroundEmphasis;
  colorToken?: SceneBackgroundColorToken;
}

export interface SpeakerAudio {
  provider: string;
  model: string;
  voiceId: string;
  textHash: string;
  storagePath: string;
  mimeType: string;
  generatedAt: string;
}

export interface Position {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Style {
  fontSize?: number;
  fontWeight?: string;
  fontStyle?: string;
  color?: string;
  backgroundColor?: string;
  textAlign?: "left" | "center" | "right";
  verticalAlign?: "top" | "middle" | "bottom";
  opacity?: number;
}

export interface Component {
  id: string;
  type: ComponentType;
  role: ComponentRole;
  content?: string;
  position: Position;
  style?: Style;
  chartData?: Record<string, unknown>;
}

export interface Slide {
  slideId: string;
  layoutType: LayoutType;
  layoutId?: string;
  contentData?: Record<string, unknown>;
  background?: SceneBackground | null;
  components?: Component[];
  speakerNotes?: string;
  speakerAudio?: SpeakerAudio;
  templateSlotMapping?: Record<string, string>;
}

export interface Theme {
  primaryColor?: string;
  secondaryColor?: string;
  backgroundColor?: string;
  fontFamily?: string;
  headingFontFamily?: string;
}

export interface Presentation {
  presentationId: string;
  title: string;
  theme?: Theme;
  slides: Slide[];
}

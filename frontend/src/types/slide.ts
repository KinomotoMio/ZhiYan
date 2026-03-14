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
  | "outline-slide"
  | "bullet-with-icons"
  | "numbered-bullets"
  | "metrics-slide"
  | "metrics-with-image"
  | "chart-with-bullets"
  | "table-info"
  | "two-column-compare"
  | "image-and-description"
  | "timeline"
  | "quote-slide"
  | "bullet-icons-only"
  | "challenge-outcome"
  | "thank-you";

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

// Slide 数据模型 — 与 shared/schemas/slide.schema.json 保持同步

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
  | "blank";

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
  components: Component[];
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

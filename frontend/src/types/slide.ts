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
  | "blank"
  // 新版 layout IDs
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
  // 主渲染字段：具体 layout ID（对应 template-registry 中的布局）
  layoutId?: string;
  // 主渲染字段：结构化内容数据（按 layout schema 生成的 JSON）
  contentData?: Record<string, unknown>;
  // 旧版兼容字段（只读兼容）
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

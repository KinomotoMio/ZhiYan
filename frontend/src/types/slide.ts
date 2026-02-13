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
  // 新增：具体 layout ID（对应 template-registry 中的布局）
  layoutId?: string;
  // 新增：结构化内容数据（按 layout schema 生成的 JSON）
  contentData?: Record<string, unknown>;
  // 保留 components 用于向后兼容
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

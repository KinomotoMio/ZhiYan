// Layout content data types — 与 backend/app/models/layouts/schemas.py 保持同步
// 每个 layout 的结构化内容数据

export interface IconRef {
  query: string;
  resolvedSvg?: string | null;
}

export interface ImageRef {
  prompt: string;
  url?: string | null;
  alt?: string;
}

export interface ChartData {
  chart_type?: string;
  chartType?: string; // legacy compatibility
  labels: string[];
  datasets: { label: string; data: number[]; color?: string }[];
}

// 1. intro-slide
export interface IntroSlideData {
  title: string;
  subtitle: string;
  author?: string | null;
  date?: string | null;
}

// 2. section-header
export interface SectionHeaderData {
  title: string;
  subtitle?: string | null;
}

// 3. bullet-with-icons
export interface BulletIconItem {
  icon: IconRef;
  title: string;
  description: string;
}

export interface BulletWithIconsData {
  title: string;
  items: BulletIconItem[];
}

// 4. numbered-bullets
export interface NumberedBulletItem {
  title: string;
  description: string;
}

export interface NumberedBulletsData {
  title: string;
  items: NumberedBulletItem[];
}

// 5. metrics-slide
export interface MetricItem {
  value: string;
  label: string;
  description?: string | null;
  icon?: IconRef | null;
}

export interface MetricsSlideData {
  title: string;
  metrics: MetricItem[];
}

// 6. metrics-with-image
export interface MetricsWithImageData {
  title: string;
  metrics: MetricItem[];
  image: ImageRef;
}

// 7. chart-with-bullets
export interface ChartWithBulletsData {
  title: string;
  chart: ChartData;
  bullets: { text: string }[];
}

// 8. table-info
export interface TableInfoData {
  title: string;
  headers: string[];
  rows: string[][];
  caption?: string | null;
}

// 9. two-column-compare
export interface CompareColumn {
  heading: string;
  items: string[];
  icon?: IconRef | null;
}

export interface TwoColumnCompareData {
  title: string;
  left: CompareColumn;
  right: CompareColumn;
}

// 10. image-and-description
export interface ImageAndDescriptionData {
  title: string;
  image: ImageRef;
  description: string;
  bullets?: string[] | null;
}

// 11. timeline
export interface TimelineEvent {
  date: string;
  title: string;
  description?: string | null;
}

export interface TimelineData {
  title: string;
  events: TimelineEvent[];
}

// 12. quote-slide
export interface QuoteSlideData {
  quote: string;
  author?: string | null;
  context?: string | null;
}

// 13. bullet-icons-only
export interface IconGridItem {
  icon: IconRef;
  label: string;
}

export interface BulletIconsOnlyData {
  title: string;
  items: IconGridItem[];
}

// 14. challenge-outcome
export interface ChallengeOutcomeItem {
  challenge: string;
  outcome: string;
}

export interface ChallengeOutcomeData {
  title: string;
  items: ChallengeOutcomeItem[];
}

// 15. thank-you
export interface ThankYouData {
  title: string;
  subtitle?: string | null;
  contact?: string | null;
}

// Union type for all layout data
export type LayoutContentData =
  | IntroSlideData
  | SectionHeaderData
  | BulletWithIconsData
  | NumberedBulletsData
  | MetricsSlideData
  | MetricsWithImageData
  | ChartWithBulletsData
  | TableInfoData
  | TwoColumnCompareData
  | ImageAndDescriptionData
  | TimelineData
  | QuoteSlideData
  | BulletIconsOnlyData
  | ChallengeOutcomeData
  | ThankYouData;

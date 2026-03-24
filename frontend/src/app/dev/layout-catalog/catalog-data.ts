import { getAllLayouts, type LayoutEntry as RuntimeLayoutEntry } from "@/lib/template-registry";

export interface CatalogFixture {
  schemaName: string;
  keyFields: string[];
  data: Record<string, unknown>;
}

export interface CatalogEntry extends RuntimeLayoutEntry, CatalogFixture {}

function svgDataUrl(stops: string[], label: string): string {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
      <defs>
        <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="${stops[0]}"/>
          <stop offset="100%" stop-color="${stops[1]}"/>
        </linearGradient>
      </defs>
      <rect width="1280" height="720" fill="url(#g)"/>
      <circle cx="1040" cy="160" r="140" fill="rgba(255,255,255,0.14)"/>
      <circle cx="180" cy="560" r="180" fill="rgba(255,255,255,0.12)"/>
      <text x="96" y="602" fill="white" font-family="Arial, sans-serif" font-size="56" font-weight="700">${label}</text>
    </svg>
  `;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

const photoA = svgDataUrl(["#1d4ed8", "#06b6d4"], "Product View");
const photoB = svgDataUrl(["#0f766e", "#65a30d"], "Dashboard");

const catalogFixtures = {
  "intro-slide": {
    schemaName: "IntroSlideData",
    keyFields: ["title", "subtitle", "author?", "date?"],
    data: {
      title: "ZhiYan Layout Catalog",
      subtitle: "Preview every built-in layout with sample content.",
      author: "Codex",
      date: "2026-03-11",
    },
  },
  "intro-slide-left": {
    schemaName: "IntroSlideData",
    keyFields: ["title", "subtitle", "author?", "date?"],
    data: {
      title: "Variant-Led Layout Selection",
      subtitle:
        "Choose a left-aligned cover when the opening slide needs more narrative context and setup.",
      author: "Zhiyan Team",
      date: "2026-03-14",
    },
  },
  "outline-slide": {
    schemaName: "OutlineSlideData",
    keyFields: ["title", "subtitle?", "sections[4-10]"],
    data: {
      title: "Presentation Outline",
      subtitle:
        "A navigation page that frames the full report structure before the detailed sections begin.",
      sections: [
        {
          title: "Background",
          description: "Business context and project motivation",
        },
        {
          title: "Method",
          description: "Approach, data sources, and evaluation logic",
        },
        {
          title: "Findings",
          description: "Key observations and critical metrics",
        },
        {
          title: "Results",
          description: "Outcome summary and measurable impact",
        },
      ],
    },
  },
  "outline-slide-rail": {
    schemaName: "OutlineSlideData",
    keyFields: ["title", "subtitle?", "sections[1-10]"],
    data: {
      title: "Delivery Roadmap",
      subtitle:
        "A directional agenda variant that emphasizes sequence and stage progression over card symmetry.",
      sections: [
        { title: "Context", description: "Why the taxonomy needs a new variant layer" },
        { title: "Model", description: "Define variant as a formal design option" },
        { title: "Runtime", description: "Select variant first, then resolve layout" },
        { title: "Templates", description: "Ship real layouts under variant tracks" },
      ],
    },
  },
  "section-header": {
    schemaName: "SectionHeaderData",
    keyFields: ["title", "subtitle?"],
    data: {
      title: "Platform Overview",
      subtitle: "A clean transition slide between major chapters.",
    },
  },
  "section-header-side": {
    schemaName: "SectionHeaderData",
    keyFields: ["title", "subtitle?"],
    data: {
      title: "Selector Contract",
      subtitle: "Shift runtime choice from direct layout IDs to variant-first resolution.",
    },
  },
  "bullet-with-icons": {
    schemaName: "BulletWithIconsData",
    keyFields: ["title", "items[3-4]"],
    data: {
      title: "Why Teams Use This Layout",
      items: [
        {
          icon: { query: "sparkles" },
          title: "Scannable",
          description:
            "Each point gets a visual anchor and one concise explanation.",
        },
        {
          icon: { query: "blocks" },
          title: "Balanced",
          description:
            "Works well for three or four capabilities on one slide.",
        },
        {
          icon: { query: "shield-check" },
          title: "Reliable",
          description: "Predictable spacing keeps the page from feeling crowded.",
        },
      ],
    },
  },
  "bullet-with-icons-cards": {
    schemaName: "BulletWithIconsData",
    keyFields: ["title", "items[3-4]"],
    data: {
      title: "Why Feature Cards Work",
      items: [
        {
          icon: { query: "layout-grid" },
          title: "Modular",
          description: "Each capability becomes its own card with a cleaner boundary.",
        },
        {
          icon: { query: "sparkles" },
          title: "Productive",
          description: "Useful when the story is closer to product modules than plain bullets.",
        },
        {
          icon: { query: "shield-check" },
          title: "Stable",
          description: "Keeps a stronger visual system without changing the underlying content schema.",
        },
        {
          icon: { query: "arrow-right-left" },
          title: "Reusable",
          description: "Lets the same icon-points structure host multiple official design variants.",
        },
      ],
    },
  },
  "image-and-description": {
    schemaName: "ImageAndDescriptionData",
    keyFields: ["title", "image", "description", "bullets?"],
    data: {
      title: "Feature Spotlight",
      image: { prompt: "hero product mockup", url: photoA, alt: "product preview" },
      description:
        "This layout works when one image should do most of the emotional work, with the text explaining why it matters.",
      bullets: [
        "Strong for demos and case studies",
        "Keeps the message focused",
        "Easy to theme with photography",
      ],
    },
  },
  "bullet-icons-only": {
    schemaName: "BulletIconsOnlyData",
    keyFields: ["title", "items[4-8]"],
    data: {
      title: "Capability Grid",
      items: [
        { icon: { query: "database" }, label: "Source ingest" },
        { icon: { query: "message-square" }, label: "Chat edits" },
        { icon: { query: "image" }, label: "Asset prompts" },
        { icon: { query: "file-chart-column" }, label: "Export" },
        { icon: { query: "sparkles" }, label: "Themeing" },
        { icon: { query: "shield-check" }, label: "Verification" },
      ],
    },
  },
  "metrics-slide": {
    schemaName: "MetricsSlideData",
    keyFields: ["title", "conclusion", "conclusionBrief", "metrics[2-4]"],
    data: {
      title: "Quarterly Snapshot",
      conclusion: "Enterprise adoption is no longer the bottleneck.",
      conclusionBrief:
        "Coverage expanded across the org, so the next constraint is shortening review latency and increasing reuse in late-stage polish.",
      metrics: [
        { value: "92%", label: "Adoption", description: "active team usage" },
        { value: "14d", label: "Lead Time", description: "from brief to deck" },
        { value: "3.6x", label: "Reuse", description: "template leverage" },
      ],
    },
  },
  "metrics-slide-band": {
    schemaName: "MetricsSlideData",
    keyFields: ["title", "conclusion", "conclusionBrief", "metrics[2-4]"],
    data: {
      title: "Variant Delivery Progress",
      conclusion:
        "The variant layer now carries real design options instead of a single baseline tag.",
      conclusionBrief:
        "Metadata, selector, and catalog can all reference one canonical variant ID before the system resolves a specific template.",
      metrics: [
        { value: "8", label: "new layouts", description: "Fresh built-ins shipped under the new variant model" },
        { value: "3", label: "design traits", description: "Tone, style, and density kept as helper descriptors" },
        { value: "1", label: "selector chain", description: "group -> sub-group -> variant -> layoutId" },
      ],
    },
  },
  "metrics-with-image": {
    schemaName: "MetricsWithImageData",
    keyFields: ["title", "metrics[2-3]", "image"],
    data: {
      title: "Impact + Product Shot",
      metrics: [
        {
          value: "48%",
          label: "Faster review",
          description: "less manual cleanup",
        },
        {
          value: "11",
          label: "Teams onboarded",
          description: "within two sprints",
        },
        { value: "4.8/5", label: "Satisfaction", description: "pilot feedback" },
      ],
      image: {
        prompt: "analytics dashboard",
        url: photoB,
        alt: "dashboard preview",
      },
    },
  },
  "chart-with-bullets": {
    schemaName: "ChartWithBulletsData",
    keyFields: ["title", "chart", "bullets[2-4]"],
    data: {
      title: "Trend + Commentary",
      chart: {
        chartType: "bar",
        labels: ["Q1", "Q2", "Q3", "Q4"],
        datasets: [{ label: "Growth", data: [12, 18, 24, 31] }],
      },
      bullets: [
        { text: "Usage climbs steadily after template standardization." },
        { text: "The largest jump happens once review loops are shortened." },
        { text: "Best used when one chart needs 2-3 plain-language takeaways." },
      ],
    },
  },
  "table-info": {
    schemaName: "TableInfoData",
    keyFields: ["title", "headers", "rows", "caption?"],
    data: {
      title: "Option Comparison",
      headers: ["Option", "Speed", "Control", "Best For"],
      rows: [
        ["Default", "Fast", "Low", "simple briefs"],
        ["Custom", "Medium", "High", "brand-heavy decks"],
        ["Hybrid", "Fast", "Medium", "most teams"],
      ],
      caption: "A compact matrix for structured comparisons.",
    },
  },
  "two-column-compare": {
    schemaName: "TwoColumnCompareData",
    keyFields: ["title", "left", "right"],
    data: {
      title: "Manual vs Assisted Workflow",
      left: {
        heading: "Manual",
        icon: { query: "pen-tool" },
        items: ["Slower setup", "Inconsistent page rhythm", "Harder to reuse"],
      },
      right: {
        heading: "Assisted",
        icon: { query: "bot" },
        items: [
          "Faster first draft",
          "Repeatable layout system",
          "Easier to refine",
        ],
      },
    },
  },
  "challenge-outcome": {
    schemaName: "ChallengeOutcomeData",
    keyFields: ["title", "items[2-4]"],
    data: {
      title: "Problems and Fixes",
      items: [
        {
          challenge: "Slides feel visually inconsistent across authors.",
          outcome: "Use a constrained layout library with schema-guided content.",
        },
        {
          challenge: "Reviewers spend time fixing spacing and hierarchy.",
          outcome: "Push style decisions into reusable TSX layouts.",
        },
      ],
    },
  },
  "numbered-bullets": {
    schemaName: "NumberedBulletsData",
    keyFields: ["title", "items[3-5]"],
    data: {
      title: "Rollout Plan",
      items: [
        {
          title: "Collect input",
          description:
            "Gather source docs, goals, and constraints from the team.",
        },
        {
          title: "Draft structure",
          description:
            "Turn raw material into a short narrative with a clear order.",
        },
        {
          title: "Polish visuals",
          description: "Pick a layout, tune wording, and verify readability.",
        },
      ],
    },
  },
  "numbered-bullets-track": {
    schemaName: "NumberedBulletsData",
    keyFields: ["title", "items[3-5]"],
    data: {
      title: "Implementation Rollout",
      items: [
        {
          title: "Model metadata",
          description: "Move variant into canonical metadata and make it an explicit node.",
        },
        {
          title: "Runtime selection",
          description: "Have selector choose variant IDs before layout IDs.",
        },
        {
          title: "Catalog surface",
          description: "Expose grouped variants and real layouts in the internal catalog.",
        },
        {
          title: "Template supply",
          description: "Ship new concrete templates so the variants are actually selectable.",
        },
      ],
    },
  },
  timeline: {
    schemaName: "TimelineData",
    keyFields: ["title", "events[3-6]"],
    data: {
      title: "Delivery Timeline",
      events: [
        {
          date: "Week 1",
          title: "Research",
          description: "Audit current layouts and sample decks.",
        },
        {
          date: "Week 2",
          title: "Prototype",
          description: "Add new layout components and schemas.",
        },
        {
          date: "Week 3",
          title: "Validate",
          description: "Run generation checks and visual review.",
        },
        {
          date: "Week 4",
          title: "Ship",
          description: "Document patterns and hand off to the team.",
        },
      ],
    },
  },
  "quote-slide": {
    schemaName: "QuoteSlideData",
    keyFields: ["quote", "author?", "context?"],
    data: {
      quote:
        "A layout system is just a promise that content will land in a predictable, readable place.",
      author: "Design review note",
      context: "internal principle",
    },
  },
  "quote-banner": {
    schemaName: "QuoteSlideData",
    keyFields: ["quote", "author?", "context?"],
    data: {
      quote:
        "Variant should name the design answer itself, not hide behind a stack of abstract axes.",
      author: "Issue #102",
      context: "product framing",
    },
  },
  "thank-you": {
    schemaName: "ThankYouData",
    keyFields: ["title", "subtitle?", "contact?"],
    data: {
      title: "Thanks",
      subtitle: "Questions, feedback, or layout ideas are welcome.",
      contact: "design-system@zhiyan.local",
    },
  },
  "thank-you-contact": {
    schemaName: "ThankYouData",
    keyFields: ["title", "subtitle?", "contact?"],
    data: {
      title: "Thanks for Reviewing",
      subtitle:
        "Use the contact-card closing variant when the ending should invite a concrete next step.",
      contact: "pm@zhiyan.ai",
    },
  },
} satisfies Record<string, CatalogFixture>;

export function getLayoutCatalogFixtureIds(): string[] {
  return Object.keys(catalogFixtures);
}

export function buildLayoutCatalogEntries(): CatalogEntry[] {
  const runtimeLayouts = getAllLayouts();
  const runtimeLayoutIds = new Set(runtimeLayouts.map((layout) => layout.id));
  const missingFixtureIds = runtimeLayouts
    .map((layout) => layout.id)
    .filter((layoutId) => !(layoutId in catalogFixtures));

  if (missingFixtureIds.length > 0) {
    throw new Error(
      `Missing layout catalog fixtures for: ${missingFixtureIds.sort().join(", ")}`,
    );
  }

  const unknownFixtureIds = Object.keys(catalogFixtures).filter(
    (layoutId) => !runtimeLayoutIds.has(layoutId),
  );

  if (unknownFixtureIds.length > 0) {
    throw new Error(
      `Layout catalog fixtures reference unknown layouts: ${unknownFixtureIds.sort().join(", ")}`,
    );
  }

  return runtimeLayouts.map((layout) => {
    const fixture = catalogFixtures[layout.id as keyof typeof catalogFixtures];
    return {
      ...layout,
      ...fixture,
    };
  });
}

import type { SceneBackground, SceneBackgroundColorToken } from "@/types/slide";

export type StyleValue = number | string;
export type StyleMap = Record<string, StyleValue>;

export interface SceneBackgroundLayer {
  key: string;
  style: StyleMap;
}

export interface SceneBackgroundRenderModel {
  attributes: Record<string, string>;
  frameStyle: StyleMap;
  contentStyle: StyleMap;
  layers: SceneBackgroundLayer[];
}

type SceneBackgroundEmphasis = NonNullable<SceneBackground["emphasis"]>;

interface EmphasisProfile {
  accent: number;
  spread: number;
  density: number;
}

const EMPHASIS_PROFILES: Record<SceneBackgroundEmphasis, EmphasisProfile> = {
  subtle: {
    accent: 0.72,
    spread: 0.92,
    density: 0.88,
  },
  balanced: {
    accent: 1,
    spread: 1,
    density: 1,
  },
  immersive: {
    accent: 1.34,
    spread: 1.18,
    density: 1.12,
  },
};

const BACKGROUND_COLOR = "var(--background-color,#ffffff)";
const BACKGROUND_TEXT = "var(--background-text,#111827)";

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, value));
}

function mixWithTransparent(color: string, percent: number): string {
  return `color-mix(in srgb, ${color} ${clampPercent(percent)}%, transparent)`;
}

function mixWithBase(color: string, percent: number, base = BACKGROUND_COLOR): string {
  return `color-mix(in srgb, ${color} ${clampPercent(percent)}%, ${base})`;
}

function resolveAccentColor(token: SceneBackgroundColorToken | undefined): string {
  switch (token) {
    case "secondary":
      return "var(--secondary-color,var(--primary-color,#3b82f6))";
    case "neutral":
      return `color-mix(in srgb, ${BACKGROUND_TEXT} 20%, ${BACKGROUND_COLOR})`;
    case "primary":
    default:
      return "var(--primary-color,#3b82f6)";
  }
}

function resolveSecondaryAccent(token: SceneBackgroundColorToken | undefined): string {
  switch (token) {
    case "secondary":
      return `color-mix(in srgb, ${BACKGROUND_TEXT} 14%, ${BACKGROUND_COLOR})`;
    case "neutral":
      return "var(--primary-color,#3b82f6)";
    case "primary":
    default:
      return "var(--secondary-color,var(--primary-color,#3b82f6))";
  }
}

function createLayer(key: string, style: StyleMap): SceneBackgroundLayer {
  return {
    key,
    style: {
      position: "absolute",
      inset: 0,
      pointerEvents: "none",
      ...style,
    },
  };
}

function heroGlowLayers(accent: string, altAccent: string, emphasis: SceneBackgroundEmphasis): SceneBackgroundLayer[] {
  const profile = EMPHASIS_PROFILES[emphasis];
  return [
    createLayer("hero-base", {
      background: `linear-gradient(140deg, ${mixWithBase(accent, 8 * profile.density)} 0%, ${BACKGROUND_COLOR} 42%, ${mixWithBase(altAccent, 12 * profile.density)} 100%)`,
    }),
    createLayer("hero-orb-a", {
      inset: "-14%",
      background: `radial-gradient(circle at 18% 20%, ${mixWithTransparent(accent, 26 * profile.accent)} 0%, ${mixWithTransparent(accent, 14 * profile.accent)} 18%, transparent ${56 * profile.spread}%)`,
      transform: `scale(${1 + (profile.spread - 1) * 0.12})`,
    }),
    createLayer("hero-orb-b", {
      inset: "-18%",
      background: `radial-gradient(circle at 82% 26%, ${mixWithTransparent(altAccent, 18 * profile.accent)} 0%, ${mixWithTransparent(altAccent, 10 * profile.accent)} 20%, transparent ${44 * profile.spread}%)`,
    }),
    createLayer("hero-beam", {
      inset: "-10%",
      background: `linear-gradient(124deg, transparent 30%, ${mixWithTransparent(accent, 14 * profile.accent)} 56%, ${mixWithTransparent(altAccent, 12 * profile.accent)} 66%, transparent 80%)`,
      transform: `translateX(${emphasis === "immersive" ? "-2%" : "0"})`,
    }),
    createLayer("hero-safe-zone", {
      background: `radial-gradient(circle at 50% 48%, ${mixWithTransparent(BACKGROUND_COLOR, emphasis === "immersive" ? 78 : 86)} 0%, ${mixWithTransparent(BACKGROUND_COLOR, emphasis === "immersive" ? 60 : 72)} 28%, transparent 72%)`,
    }),
  ];
}

function sectionBandLayers(accent: string, altAccent: string, emphasis: SceneBackgroundEmphasis): SceneBackgroundLayer[] {
  const profile = EMPHASIS_PROFILES[emphasis];
  return [
    createLayer("section-haze", {
      background: `linear-gradient(180deg, ${mixWithBase(accent, 6 * profile.density)} 0%, ${BACKGROUND_COLOR} 56%, ${mixWithBase(altAccent, 10 * profile.density)} 100%)`,
    }),
    createLayer("section-band-major", {
      top: `${8 - (profile.spread - 1) * 10}%`,
      left: `${-16 - (profile.spread - 1) * 12}%`,
      width: `${76 + (profile.spread - 1) * 34}%`,
      height: `${34 + (profile.spread - 1) * 34}%`,
      inset: "auto",
      borderRadius: "44px",
      transform: `rotate(-10deg)`,
      background: `linear-gradient(135deg, ${mixWithTransparent(accent, 20 * profile.accent)} 0%, ${mixWithTransparent(altAccent, 34 * profile.accent)} 100%)`,
    }),
    createLayer("section-band-minor", {
      right: `${-18 - (profile.spread - 1) * 10}%`,
      bottom: `${-10 - (profile.spread - 1) * 8}%`,
      width: `${62 + (profile.spread - 1) * 24}%`,
      height: `${28 + (profile.spread - 1) * 18}%`,
      inset: "auto",
      borderRadius: "36px",
      transform: "rotate(10deg)",
      background: `linear-gradient(135deg, ${mixWithTransparent(altAccent, 16 * profile.accent)} 0%, ${mixWithTransparent(accent, 14 * profile.accent)} 100%)`,
    }),
    createLayer("section-safe-zone", {
      background: `linear-gradient(180deg, ${mixWithTransparent(BACKGROUND_COLOR, 82)} 12%, ${mixWithTransparent(BACKGROUND_COLOR, emphasis === "immersive" ? 70 : 80)} 48%, ${mixWithTransparent(BACKGROUND_COLOR, 82)} 90%)`,
    }),
  ];
}

function outlineGridLayers(accent: string, emphasis: SceneBackgroundEmphasis): SceneBackgroundLayer[] {
  const profile = EMPHASIS_PROFILES[emphasis];
  return [
    createLayer("outline-base", {
      background: `linear-gradient(180deg, ${mixWithBase(accent, 5 * profile.density)} 0%, ${BACKGROUND_COLOR} 100%)`,
    }),
    createLayer("outline-grid", {
      opacity: emphasis === "balanced" ? 1 : 0.88,
      backgroundImage: [
        `linear-gradient(${mixWithTransparent(accent, 10 * profile.accent)} 1px, transparent 1px)`,
        `linear-gradient(90deg, ${mixWithTransparent(accent, 8 * profile.accent)} 1px, transparent 1px)`,
      ].join(","),
      backgroundSize: emphasis === "balanced" ? "96px 96px, 96px 96px" : "108px 108px, 108px 108px",
      backgroundPosition: "0 18px, 18px 0",
    }),
    createLayer("outline-highlight", {
      inset: "-12%",
      background: `radial-gradient(circle at 82% 12%, ${mixWithTransparent(accent, 14 * profile.accent)} 0%, transparent ${44 * profile.spread}%)`,
    }),
    createLayer("outline-safe-zone", {
      background: `linear-gradient(180deg, ${mixWithTransparent(BACKGROUND_COLOR, 94)} 0%, ${mixWithTransparent(BACKGROUND_COLOR, 88)} 100%)`,
    }),
  ];
}

function quoteFocusLayers(accent: string, altAccent: string, emphasis: SceneBackgroundEmphasis): SceneBackgroundLayer[] {
  const profile = EMPHASIS_PROFILES[emphasis];
  return [
    createLayer("quote-base", {
      background: `linear-gradient(180deg, ${mixWithBase(accent, 6 * profile.density)} 0%, ${BACKGROUND_COLOR} 100%)`,
    }),
    createLayer("quote-halo", {
      inset: "-16%",
      background: `radial-gradient(circle at 50% 42%, ${mixWithTransparent(accent, 22 * profile.accent)} 0%, ${mixWithTransparent(accent, 12 * profile.accent)} 22%, transparent ${48 * profile.spread}%)`,
    }),
    createLayer("quote-pulse", {
      inset: "-8%",
      background: `radial-gradient(circle at 26% 24%, ${mixWithTransparent(altAccent, 14 * profile.accent)} 0%, transparent ${34 * profile.spread}%)`,
    }),
    createLayer("quote-safe-zone", {
      background: `radial-gradient(circle at 50% 48%, ${mixWithTransparent(BACKGROUND_COLOR, emphasis === "immersive" ? 86 : 92)} 0%, ${mixWithTransparent(BACKGROUND_COLOR, emphasis === "immersive" ? 70 : 80)} 34%, transparent 76%)`,
    }),
  ];
}

function closingWashLayers(accent: string, altAccent: string, emphasis: SceneBackgroundEmphasis): SceneBackgroundLayer[] {
  const profile = EMPHASIS_PROFILES[emphasis];
  return [
    createLayer("closing-base", {
      background: `linear-gradient(180deg, ${mixWithBase(altAccent, 6 * profile.density)} 0%, ${BACKGROUND_COLOR} 44%, ${mixWithBase(accent, 10 * profile.density)} 100%)`,
    }),
    createLayer("closing-wash-top", {
      inset: "-20%",
      background: `radial-gradient(circle at 84% 16%, ${mixWithTransparent(accent, 24 * profile.accent)} 0%, ${mixWithTransparent(accent, 14 * profile.accent)} 20%, transparent ${54 * profile.spread}%)`,
    }),
    createLayer("closing-wash-bottom", {
      inset: "-24%",
      background: `radial-gradient(circle at 16% 88%, ${mixWithTransparent(altAccent, 18 * profile.accent)} 0%, ${mixWithTransparent(altAccent, 10 * profile.accent)} 24%, transparent ${52 * profile.spread}%)`,
    }),
    createLayer("closing-ribbon", {
      inset: "-12%",
      background: `linear-gradient(118deg, transparent 36%, ${mixWithTransparent(accent, 14 * profile.accent)} 58%, transparent 78%)`,
    }),
    createLayer("closing-safe-zone", {
      background: `radial-gradient(circle at 50% 46%, ${mixWithTransparent(BACKGROUND_COLOR, emphasis === "immersive" ? 76 : 84)} 0%, ${mixWithTransparent(BACKGROUND_COLOR, emphasis === "immersive" ? 56 : 68)} 34%, transparent 80%)`,
    }),
  ];
}

export function getSceneBackgroundRenderModel(
  background: SceneBackground | null | undefined
): SceneBackgroundRenderModel | null {
  if (!background || background.kind !== "scene") {
    return null;
  }

  const emphasis = background.emphasis ?? "balanced";
  const accent = resolveAccentColor(background.colorToken);
  const altAccent = resolveSecondaryAccent(background.colorToken);

  let layers: SceneBackgroundLayer[];
  switch (background.preset) {
    case "hero-glow":
      layers = heroGlowLayers(accent, altAccent, emphasis);
      break;
    case "section-band":
      layers = sectionBandLayers(accent, altAccent, emphasis);
      break;
    case "outline-grid":
      layers = outlineGridLayers(accent, emphasis);
      break;
    case "quote-focus":
      layers = quoteFocusLayers(accent, altAccent, emphasis);
      break;
    case "closing-wash":
      layers = closingWashLayers(accent, altAccent, emphasis);
      break;
    default:
      return null;
  }

  return {
    attributes: {
      "data-scene-background": background.kind,
      "data-scene-preset": background.preset,
      "data-scene-emphasis": emphasis,
    },
    frameStyle: {
      position: "relative",
      width: "100%",
      height: "100%",
      overflow: "hidden",
      backgroundColor: BACKGROUND_COLOR,
      isolation: "isolate",
    },
    contentStyle: {
      position: "relative",
      zIndex: 1,
      width: "100%",
      height: "100%",
    },
    layers,
  };
}

function toKebabCase(property: string): string {
  return property.replace(/[A-Z]/g, (match) => `-${match.toLowerCase()}`);
}

export function styleMapToCss(style: StyleMap): string {
  return Object.entries(style)
    .map(([property, value]) => `${toKebabCase(property)}:${String(value)}`)
    .join(";");
}

import type { ComponentType } from "react";
import {
  Award,
  ChartColumn,
  CircleCheckBig,
  Clock,
  Cloud,
  Code,
  Database,
  Eye,
  FileText,
  Gift,
  Globe,
  Headphones,
  Heart,
  Image as ImageIcon,
  Layers,
  Lightbulb,
  Link,
  Lock,
  Mail,
  MapPin,
  Monitor,
  Package,
  Palette,
  Rocket,
  Settings,
  Shield,
  Star,
  Target,
  TrendingUp,
  TriangleAlert,
  Users,
  Zap,
} from "lucide-react";

// We intentionally read Lucide's internal icon nodes so editor layouts and
// reveal HTML can share the same SVG source. This relies on Lucide's current
// package layout, so keep lucide-react pinned to the exact version in package.json.

import { __iconNode as awardIconNode } from "lucide-react/dist/esm/icons/award.js";
import { __iconNode as chartColumnIconNode } from "lucide-react/dist/esm/icons/chart-column.js";
import { __iconNode as circleCheckBigIconNode } from "lucide-react/dist/esm/icons/circle-check-big.js";
import { __iconNode as clockIconNode } from "lucide-react/dist/esm/icons/clock.js";
import { __iconNode as cloudIconNode } from "lucide-react/dist/esm/icons/cloud.js";
import { __iconNode as codeIconNode } from "lucide-react/dist/esm/icons/code.js";
import { __iconNode as databaseIconNode } from "lucide-react/dist/esm/icons/database.js";
import { __iconNode as eyeIconNode } from "lucide-react/dist/esm/icons/eye.js";
import { __iconNode as fileTextIconNode } from "lucide-react/dist/esm/icons/file-text.js";
import { __iconNode as giftIconNode } from "lucide-react/dist/esm/icons/gift.js";
import { __iconNode as globeIconNode } from "lucide-react/dist/esm/icons/globe.js";
import { __iconNode as headphonesIconNode } from "lucide-react/dist/esm/icons/headphones.js";
import { __iconNode as heartIconNode } from "lucide-react/dist/esm/icons/heart.js";
import { __iconNode as imageIconNode } from "lucide-react/dist/esm/icons/image.js";
import { __iconNode as layersIconNode } from "lucide-react/dist/esm/icons/layers.js";
import { __iconNode as lightbulbIconNode } from "lucide-react/dist/esm/icons/lightbulb.js";
import { __iconNode as linkIconNode } from "lucide-react/dist/esm/icons/link.js";
import { __iconNode as lockIconNode } from "lucide-react/dist/esm/icons/lock.js";
import { __iconNode as mailIconNode } from "lucide-react/dist/esm/icons/mail.js";
import { __iconNode as mapPinIconNode } from "lucide-react/dist/esm/icons/map-pin.js";
import { __iconNode as monitorIconNode } from "lucide-react/dist/esm/icons/monitor.js";
import { __iconNode as packageIconNode } from "lucide-react/dist/esm/icons/package.js";
import { __iconNode as paletteIconNode } from "lucide-react/dist/esm/icons/palette.js";
import { __iconNode as rocketIconNode } from "lucide-react/dist/esm/icons/rocket.js";
import { __iconNode as settingsIconNode } from "lucide-react/dist/esm/icons/settings.js";
import { __iconNode as shieldIconNode } from "lucide-react/dist/esm/icons/shield.js";
import { __iconNode as starIconNode } from "lucide-react/dist/esm/icons/star.js";
import { __iconNode as targetIconNode } from "lucide-react/dist/esm/icons/target.js";
import { __iconNode as trendingUpIconNode } from "lucide-react/dist/esm/icons/trending-up.js";
import { __iconNode as triangleAlertIconNode } from "lucide-react/dist/esm/icons/triangle-alert.js";
import { __iconNode as usersIconNode } from "lucide-react/dist/esm/icons/users.js";
import { __iconNode as zapIconNode } from "lucide-react/dist/esm/icons/zap.js";

export type IconNode = Array<[string, Record<string, string>]>;

export type LayoutIconKey =
  | "award"
  | "chart"
  | "check"
  | "clock"
  | "cloud"
  | "code"
  | "database"
  | "eye"
  | "file"
  | "gift"
  | "globe"
  | "headphones"
  | "heart"
  | "image"
  | "layers"
  | "lightbulb"
  | "link"
  | "lock"
  | "mail"
  | "map-pin"
  | "monitor"
  | "package"
  | "palette"
  | "rocket"
  | "settings"
  | "shield"
  | "star"
  | "target"
  | "trending"
  | "triangle-alert"
  | "users"
  | "zap";

interface LayoutIconDefinition {
  component: ComponentType<{ className?: string }>;
  node: IconNode;
}

const ICON_DEFINITIONS: Record<LayoutIconKey, LayoutIconDefinition> = {
  award: { component: Award, node: awardIconNode },
  chart: { component: ChartColumn, node: chartColumnIconNode },
  check: { component: CircleCheckBig, node: circleCheckBigIconNode },
  clock: { component: Clock, node: clockIconNode },
  cloud: { component: Cloud, node: cloudIconNode },
  code: { component: Code, node: codeIconNode },
  database: { component: Database, node: databaseIconNode },
  eye: { component: Eye, node: eyeIconNode },
  file: { component: FileText, node: fileTextIconNode },
  gift: { component: Gift, node: giftIconNode },
  globe: { component: Globe, node: globeIconNode },
  headphones: { component: Headphones, node: headphonesIconNode },
  heart: { component: Heart, node: heartIconNode },
  image: { component: ImageIcon, node: imageIconNode },
  layers: { component: Layers, node: layersIconNode },
  lightbulb: { component: Lightbulb, node: lightbulbIconNode },
  link: { component: Link, node: linkIconNode },
  lock: { component: Lock, node: lockIconNode },
  mail: { component: Mail, node: mailIconNode },
  "map-pin": { component: MapPin, node: mapPinIconNode },
  monitor: { component: Monitor, node: monitorIconNode },
  package: { component: Package, node: packageIconNode },
  palette: { component: Palette, node: paletteIconNode },
  rocket: { component: Rocket, node: rocketIconNode },
  settings: { component: Settings, node: settingsIconNode },
  shield: { component: Shield, node: shieldIconNode },
  star: { component: Star, node: starIconNode },
  target: { component: Target, node: targetIconNode },
  trending: { component: TrendingUp, node: trendingUpIconNode },
  "triangle-alert": { component: TriangleAlert, node: triangleAlertIconNode },
  users: { component: Users, node: usersIconNode },
  zap: { component: Zap, node: zapIconNode },
};

const QUERY_TO_ICON_KEY: Array<[string, LayoutIconKey]> = [
  ["zap", "zap"],
  ["lightning", "zap"],
  ["speed", "zap"],
  ["fast", "zap"],
  ["performance", "zap"],
  ["shield", "shield"],
  ["security", "shield"],
  ["protect", "shield"],
  ["safe", "shield"],
  ["target", "target"],
  ["goal", "target"],
  ["aim", "target"],
  ["focus", "target"],
  ["users", "users"],
  ["team", "users"],
  ["people", "users"],
  ["community", "users"],
  ["chart", "chart"],
  ["data", "chart"],
  ["analytics", "chart"],
  ["stats", "chart"],
  ["globe", "globe"],
  ["world", "globe"],
  ["global", "globe"],
  ["internet", "globe"],
  ["lightbulb", "lightbulb"],
  ["idea", "lightbulb"],
  ["innovation", "lightbulb"],
  ["creative", "lightbulb"],
  ["rocket", "rocket"],
  ["launch", "rocket"],
  ["growth", "rocket"],
  ["startup", "rocket"],
  ["heart", "heart"],
  ["love", "heart"],
  ["health", "heart"],
  ["care", "heart"],
  ["star", "star"],
  ["quality", "star"],
  ["rating", "star"],
  ["favorite", "star"],
  ["check", "check"],
  ["success", "check"],
  ["done", "check"],
  ["complete", "check"],
  ["clock", "clock"],
  ["time", "clock"],
  ["schedule", "clock"],
  ["duration", "clock"],
  ["layers", "layers"],
  ["stack", "layers"],
  ["architecture", "layers"],
  ["structure", "layers"],
  ["settings", "settings"],
  ["config", "settings"],
  ["gear", "settings"],
  ["tool", "settings"],
  ["award", "award"],
  ["prize", "award"],
  ["achievement", "award"],
  ["trophy", "award"],
  ["trending", "trending"],
  ["increase", "trending"],
  ["rise", "trending"],
  ["progress", "trending"],
  ["database", "database"],
  ["storage", "database"],
  ["server", "database"],
  ["lock", "lock"],
  ["privacy", "lock"],
  ["secure", "lock"],
  ["cloud", "cloud"],
  ["saas", "cloud"],
  ["hosting", "cloud"],
  ["code", "code"],
  ["develop", "code"],
  ["program", "code"],
  ["tech", "code"],
  ["eye", "eye"],
  ["vision", "eye"],
  ["view", "eye"],
  ["observe", "eye"],
  ["file", "file"],
  ["document", "file"],
  ["report", "file"],
  ["gift", "gift"],
  ["bonus", "gift"],
  ["reward", "gift"],
  ["headphones", "headphones"],
  ["audio", "headphones"],
  ["support", "headphones"],
  ["link", "link"],
  ["connect", "link"],
  ["chain", "link"],
  ["integration", "link"],
  ["mail", "mail"],
  ["email", "mail"],
  ["message", "mail"],
  ["contact", "mail"],
  ["location", "map-pin"],
  ["map", "map-pin"],
  ["place", "map-pin"],
  ["address", "map-pin"],
  ["monitor", "monitor"],
  ["screen", "monitor"],
  ["display", "monitor"],
  ["desktop", "monitor"],
  ["package", "package"],
  ["product", "package"],
  ["box", "package"],
  ["delivery", "package"],
  ["palette", "palette"],
  ["design", "palette"],
  ["color", "palette"],
  ["art", "palette"],
  ["image", "image"],
  ["photo", "image"],
  ["picture", "image"],
  ["alert", "triangle-alert"],
  ["warning", "triangle-alert"],
  ["risk", "triangle-alert"],
];

export function normalizeLayoutIconQuery(query: string): string {
  return query.toLowerCase().replace(/[-_\s]+/g, "");
}

export function resolveLayoutIconKey(query: string): LayoutIconKey {
  const normalizedQuery = normalizeLayoutIconQuery(query);

  for (const [needle, iconKey] of QUERY_TO_ICON_KEY) {
    if (normalizedQuery.includes(needle)) {
      return iconKey;
    }
  }

  return "star";
}

export function getLayoutIconComponent(query: string): ComponentType<{ className?: string }> {
  return ICON_DEFINITIONS[resolveLayoutIconKey(query)].component;
}

export function getLayoutIconNode(query: string): IconNode {
  return ICON_DEFINITIONS[resolveLayoutIconKey(query)].node;
}


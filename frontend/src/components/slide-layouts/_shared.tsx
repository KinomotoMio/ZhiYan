"use client";

import Image from "next/image";
import {
  Zap, Shield, Target, Users, BarChart3, Globe,
  Lightbulb, Rocket, Heart, Star, CheckCircle, Clock,
  Layers, Settings, Award, TrendingUp, Database, Lock,
  Cloud, Code, Eye, FileText, Gift, Headphones,
  Link, Mail, MapPin, Monitor, Package, Palette,
} from "lucide-react";

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  zap: Zap, lightning: Zap, speed: Zap, fast: Zap, performance: Zap,
  shield: Shield, security: Shield, protect: Shield, safe: Shield,
  target: Target, goal: Target, aim: Target, focus: Target,
  users: Users, team: Users, people: Users, community: Users,
  chart: BarChart3, data: BarChart3, analytics: BarChart3, stats: BarChart3,
  globe: Globe, world: Globe, global: Globe, internet: Globe,
  lightbulb: Lightbulb, idea: Lightbulb, innovation: Lightbulb, creative: Lightbulb,
  rocket: Rocket, launch: Rocket, growth: Rocket, startup: Rocket,
  heart: Heart, love: Heart, health: Heart, care: Heart,
  star: Star, quality: Star, rating: Star, favorite: Star,
  check: CheckCircle, success: CheckCircle, done: CheckCircle, complete: CheckCircle,
  clock: Clock, time: Clock, schedule: Clock, duration: Clock,
  layers: Layers, stack: Layers, architecture: Layers, structure: Layers,
  settings: Settings, config: Settings, gear: Settings, tool: Settings,
  award: Award, prize: Award, achievement: Award, trophy: Award,
  trending: TrendingUp, increase: TrendingUp, rise: TrendingUp, progress: TrendingUp,
  database: Database, storage: Database, server: Database,
  lock: Lock, privacy: Lock, secure: Lock,
  cloud: Cloud, saas: Cloud, hosting: Cloud,
  code: Code, develop: Code, program: Code, tech: Code,
  eye: Eye, vision: Eye, view: Eye, observe: Eye,
  file: FileText, document: FileText, report: FileText,
  gift: Gift, bonus: Gift, reward: Gift,
  headphones: Headphones, audio: Headphones, support: Headphones,
  link: Link, connect: Link, chain: Link, integration: Link,
  mail: Mail, email: Mail, message: Mail, contact: Mail,
  location: MapPin, map: MapPin, place: MapPin, address: MapPin,
  monitor: Monitor, screen: Monitor, display: Monitor, desktop: Monitor,
  package: Package, product: Package, box: Package, delivery: Package,
  palette: Palette, design: Palette, color: Palette, art: Palette,
};

export function LayoutIcon({ query, className }: { query: string; className?: string }) {
  const key = query.toLowerCase().replace(/[-_\s]+/g, "");
  // Try to match keywords
  for (const [k, Icon] of Object.entries(ICON_MAP)) {
    if (key.includes(k)) {
      return <Icon className={className} />;
    }
  }
  // Default fallback
  return <Star className={className} />;
}

export function ImagePlaceholder({ prompt, alt, url }: { prompt: string; alt?: string; url?: string | null }) {
  if (url) {
    return (
      <div className="relative h-full w-full">
        <Image
          src={url}
          alt={alt || prompt}
          fill
          unoptimized
          sizes="100vw"
          className="object-cover"
        />
      </div>
    );
  }
  return (
    <div className="w-full h-full bg-gray-100 flex flex-col items-center justify-center text-gray-400">
      <Eye className="w-10 h-10 mb-2 opacity-50" />
      <span style={{ fontSize: 13 }} className="text-center px-4 opacity-60">{prompt}</span>
    </div>
  );
}

import type gsap from "gsap";

export interface CentiDeckSlideDescriptor {
  slideId: string;
  title: string;
  plainText: string;
  moduleSource: string;
  notes?: string | null;
  audioUrl?: string | null;
  actions?: Record<string, unknown>[];
  drilldowns?: Record<string, unknown>[];
  background?: Record<string, unknown> | null;
  transition?: string | null;
}

export interface CentiDeckTheme {
  [key: string]: unknown;
}

export interface CentiDeckDeckInput {
  slides: CentiDeckSlideDescriptor[];
  theme?: CentiDeckTheme | null;
  title?: string;
}

export interface CentiDeckSlideContext {
  slideId: string;
  slideIndex: number;
  section: HTMLElement;
  gsap: typeof gsap;
  /** Go to a slide by index. */
  goTo: (index: number) => void;
  /** Register a cleanup function invoked when this slide leaves. */
  registerCleanup: (fn: () => void) => void;
}

/**
 * The shape an authored slide module must export as default.
 * Matches centi-deck's slide contract — render() returns an HTML string or
 * HTMLElement; enter/leave are optional lifecycle hooks; actions/drilldowns
 * are optional interaction handlers (UI not yet wired in ZhiYan v1).
 */
export interface CentiDeckSlideModule {
  id?: string;
  title?: string;
  render: () => string | HTMLElement;
  enter?: (section: HTMLElement, ctx: CentiDeckSlideContext) => void;
  leave?: (section: HTMLElement, ctx: CentiDeckSlideContext) => void;
  actions?: Record<string, unknown>;
  drilldowns?: Record<string, unknown>;
}

export interface LoadedCentiDeckSlide {
  descriptor: CentiDeckSlideDescriptor;
  module: CentiDeckSlideModule;
}

export type CentiDeckRuntimeMode = "interactive" | "presenter" | "thumbnail" | "print";

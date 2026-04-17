const CENTI_DECK_RUNTIME_STYLE_ID = "zhiyan-centi-deck-runtime-styles";

export function getCentiDeckRuntimeStyles(): string {
  return `
.centi-deck-root {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  isolation: isolate;
}

.centi-deck-slides {
  position: relative;
  width: 100%;
  height: 100%;
}

.centi-deck-slide {
  position: absolute;
  inset: 0;
  opacity: 0;
  pointer-events: none;
  overflow: hidden;
  container-type: size;
  container-name: centi-slide;
  will-change: opacity, transform, filter;
  transition:
    opacity 600ms cubic-bezier(0.22, 1, 0.36, 1),
    transform 600ms cubic-bezier(0.22, 1, 0.36, 1),
    filter 600ms cubic-bezier(0.22, 1, 0.36, 1);
}

.centi-deck-slide.is-active {
  z-index: 1;
  opacity: 1;
  pointer-events: auto;
}

.centi-deck-slide:not(.is-active) {
  transform: scale(1.03);
  filter: blur(8px);
}

.centi-deck-slide.is-exiting {
  transform: scale(0.95);
  filter: blur(5px);
}

.centi-deck-root[data-centi-mode="thumbnail"] .centi-deck-slide,
.centi-deck-root[data-centi-mode="presenter"] .centi-deck-slide,
.centi-deck-root[data-centi-mode="print"] .centi-deck-slide {
  transition: none !important;
}

.centi-deck-root[data-centi-mode="thumbnail"] .centi-deck-slide:not(.is-active),
.centi-deck-root[data-centi-mode="presenter"] .centi-deck-slide:not(.is-active),
.centi-deck-root[data-centi-mode="print"] .centi-deck-slide:not(.is-active),
.centi-deck-root[data-centi-mode="thumbnail"] .centi-deck-slide.is-exiting,
.centi-deck-root[data-centi-mode="presenter"] .centi-deck-slide.is-exiting,
.centi-deck-root[data-centi-mode="print"] .centi-deck-slide.is-exiting {
  transform: none;
  filter: none;
}
`.trim();
}

export function ensureCentiDeckRuntimeStyles(): void {
  if (typeof document === "undefined") return;
  if (document.getElementById(CENTI_DECK_RUNTIME_STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = CENTI_DECK_RUNTIME_STYLE_ID;
  style.textContent = getCentiDeckRuntimeStyles();
  document.head.appendChild(style);
}

# Centi-deck Anti-Patterns

## Avoid These Outcomes

- Long document paragraphs that read like an article section instead of a slide.
- Weak title-only pages with no supporting visual structure or focal point.
- Generic webpage sections: navbar-like chrome, repeated CTA cards, or marketing landing-page composition that ignores single-slide pacing.
- Pages where every text block has similar size and weight, so nothing reads as primary.
- Consecutive slides that reuse the exact same card grid or bullet stack without narrative reason.
- Lifecycle hooks that animate `'h1'`, `'p'`, `.card`, or other global selectors without scoping through `el`.

## Recovery Heuristics

- If the slide feels like a document section, promote one statement and remove detail.
- If the page feels empty, add one supporting structure block instead of more paragraphs.
- If the page feels repetitive, switch recipes rather than restyling the same structure.

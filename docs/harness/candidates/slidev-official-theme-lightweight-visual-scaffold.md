# Slidev Official Theme Plus Lightweight Visual Scaffold

## Situation

Issue `#221` follows `#220`: once Slidev references become an executable protocol, the next gap is not reference selection itself, but whether the generated deck immediately reads like a presentation instead of a markdown report. The system already has an official theme baseline, selected references, and review/validation telemetry, but it still needs a lightweight visual scaffold that can be enforced without ejecting into a custom local theme.

## Candidate Rule

- Keep the official Slidev theme as the baseline rather than forking into a local theme package too early.
- Add a lightweight scaffold through deck-level frontmatter, `themeConfig`, and stronger per-role class/layout cues.
- Treat visual delivery as a separate layer from reference selection: references answer "what recipe was chosen", while the scaffold answers "does the deck visually read like a presentation".
- Strengthen review and validation telemetry around document-like slides, inline-style overuse, and theme-marker presence before escalating to deeper theme engineering.

## Why It Matters

There is a useful middle ground between plain markdown output and a fully custom Slidev theme:

- official theme keeps compatibility and maintenance cost low
- deck-level scaffold creates a reusable brand rhythm
- per-role recipe cues make key pages look more like slides than report sections
- review/validation warnings can measure visual drift without blocking save on subjective taste

This lets the system improve first-glance PPT quality while keeping scope smaller than a theme-engineering project.

## Reuse Guidance

For future slide-generation systems:

1. Start with an official renderer/theme baseline when possible.
2. Add a thin scaffold layer before building a fully custom theme.
3. Make the scaffold visible to generation, review, validation, and artifact metadata together.
4. Keep visual warnings observable and actionable even when they are not hard save gates.

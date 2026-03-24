---
name: slidev-design-system
description: Slidev references layer for deck-level styles plus per-slide layout/block recipes. Use it to turn selected references into executable slide structure instead of free-form markdown aesthetics.
version: 0.2.0
command: /slidev-design-system
---

# Slidev Design System

## Purpose

Use this skill to interpret the local Slidev references layer.
The source of truth lives in `references/styles`, `references/layouts`, and `references/blocks`.
This skill explains how to apply those assets; it is not the only place where recipe details live.

## References Layer

- `references/styles/`
  - Deck-level baseline.
  - Defines theme, tone, selection signals, required classes, and anti-patterns.
- `references/layouts/`
  - Slide-role skeletons.
  - Defines which roles a layout applies to, the preferred Slidev layout, required patterns/classes, and forbidden patterns.
- `references/blocks/`
  - In-slide information blocks.
  - Defines recommended structure, required signals, visual constraints, and anti-patterns.

## Execution Order

Always apply references in this order:

1. Select one deck-level style.
2. For each slide, select one layout recipe.
3. For each slide, select one or two block recipes.
4. Generate markdown that explicitly realizes those selected recipes.
5. Review and validate against the same selected references.

## How To Use The References

- `style`
  - Sets the deck baseline: official theme, tone, and deck-wide anti-patterns.
  - Do not switch themes or visual direction after selection.
- `layout`
  - Sets the page skeleton.
  - Prefer the selected native `layout:` when it exists; otherwise realize the recipe with `class:`, grid, table, Mermaid, quote, or callout.
- `blocks`
  - Set page-level content shape and density.
  - Keep within each block's visual constraints; do not exceed the intended information capacity.

## Non-Negotiable Rules

- References outrank free-form visual improvisation.
- Do not output pages that look like markdown article sections when the selected recipe expects a presentation skeleton.
- Do not rely on ad-hoc inline `style=` to compensate for missing recipe structure.
- Do not claim to use a selected layout/block if the resulting slide does not show its required signals.
- Keep `slide_role` as the control plane; references are the execution layer that makes the role visible in Slidev.

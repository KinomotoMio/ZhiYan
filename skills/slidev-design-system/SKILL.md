---
name: slidev-design-system
description: Slidev deck visual design guidance for tech-launch style presentations. Use it to make slides feel like presentation pages instead of markdown documents.
version: 0.1.0
command: /slidev-design-system
---

# Slidev Design System

## Purpose

Use this skill to keep Slidev decks visually intentional.
It does not replace `slide_role`; it teaches how each role should look when rendered as a Slidev deck.

## Deck-level Direction

- Default baseline: official `seriph` theme
- Desired feel: tech product launch / strategy presentation
- Prefer stable page rhythm over ad-hoc decoration
- Avoid raw markdown-report aesthetics

## Visual Rules

- Cover
  - strong title, short subtitle, sparse density
  - prefer `layout: cover` or `layout: center`
  - use `deck-cover`
- Context
  - use one structural cue beyond bullets
  - prefer compact bullets plus quote/callout
  - use `deck-context`
- Framework
  - must feel modeled, not listed
  - prefer Mermaid, table, or grid
  - use `deck-framework`
- Comparison
  - must create left/right contrast
  - prefer `layout: two-cols` or a strong compare table
  - use `deck-comparison`
- Closing
  - must feel conclusive
  - prefer `layout: end` or `layout: center`
  - use `deck-closing`

## Anti-Patterns

- Do not output pages that look like markdown article sections
- Do not stack long bullet lists without one visual structure
- Do not rely on ad-hoc inline `style=` for every page
- Do not choose a recipe class and then fail to express it in the slide body

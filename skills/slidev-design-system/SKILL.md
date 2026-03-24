---
name: slidev-design-system
description: Slidev deck visual design system for styles, layouts, and block recipes. Use it to select stable references before writing deck markdown.
version: 0.1.0
command: /slidev-design-system
---

# Slidev Design System

## Purpose

Use this skill when you need deck-level visual direction and page-level recipe selection for Slidev.
Treat styles, layouts, and blocks as a static references layer that constrains generation, instead of asking the model to improvise visual design from scratch.

## Core Rule

- `slide_role` remains the control-plane intent.
- Slidev layout/pattern remains the rendering plane.
- This skill provides the references layer in between: `style` + `layout recipe` + `block recipe`.

## Reference Types

- **styles**
  - deck-level visual direction
  - palette, density, tone, typography tendency, emphasis rules, anti-patterns
- **layouts**
  - role-aware page skeletons
  - when to use `cover`, `two-cols`, `end`, or plain structure with wrappers
- **blocks**
  - repeatable content modules
  - hero title, compact bullets, quote/callout, framework explainer, compare split, takeaway-next-steps

## Selection Rules

- Choose exactly 1 deck-level style for the whole deck.
- Choose 1 layout recipe per slide.
- Choose 1-2 block recipes per slide.
- Prefer stable references over creative drift.
- If a page already claims a recipe, do not degrade it into a plain bullet dump.

## Good Usage

- cover -> select one style + `cover-hero` layout + `hero-title` block
- framework -> keep the style, use `framework-visual` layout + `framework-explainer` block
- comparison -> keep the style, use `comparison-split` layout + `compare-split` block
- closing -> keep the style, use `closing-takeaway` layout + `takeaway-next-steps` block

## Anti-Patterns

- Do not invent an ad-hoc visual system per slide.
- Do not choose different deck-level styles inside one deck.
- Do not use references only as labels; the final markdown should visibly reflect them.
- Do not treat block names as decorative tags; they imply actual structure and density constraints.

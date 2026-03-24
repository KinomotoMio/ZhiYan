---
name: slidev-syntax
description: Slidev markdown syntax reference for frontmatter, slide separators, layouts, code blocks, and Mermaid diagrams.
version: 0.1.0
command: /slidev-syntax
---

# Slidev Syntax

## Purpose

Use this skill when you need authoritative Slidev markdown structure while generating deck source.
Treat Slidev native structure as a first-class layout language, not just a markdown bullet renderer.

## Core Syntax

- Separate slides with `---`
- Put global frontmatter on the first slide inside `---` fences
- Use per-slide frontmatter like `layout: cover`, `layout: center`, `layout: two-cols`, `layout: quote`, `layout: section`, or `layout: end` when needed
- Use fenced code blocks for code samples
- Use fenced `mermaid` blocks for diagrams
- Prefer mixing structures: columns, grids, compare, quote, section divider, code, diagram
- Use `class:` and `transition:` sparingly to reinforce structure, not as decoration spam
- `themeConfig` and scoped classes are allowed when they create clear visual hierarchy

## Example

```md
---
theme: default
title: Demo Deck
---

# Opening

---
layout: center
---

## Architecture

```mermaid
graph TD
  A[Input] --> B[Process]
  B --> C[Output]
```
```

## Useful Patterns

- **Cover**
  - prefer `layout: cover` or `layout: center`
  - use one strong title + one short positioning line
- **Context**
  - prefer a compact quote, callout, or 2-4 bullets
  - avoid turning context pages into dense body text
- **Section divider**
  - one strong heading + one supporting line
  - `layout: section` or `layout: center` works better than a plain body page
- **Compare**
  - use `layout: two-cols`, a grid, or a table with explicit contrast labels
- **Framework**
  - prefer 2x2 grid / numbered stack / Mermaid over long flat bullets
- **Detail / Evidence / Process**
  - if there is no stable built-in layout, prefer native structures like Mermaid, tables, `div` grids, or scoped callouts
  - do not force every structured page into a built-in Slidev layout name
- **Recommendation**
  - one headline + 2-4 actions / decisions
- **Closing**
  - avoid ending on a weak bullet dump; make the last slide a takeaway or next-step page
  - `layout: end` is a good default for a deliberate finish

## Native Mapping Hints

- `cover` role
  - first choice: `layout: cover`
  - fallback: `layout: center`
- `comparison` role
  - first choice: `layout: two-cols`
  - fallback: explicit markdown table
- `section-divider` role
  - first choice: `layout: section`
  - fallback: `layout: center`
- `highlight` role
  - first choice: `layout: quote`
  - fallback: one strong quoted statement
- `closing` role
  - first choice: `layout: end`
  - fallback: centered takeaway / next-step structure

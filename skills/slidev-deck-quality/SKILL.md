---
name: slidev-deck-quality
description: Slidev deck information architecture and structure-quality guidance for page roles, density, and anti-pattern checks.
version: 0.1.0
command: /slidev-deck-quality
---

# Slidev Deck Quality

## Purpose

Use this skill to plan a Slidev deck before writing markdown and to review whether the final deck has enough structural variety.

## Information Architecture Rules

- Every deck should have a real `cover` and `closing`
- Do not let most pages collapse into the same bullet-list shape
- Match page role to communication goal:
  - `context`: frame the problem or current state
  - `framework`: explain a model, stack, or mental map
  - `detail`: unpack one concrete area
  - `comparison`: contrast options, before/after, or tradeoffs
  - `recommendation`: state decision, next step, or operating rule
- Prefer 2-4 dense ideas per slide instead of 5-8 shallow bullets

## Content Density Rules

- A bullet slide should usually stay within 3-5 bullets
- If three or more consecutive slides share the same structure, vary the next one
- Closing slides should end with a takeaway, decision, or next-step signal

## Role to Shape Mapping

- `cover`
  - strong title + one positioning line
  - prefer `layout: cover` or `layout: center`
- `context`
  - 2-4 bullets, a short problem statement, or a lightweight quote/callout
- `framework`
  - prefer two-column, grid, numbered stack, or diagram instead of flat bullets
- `detail`
  - one focused explanation with evidence, flow, or example
- `comparison`
  - use explicit left/right contrast, table, or `two-cols`
- `recommendation`
  - one decision headline + 2-4 actions
- `closing`
  - summary, takeaway, or next-step page; prefer `layout: end` or a strong centered finish

## AI Consumption Rules

- Plan the outline before writing markdown
- Treat `slide_role` as the contract and `content_shape` as the execution hint
- If deck length is 5 pages or more, include at least one non-bullet structural page
- Review the outline first, then review the full deck, then save

## Anti-Patterns

- all-bullet deck
- no closing slide
- consecutive repeated structures
- title says one thing, body acts like another
- cover slide that looks like ordinary body text

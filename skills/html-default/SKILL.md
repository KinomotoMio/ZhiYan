---
name: html-default
description: Default HTML generation skill. Use it when the same Agent needs to generate or revise Reveal-style HTML decks with explicit async render checkpoints.
version: 0.1.0
command: /html-default
default_for_output: html
allowed_tools: read_file,submit_html_deck
---

# HTML Default

## Purpose

Use the same Agent runtime as Slidev, but switch into an async-first HTML deck workflow.
The goal is a complete, renderable HTML presentation that preserves stable slide identity and supports later preview/export.

## Required Workflow

1. Plan the deck from sources and requested story.
2. Produce the full HTML deck with stable slide sections.
3. Keep each slide renderable and presentation-first.
4. Submit only when the whole deck is ready for rendering.

## Non-Negotiable Rules

- Return full HTML, not snippets.
- Preserve stable `data-slide-id` and `data-slide-title`.
- Keep section order unless the user explicitly asks to restructure.
- Optimize for correctness, renderability, and observability rather than “seconds-fast” output.
- Treat local `references/` files as the source of truth for render checkpoints and structure.

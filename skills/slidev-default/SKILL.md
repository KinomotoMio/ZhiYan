---
name: slidev-default
description: Default Slidev generation and editing skill. Use it to plan first, write valid Slidev markdown, apply local references, and submit a presentation-ready markdown deck.
version: 0.1.0
command: /slidev-default
default_for_output: slidev
allowed_tools: read_file,submit_slidev_deck
---

# Slidev Default

## Purpose

Use the same Agent for Slidev generation and Slidev editing, but force it into a markdown-first execution model.
The job is to produce a valid Slidev deck source, not to improvise arbitrary prose or HTML.

## Required Workflow

1. Plan the deck structure from the requested story and sources.
2. Choose one deck-level style direction.
3. Choose one layout recipe per slide.
4. Write the full markdown deck.
5. Validate the markdown structure before submitting.

## Non-Negotiable Rules

- Output must remain valid Slidev markdown.
- The first slide must merge global frontmatter and cover layout cleanly.
- Keep slide separators, frontmatter, and layout usage syntactically correct.
- Prefer presentation structures over article-like paragraphs.
- Keep visible variety; do not collapse the whole deck into weak bullet slides.
- Treat local `references/` files as the source of truth for formatting and workflow.

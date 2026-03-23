---
name: slidev-syntax
description: Slidev markdown syntax reference for frontmatter, slide separators, layouts, code blocks, and Mermaid diagrams.
version: 0.1.0
command: /slidev-syntax
---

# Slidev Syntax

## Purpose

Use this skill when you need authoritative Slidev markdown structure while generating deck source.

## Core Syntax

- Separate slides with `---`
- Put global frontmatter on the first slide inside `---` fences
- Use fenced code blocks for code samples
- Use fenced `mermaid` blocks for diagrams
- Use layout directives such as `layout: center` in slide frontmatter when needed

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

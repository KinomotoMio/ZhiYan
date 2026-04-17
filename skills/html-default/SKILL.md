---
name: html-default
description: Centi-deck author skill. The agent writes one ES module per slide exporting `render()` + optional `enter/leave` lifecycle hooks. Use `ctx.gsap` for animations. Submit the full deck with `submit_centi_deck_revision` (editor) or `submit_centi_deck` (generation).
version: 1.0.0
command: /html-default
default_for_output: html
allowed_tools: read_file,submit_centi_deck,submit_centi_deck_revision
---

# Centi-deck HTML Author

## Purpose

Author a presentation deck as a collection of ES modules — each slide is an ES module that exports a default object with a `render()` method returning an HTML string (inline `<style>`/CSS is allowed but no `<script>`/JS-in-markup). Optional `enter(el, ctx)` / `leave(el, ctx)` lifecycle hooks let you animate the slide using `ctx.gsap` when the slide becomes active / leaves view.

This replaces the older Reveal.js single-document HTML path. Animations must go through `ctx.gsap` so the runtime can clean them up across slide transitions.

## Mindset

Write slides, not webpage sections.

- Each page should have one obvious message and one obvious visual focal point.
- Prefer presentation density: concise headings, short support copy, clear grouping, strong negative space.
- `plainText` is a speaking/search summary, not the visual layout spec.
- Before drafting a slide, choose a recipe from `references/page-recipes/` and make sure the rendered page exhibits that recipe's structure signals.
- Read `references/render-rules.md` and `references/anti-patterns.md` before free-form experimentation.

## Required Workflow

1. Plan slide order and key messages from sources + outline.
2. Read the relevant recipe files under `references/page-recipes/` plus `references/render-rules.md`.
3. For each slide: pick one recipe, then write `render()` so the visible page clearly matches that recipe's hierarchy and pacing. You may use Tailwind classes, inline CSS, or CSS custom properties from the theme.
4. Derive a `plainText` summary that captures the slide's message in 1–3 sentences — speaker notes / TTS / search / visual scan all consume this.
5. Optionally add `enter(el, ctx)` animations — gsap `timeline`, `stagger`, `from`, `to`, `fromTo`, eases (`back`, `elastic`, `expo`), and premium plugins (`Flip`, `ScrollTrigger`, `SplitText`, `DrawSVGPlugin`, `MorphSVGPlugin`) are all available via `ctx.gsap`.
6. Submit **the whole deck** with `submit_centi_deck` (first-time generation) or `submit_centi_deck_revision` (editor revision).

## Module Contract (non-negotiable)

Each `moduleSource` must:
- Contain `export default { ... }`.
- Never use `import`, `require`, `fetch`, `XMLHttpRequest`, `eval`, `new Function`, `document.cookie`, `localStorage`, `sessionStorage`, `indexedDB`, `navigator.sendBeacon`, `WebSocket`, `Worker`, or `SharedWorker`.
- Never embed `<script>` or `<iframe>` in rendered HTML (they'll be stripped).
- Be ≤ 64 KB.
- Work with `"use strict"` prepended (the backend does this automatically; just don't rely on sloppy-mode features).

## Slide Payload Shape

```json
{
  "slideId": "cover",
  "title": "封面",
  "plainText": "第1页：产品名 + 一句话价值主张 + 作者",
  "notes": "演讲者备注（可选）",
  "moduleSource": "export default { id: 'cover', title: '封面', render() { return `<section class=\"cover\">...</section>`; }, enter(el, ctx) { ctx.gsap.timeline().from(el.querySelector('.title'), { opacity: 0, y: 20, duration: 0.6, ease: 'back.out(1.6)' }).from(el.querySelectorAll('.bullets li'), { opacity: 0, y: 10, stagger: 0.08 }, '<0.2'); } };"
}
```

## Deck Payload Shape

```json
{
  "title": "deck title",
  "theme": { "--brand": "#7c3aed", "--surface": "#0f172a" },
  "slides": [ { /* slide payload */ }, ... ],
  "summary": "生成摘要（可选）"
}
```

## Non-Negotiable Rules

- Submit the **full deck**, not incremental patches.
- Keep `slideId` stable across revisions when refining existing slides.
- `plainText` must be non-empty and describe what the slide says (not just the title).
- Prefer clear visual hierarchy (one primary heading, one or two support levels, short bullets).
- Every slide must visibly conform to a recipe or a deliberate variant of one. Do not improvise raw document sections without checking recipes first.
- Avoid long report paragraphs, weak title-only pages, and layouts that look like marketing webpages rather than single-message slides.
- If a slide is animated, the static `render()` output must already be legible before animation starts.
- Do not use `ctx.gsap.to(document, ...)` or try to break out of the slide's `el` container — cross-slide animation hurts the runtime's transition cleanup.
- Scope DOM reads/animations to `el`, `el.querySelector(...)`, or descendants of `el`; avoid global selectors like `'h1'`, `'p'`, or `document.querySelector(...)` inside lifecycle hooks.
- Do not try to network-load assets at render time; images must use public URLs embedded directly in the HTML.

## Animation Toolkit Available via `ctx.gsap`

- `ctx.gsap.timeline()` — chain multi-step animations with `.from()` / `.to()` / `.fromTo()`
- `ctx.gsap.from(targets, vars)` — entrance from an offset state
- `stagger` — array-driven entrance (`{ stagger: 0.08 }` or `{ stagger: { each: 0.05, from: 'center' } }`)
- `ease` — `back.out(1.6)`, `elastic.out(1, 0.3)`, `expo.out`, `power2.inOut`
- `ctx.gsap.set(target, { clearProps: 'all' })` — reset before a transition if needed
- Premium plugins: `Flip.from(state, { ... })` for layout transitions, `SplitText` for per-char/word animations, `DrawSVGPlugin` for SVG path draw-in, `MorphSVGPlugin` for shape morphs, `ScrollTrigger` if you need scroll-based reveals.

## Reference Files

- `references/render-rules.md`: deck-wide page density, hierarchy, and animation-scope rules.
- `references/anti-patterns.md`: concrete bad outcomes to avoid.
- `references/page-recipes/cover-hero.md`
- `references/page-recipes/agenda-cards.md`
- `references/page-recipes/section-break.md`
- `references/page-recipes/evidence-grid.md`
- `references/page-recipes/closing-takeaway.md`

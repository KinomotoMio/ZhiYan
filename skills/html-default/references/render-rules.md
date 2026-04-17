# Centi-deck Render Rules

## Core Rules

- One slide, one message. If the page tries to explain two unrelated ideas, split it.
- A viewer should identify the page's main point within 2 seconds.
- Favor large type, visible grouping, and deliberate whitespace over dense prose.
- The page must remain readable even if `enter()` never runs.

## Hierarchy Signals

- Include one dominant headline or statement block.
- Keep supporting copy short; prefer 1-3 short blocks, not report paragraphs.
- Use layout contrast: hero vs rail vs cards vs evidence blocks vs closing emphasis.
- Decorative surfaces should support the message, not compete with it.

## Density Rules

- Avoid more than one long paragraph on a slide.
- Prefer 3-5 agenda / evidence items per page; beyond that, split the page.
- If three consecutive slides share the same composition, vary the next one.

## Animation Rules

- Scope all animation targets to `el` or descendants of `el`.
- Prefer `el.querySelector(...)` or `el.querySelectorAll(...)` over global selectors.
- Do not rely on animation to reveal hidden essential content.
- Avoid cross-slide motion or selectors that can touch DOM outside the current slide.

# Slidev Native Layout Mapping Baseline

## Purpose

This candidate records which Zhiyan page semantics can already map cleanly to Slidev native layouts or native markdown structures, so future Slidev follow-up work reuses the same boundary.

## Control-Plane Rule

- Zhiyan taxonomy and `slide_role` remain the control plane.
- Slidev native layouts remain the rendering plane.
- We map intent to Slidev, but we do not replace Zhiyan taxonomy with Slidev layout names.

## Stable Mappings

| Zhiyan semantic | Preferred Slidev native mapping | Notes |
|---|---|---|
| `cover` | `layout: cover` or `layout: center` | Strong opening title + one positioning line |
| `comparison` | `layout: two-cols` or explicit markdown table | Best fit for left/right contrast |
| `closing` | `layout: end` or `layout: center` | Best fit for takeaway / next-step finish |
| `highlight` | `layout: quote` | Useful when one statement should dominate the page |
| `section-divider` | `layout: section` or `layout: center` | Works for stage transitions without body content |

## Native Structure First, Not Built-in Layout First

Some Zhiyan semantics do not yet have a stable one-to-one Slidev built-in layout. For those pages, reusing Slidev still means using its native structure language:

- `framework` -> Mermaid, table, grid, `div`-based structure
- `detail` -> callout, quote, focused split layout, grid
- `evidence` -> table, chart container, data-first split structure
- `process` -> Mermaid flow, timeline-like grid, numbered sequence

## Non-Goals

- Do not force `agenda` into a fake Slidev built-in layout.
- Do not migrate theme/runtime/export boundaries in the same step.
- Do not bypass review/validation just because a deck is more "native looking".

## Reuse Guidance

When adding a new Slidev mapping:

1. Keep Zhiyan semantics as the source of truth.
2. Prefer a native Slidev layout only when the fit is stable and legible.
3. Otherwise prefer native markdown structures over inventing pseudo-layout names.
4. Keep the mapping observable in artifact metadata and validation output.

# Centi-deck Render Contract

## Runtime

Each slide is instantiated by ZhiYan's centi-deck runtime (`frontend/src/lib/centi-deck/runtime.ts`, ported from `centi-deck/src/core/runtime.js`). The runtime:

1. Loads each `moduleSource` via `import(URL.createObjectURL(new Blob([source], { type: 'application/javascript' })))` (blob URL revoked immediately after module load).
2. Calls `render()` and injects the returned HTML into a `<section class="centi-deck-slide">` element.
3. When a slide becomes active, calls `enter(section, ctx)`.
4. When leaving, calls `leave(section, ctx)` then `gsap.killTweensOf` to reset animated props.

## Context Object (`ctx`) Fields

| Field | Type | Purpose |
|---|---|---|
| `slideId` | string | Stable id from your submission |
| `slideIndex` | number | 0-based position in the deck |
| `section` | HTMLElement | The live `<section>` wrapping your `render()` output |
| `gsap` | gsap object | Full gsap instance with Flip / SplitText / DrawSVGPlugin / MorphSVGPlugin / ScrollTrigger pre-registered |
| `goTo(index)` | fn | Programmatically navigate (e.g. auto-advance timer) |
| `registerCleanup(fn)` | fn | Pass a cleanup fn; called when the slide leaves |

## Safety / Sanitization

Backend's `normalize_centi_deck_submission` rejects modules containing:
- `import` / dynamic `import()` (except the runtime's blob URL import)
- `require` / `fetch` / `XMLHttpRequest`
- `eval` / `new Function`
- `document.cookie` / `localStorage` / `sessionStorage` / `indexedDB` / `navigator.sendBeacon`
- `WebSocket` / `Worker` / `SharedWorker`

Modules exceeding **64 KB** are rejected. Strict-mode preamble is prepended automatically.

## Anti-Patterns

- ❌ Hard-coding absolute positions — use flexbox/grid layouts so decks degrade gracefully.
- ❌ Animating across slide boundaries (e.g. a timeline that references `document` global) — the runtime resets animated props between slides.
- ❌ Relying on `requestAnimationFrame` / `setInterval` without `ctx.registerCleanup` — leaks timers.
- ❌ Expecting external CSS — inline your styles in the `render()` output or use Tailwind classes (available on the page).
- ❌ Loading fonts / images at runtime — keep assets referenced by public URL.

## Print / Presenter Modes

When the runtime mounts in `print` or `thumbnail` mode, `enter/leave` still fire but transitions are suppressed (CSS transition duration forced to 0). Authors should not rely on enter animations for content to become visible — the `render()` output must be legible without any animation having played.

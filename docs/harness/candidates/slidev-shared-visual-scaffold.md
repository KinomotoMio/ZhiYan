# Slidev Shared Visual Scaffold Before Custom Theme Engineering

## Situation

Issue `#232` sits after the page-brief/deck-chrome protocol work: the system can already name good deck structures, but generated slides still drift toward document-like output when those structures are only semantic hints. The next reliability layer is not a full custom theme package yet; it is a shared visual scaffold that makes semantic Slidev classes actually render like presentation components.

## Candidate Rule

- Keep the official Slidev theme baseline and inject one shared visual scaffold before considering a local custom theme.
- Treat semantic classes such as `slide-topline`, `metric-card`, `map-panel`, `compare-side`, and `action-step` as reusable presentation primitives, not as empty labels.
- Controller-owned baseline application should inject the same scaffold for short and long decks, so visual uplift is a mainline capability rather than a lucky prompt outcome.
- Review and validation should observe whether the shared scaffold is present and whether semantic primitives are actually being used, but visual weakness should remain a warning until the renderer baseline is stable.

## Why It Matters

Without a shared scaffold, the model keeps re-inventing page styling through ad-hoc utility classes or inline tweaks. That produces inconsistent output across deck lengths and topics:

- short decks may look acceptable by luck
- long decks drift faster toward markdown-document presentation
- semantic recipe classes exist in metadata but do not reliably change what the user sees

Adding one reusable visual layer raises the floor for every deck without forcing the system into theme-package maintenance too early.

## Reuse Guidance

When another generated deck system already has layout/block protocols but still feels document-like:

1. Add one shared visual scaffold before building a custom theme.
2. Make semantic classes render meaningfully across all deck sizes.
3. Inject the scaffold from the controller/baseline layer, not from per-slide prompt improvisation.
4. Track scaffold presence and primitive usage in validation telemetry so regressions stay visible.

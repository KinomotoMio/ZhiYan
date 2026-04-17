# HTML Render Contract

- Final output must be a full presentation deck.
- Every slide must live in a `<section>` with stable identity attributes.
- The deck should be suitable for async render, preview, and export stages.
- The agent should think in explicit stages: plan, write, render, validate, persist.
- Prefer clear progress milestones over opaque long-running rewrites.

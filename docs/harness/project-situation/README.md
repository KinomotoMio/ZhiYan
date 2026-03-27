# Slidev Project Situation

## Scope

This document records the current Slidev generation baseline on `main` after `#223`, `#224`, `#225`, and `#226` merged.

It is a project-situation snapshot, not a feature proposal. If future acceptance uncovers a real product gap, that gap should become a follow-up issue instead of being retroactively treated as already complete.

## Mainline Baseline

The current Slidev baseline on `main` now includes four layers that are meant to work together:

1. Controller-owned finalization from `#223`
2. Short/long deck stability work from `#224`
3. References-as-protocol execution from `#225`
4. Lightweight visual delivery baseline from `#226`

Those layers are now part of the same mainline fact set. Future Slidev acceptance should judge the system against this integrated baseline rather than against older experimental worktrees or pre-merge PR branches.

## Responsibility Boundaries

### Slidev renderer and runtime

- Uses Slidev as the render target for generated `slides.md`
- Keeps the official theme baseline centered on `seriph`
- Supports local preview/build through the generated artifact commands

### Controller and service layer

- Owns the final `review -> validate -> save` gate
- Unifies short-deck and long-deck finalization semantics
- Persists artifact metadata, retry/chunk/provider summaries, and composition normalization signals
- Provides the stable API/CLI contract used by local acceptance and smoke runs

### Agent loop

- Produces outline, references, draft markdown, and revisions
- Participates in long-deck planning and chunk generation
- Does not own the final save discipline by itself

### References layer

- Provides static `styles / layouts / blocks` assets under `skills/slidev-design-system/references/`
- Selects deck-level style/theme plus per-slide layout/block recipes
- Feeds the same selected references into generation, review, validation, and artifact metadata

### Review and validation layer

- Review focuses on structure plus presentation-oriented warnings such as `document_like_*`
- Validation keeps syntax legality and observable telemetry separate from subjective save gates
- Both layers now expose theme/reference fidelity as part of the mainline contract

## Mainline Capability Inventory

### Finalization and correctness

- Controller-owned final gate is on `main`
- Short-deck and long-deck both persist artifacts through the same controller finalization path
- Composition normalization remains as a safeguard, but the baseline now tracks normalization signals explicitly in artifact metadata

### Stability and diagnostics

- Long-deck planning/chunk assembly is in mainline, including retry of failed chunks only
- Provider/model-side failures are classified into machine-readable summaries rather than being flattened into one generic error
- Mainline artifacts now expose:
  - `quality.chunk_summary`
  - `quality.chunk_reports`
  - `quality.retry_summary`
  - `quality.provider_error_summary`
  - `agentic.long_deck_mode`

### References protocol

- Selected references are no longer only controller hints
- Mainline stores and returns:
  - `quality.selected_style`
  - `quality.selected_theme`
  - `quality.selected_layouts`
  - `quality.selected_blocks`
  - `quality.reference_fidelity_summary`
- Equivalent truth also lands in `state.document_metadata`

### Visual delivery baseline

- The default theme baseline stays on official `seriph`
- Deck-level scaffold and stronger recipe execution are now part of the generation contract
- Review and validation expose observable visual drift signals such as:
  - `document_like_cover`
  - `document_like_context`
  - `document_like_framework`
  - `document_like_comparison`
  - `document_like_closing`
  - `theme_recipe_weak`
  - `too_much_ad_hoc_inline_style`

## Mainline Truth Sources

When the team needs to answer "what is actually in Slidev mainline now?", use these sources in order:

1. `main` branch code and tests
2. This project-situation document
3. Merged PRs `#223` to `#226`

The following are not source-of-truth inputs for current acceptance:

- local experimental worktrees
- stale stacked branches that predate merge
- older demo conclusions captured before `#223` to `#226` landed on `main`

## Acceptance Baseline

The old local `design/slidev-mvp` sandbox has been retired. Treat the merged code, tests, and this document as the maintained baseline instead of any external design sandbox instructions.

## Mainline vs Experimental Boundary

The current expectation for the team is:

- Accept Slidev behavior based on what is merged into `main`
- Treat the candidate cards under `docs/harness/candidates/` as reusable reasoning inputs, not as the authoritative statement of shipped behavior
- Treat any missing feature discovered during mainline acceptance as a new follow-up instead of an implicit part of `#222`

## What #222 Does Not Claim

This consolidation does not claim that Slidev is "finished". It only claims that there is now one coherent mainline baseline for:

- controller finalization
- regular-range stability
- executable references
- lightweight visual delivery

Further work such as broader visual upgrades, deeper provider strategy, or larger orchestration redesign should be tracked as explicit follow-up issues.

The first consolidation pass also opened `#227` for build-smoke gaps that were discovered during mainline acceptance and intentionally left out of `#222`.

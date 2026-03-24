# Slidev References As Executable Protocol

## Situation

Issue `#220` follows `#218/#219`: once the controller owns finalization and the service has clearer stability semantics, the next problem is whether selected Slidev references actually shape generation. A design-system skill that only describes recipes in prose, or a controller that only stores reference metadata, does not create a reliable deck contract.

## Candidate Rule

- Keep the Slidev references layer in structured static assets: `styles`, `layouts`, and `blocks`.
- Select references from that asset layer once, then reuse the same selected style/layout/block payload across generation, review, validation, and artifact metadata.
- Treat selected references as an execution protocol, not as decorative hints.
- Keep skill prose as usage guidance; do not let `SKILL.md` become the only source of recipe truth.

## Why It Matters

If references are only recorded in metadata, the system can claim that it picked a style or layout recipe without the generated deck actually showing it. That makes quality telemetry misleading and weakens any later visual work.

Turning references into an executable protocol creates one reusable contract:

- selection comes from structured assets
- generation receives concrete layout/block requirements
- review compares the deck against the same selected recipes
- validation reports selected-vs-observed telemetry from the same source

## Reuse Guidance

For future skill-backed generation systems:

1. Put reusable design knowledge in versioned structured assets.
2. Load and select from those assets rather than hand-writing controller-side dicts.
3. Reuse the same selected payload in drafting, review, and validation.
4. Keep warnings and telemetry aligned to the selected protocol, even when fidelity is not yet a hard gate.

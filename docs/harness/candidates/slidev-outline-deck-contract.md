# Slidev Outline-to-Deck Contract

## Situation

Issue `#202` tightens the offline Slidev MVP so the harness is judged on whether it can faithfully turn a planned outline into a structured deck, not just whether it can emit syntactically valid markdown.

## Candidate Rule

- Root harness owns the workflow discipline: `outline -> outline review -> deck review -> syntax validation -> save`.
- Skill-layer contract review owns role fidelity: it decides whether `cover`, `framework`, `comparison`, and `closing` were actually honored.
- Syntax validation stays narrow: it blocks malformed Slidev markdown and reports static structure warnings, but it does not decide whether the deck fulfilled the outline contract.
- Save gates should block only on hard contract failures or stale reviews, not on taste or density warnings.

## Why It Matters

If role fidelity lives in the root prompt, the system becomes a fragile prompt garden. If it lives in syntax validation, legality and intent get mixed together. Keeping contract review in the skill layer preserves harness layering:

- root = control plane
- skill = domain rules
- validator = legality
- save gate = final enforcement

## Reuse Guidance

When a future harness capability needs stronger output guarantees, first ask:

1. Is this a workflow rule? Put it in the root harness or orchestration layer.
2. Is this a domain-specific contract? Put it in a review skill.
3. Is this just syntax or schema legality? Put it in validation.
4. Is this only quality guidance? Keep it as a warning unless product intent requires fail-closed behavior.

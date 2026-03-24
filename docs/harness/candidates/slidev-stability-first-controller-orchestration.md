# Slidev Stability-First Controller Orchestration

## Situation

Issue `#219` follows `#218`: once the controller owns the final `review -> validate -> save` gate, the next reliability problems are no longer about tool existence, but about whether short-deck and long-deck runs can recover from partial generation, malformed provider responses, and chunk-local failures without losing diagnostic clarity.

## Candidate Rule

- Keep one controller-owned finalization model for both short-deck and long-deck runs.
- Treat stability as stage management: planning, drafting, chunk generation, assembly, and finalization should each have explicit status and retry boundaries.
- Retry only at generation boundaries where the system can safely regenerate output; do not silently retry artifact persistence.
- Record provider failures and retry decisions as machine-readable metadata so the control plane can explain whether a failure came from provider output, chunk drafting, assembly, or finalization.

## Why It Matters

After final-gate ownership is moved into the controller, the next class of bugs is orchestration ambiguity. Without stage-aware retries and diagnostics, long decks look flaky even when the underlying issue is one malformed provider response or one bad chunk fragment.

Stability should therefore be expressed as:

- same finalization contract across short and long runs
- explicit retry boundaries
- clear failure attribution
- telemetry that survives retries

## Reuse Guidance

For future artifact-producing agentic flows:

1. Define the stable stages the controller expects to observe.
2. Retry only the stage that can be safely replayed.
3. Preserve structured retry and provider-failure metadata across attempts.
4. Let final failure reasons report the last unresolved stage gap, not an earlier transient error.

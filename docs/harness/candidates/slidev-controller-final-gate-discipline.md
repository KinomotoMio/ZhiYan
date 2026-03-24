# Slidev Controller-Owned Final Gate Discipline

## Situation

Issue `#218` closes a reliability gap in the Slidev MVP: the system already had `review -> validate -> save` tools, but the final sequence still depended too much on whether the model remembered to call them in the right order.

## Candidate Rule

- Agent loops are good at planning, drafting, and revising markdown.
- Controller/service code must own the final `review -> validate -> save` sequence for artifact-producing generation.
- The controller should finalize against one concrete markdown payload plus the current outline/reference state, instead of trusting the model's last tool-calling attempt.
- Early or failed save attempts must not become the long-term diagnosis if controller finalization later succeeds or fails for a different reason.

## Why It Matters

Prompt discipline is not the same as orchestration discipline. Once generation has a real final gate, the control plane should guarantee that gate for both short and long runs.

This keeps responsibilities clean:

- agent loop = plan / draft / repair
- controller = sequencing and final enforcement
- review skill = contract fidelity
- validator = syntax legality
- save gate = artifact persistence

## Reuse Guidance

When a future agentic workflow must produce a final artifact:

1. Let the model create or revise the candidate output.
2. Store enough state for the controller to pick up finalization deterministically.
3. Re-run the official final checks from the controller on the exact output being persisted.
4. Report the finalization failure reason from the controller-owned gate, not from an earlier failed save attempt.

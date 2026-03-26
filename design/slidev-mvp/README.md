# Slidev MVP Mainline Baseline

## Purpose

This document is the maintenance and acceptance guide for the Slidev MVP path that is now on `main`.

It describes the shipped baseline after `#223`, `#224`, `#225`, and `#226` merged. It is intentionally operational: use it to answer what is in the mainline path, how to smoke it, what fields to inspect, and how to bucket failures during acceptance.

## What Is In Mainline Now

### 1. Controller-owned finalization

- The agent loop no longer acts as the sole owner of final save discipline.
- The service/controller owns the final `review -> validate -> save` sequence for the exact markdown that becomes the artifact.
- Short-deck and long-deck both converge on the same finalization semantics.

### 2. Regular-range stability

- Short-deck and long-deck share the same finalization model.
- Long-deck generation includes chunk planning, chunk reports, and bounded retry behavior.
- Provider/model-side failures are classified for diagnostics instead of collapsing into one generic reason.

### 3. Executable references

- Slidev references now live as static assets in `skills/slidev-design-system/references/`.
- The system selects:
  - one deck-level style/theme baseline
  - one layout recipe per slide
  - one or two block recipes per slide
- The same selected references are consumed by generation, review, validation, and artifact metadata.

### 4. Lightweight visual delivery baseline

- Official `seriph` remains the theme baseline.
- Deck-level scaffold, page classes, and stronger role recipes are part of the generation contract.
- Review and validation expose visual drift warnings and telemetry without turning taste into a hard save gate.

## Stable Output Surfaces To Inspect

### API/CLI payload

The `slidev-mvp` response should be inspected for:

- `artifact_dir`
- `slides_path`
- `dev_command`
- `build_command`
- `validation`
- `quality`
- `agentic`

### High-signal `quality` fields

These fields are the primary mainline acceptance surface:

- `quality.selected_style`
- `quality.selected_theme`
- `quality.theme_reason`
- `quality.selected_layouts`
- `quality.selected_blocks`
- `quality.reference_fidelity_summary`
- `quality.theme_fidelity_summary`
- `quality.chunk_summary`
- `quality.chunk_reports`
- `quality.retry_summary`
- `quality.provider_error_summary`
- `quality.composition_normalization`

### High-signal document metadata

The generated artifact state should carry corresponding metadata such as:

- `slidev_long_deck_mode`
- `slidev_selected_style`
- `slidev_selected_theme`
- `slidev_theme_reason`
- `slidev_selected_layouts`
- `slidev_selected_blocks`
- `slidev_reference_fidelity`
- `slidev_theme_fidelity`
- `slidev_chunk_summary`
- `slidev_retry_summary`
- `slidev_provider_error_summary`

## Smoke Prerequisites

### Backend server

Start the backend locally from `/Users/qizhi_dong/Projects/Zhiyan-mainline/backend`:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Slidev runtime sandbox

The build path uses the local Slidev sandbox under `/Users/qizhi_dong/Projects/Zhiyan-mainline/design/slidev-mvp`.

The first `--build` run may install dependencies through `pnpm install`.

## Canonical Smoke Commands

### Short-deck smoke

Use this fixed 5-page smoke:

```bash
cd /Users/qizhi_dong/Projects/Zhiyan-mainline/backend
uv run zhiyan-cli --base-url http://127.0.0.1:8000 --timeout 600 slidev-mvp \
  --topic "团队 AI 知识助手价值" \
  --content "准备一个关于团队 AI 知识助手价值的5页演示文稿" \
  --num-pages 5 \
  --build
```

### Long-deck smoke

Use this fixed 12-page smoke:

```bash
cd /Users/qizhi_dong/Projects/Zhiyan-mainline/backend
uv run zhiyan-cli --base-url http://127.0.0.1:8000 --timeout 600 slidev-mvp \
  --topic "人工智能对未来工作影响" \
  --content "准备一个关于人工智能对未来工作影响的12页演示文稿" \
  --num-pages 12 \
  --build
```

## Build and Preview Interpretation

Each successful smoke returns:

- a generated `slides.md`
- `dev_command` for local preview
- `build_command` for local build replay

Minimum acceptance for a successful smoke:

1. generation returns a payload instead of an API failure
2. artifact is written to disk
3. `validation.ok` is true
4. review/validate signals are present in `quality`
5. `--build` completes successfully
6. the generated deck is locally previewable with `dev_command`

## Visual Acceptance Baseline

The visual baseline is intentionally light, but mainline acceptance should still confirm:

- the result reads like a Slidev deck rather than a plain markdown report
- the cover has a real cover feel
- comparison slides show visible contrast instead of reading like body prose
- closing slides have a clear closing/takeaway feel
- context/framework slides do not collapse into generic section pages

Visual weakness is expected to surface as warnings and telemetry, not as an automatic save failure.

## Failure Attribution Buckets

Use these buckets during acceptance:

### Mainline logic failure

Use this when:

- controller finalization is skipped or inconsistent
- references/metadata are missing unexpectedly
- chunk assembly or retry behavior contradicts the mainline contract
- `slidev build` fails because the generated artifact is structurally wrong

### External provider noise

Use this when:

- the upstream model returns malformed, empty, or incomplete output
- the local code path looks correct but the provider response interrupts the smoke
- retry summaries and provider error summaries point to model boundary instability

### Local environment or render dependency issue

Use this when:

- the backend server is not running
- required credentials are missing
- local `pnpm`/Node/Slidev runtime setup is broken
- the build fails because the local environment cannot run the declared command

## Mainline vs Experimental Rule

When smoke results disagree with older experiments, trust:

1. the merged `main` code
2. this README
3. `/Users/qizhi_dong/Projects/Zhiyan-mainline/docs/harness/project-situation/README.md`

Do not use older worktrees or pre-merge stacked branch output as the arbiter of current Slidev behavior.

## Follow-up Rule

If a smoke reveals a real gap that is not already represented in the mainline baseline:

- document the exact failure
- classify it using the buckets above
- open or link a follow-up issue

Do not expand the consolidation baseline in-place with a new feature implementation.

## Initial Consolidation Evidence (2026-03-25)

The first `#222` consolidation pass was executed from clean `main` after `#223` to `#226` merged.

### Automated evidence

```bash
cd /Users/qizhi_dong/Projects/Zhiyan-mainline/backend
uv run --group dev python -m pytest -q tests/test_generation_slidev_mvp.py
```

Result:

- `53 passed in 4.22s`

### Short-deck smoke evidence

Command:

```bash
cd /Users/qizhi_dong/Projects/Zhiyan-mainline/backend
uv run zhiyan-cli --base-url http://127.0.0.1:8000 --timeout 600 slidev-mvp \
  --topic "团队 AI 知识助手价值" \
  --content "准备一个关于团队 AI 知识助手价值的5页演示文稿" \
  --num-pages 5 \
  --build
```

Observed result:

- generation reached artifact persistence and wrote `/Users/qizhi_dong/Projects/Zhiyan-mainline/data/slidev-mvp/deck-b6fa1c12a06d/slides.md`
- build failed with `YAMLParseError`
- failure bucket: `mainline logic failure`

Current concrete symptom:

- `/Users/qizhi_dong/Projects/Zhiyan-mainline/data/slidev-mvp/deck-b6fa1c12a06d/slides.md` contains duplicated `themeConfig` serialization in the opening frontmatter, which breaks `slidev build`

### Long-deck smoke evidence

Command:

```bash
cd /Users/qizhi_dong/Projects/Zhiyan-mainline/backend
uv run zhiyan-cli --base-url http://127.0.0.1:8000 --timeout 600 slidev-mvp \
  --topic "人工智能对未来工作影响" \
  --content "准备一个关于人工智能对未来工作影响的12页演示文稿" \
  --num-pages 12
```

Observed result:

- command returned `200 OK`
- artifact persisted at `/Users/qizhi_dong/Projects/Zhiyan-mainline/data/slidev-mvp/deck-3a729ed2dfa4`
- `validation.ok == true`
- `quality.chunk_summary.completed_chunks == 4`
- `agentic.long_deck_mode == true`

### Build smoke evidence

Command:

```bash
cd /Users/qizhi_dong/Projects/Zhiyan-mainline/data/slidev-mvp/deck-3a729ed2dfa4
./node_modules/.bin/slidev build slides.md --out dist-manual
```

Observed result:

- build failed with `The theme "@slidev/theme-seriph" was not found and cannot prompt for installation`
- failure bucket: `mainline logic failure`

Interpretation:

- the long-deck artifact is structurally generated and saved correctly enough for controller/review/validate acceptance
- the current build/runtime baseline on `main` still has at least one follow-up gap around theme/runtime availability
- those gaps should be fixed in follow-up work, not by scope-creeping the `#222` consolidation PR
- tracked follow-up: `#227`

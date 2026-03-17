"""Engine implementations for generation routing.

Phase 1 only provides the internal engine wrapper that preserves current behavior.
External engines will be added in later phases behind the router.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.pipeline.graph import PipelineState
from app.services.pipeline import graph as graph_mod


@dataclass(frozen=True)
class InternalV2Engine:
    engine_id: str = "internal_v2"

    async def parse(self, state: PipelineState, *, progress=None) -> None:
        await graph_mod.stage_parse_document(state, progress=progress)

    async def outline(self, state: PipelineState, *, progress=None) -> None:
        await graph_mod.stage_generate_outline(state, progress=progress)

    async def layout(self, state: PipelineState, *, progress=None) -> None:
        await graph_mod.stage_select_layouts(state, progress=progress)

    async def slides(self, state: PipelineState, *, per_slide_timeout: float, progress=None, on_slide=None) -> None:
        await graph_mod.stage_generate_slides(
            state,
            per_slide_timeout=per_slide_timeout,
            progress=progress,
            on_slide=on_slide,
        )

    async def assets(self, state: PipelineState, *, progress=None) -> None:
        await graph_mod.stage_resolve_assets(state, progress=progress)

    async def verify(self, state: PipelineState, *, progress=None, enable_vision: bool = True) -> None:
        await graph_mod.stage_verify_slides(state, progress=progress, enable_vision=enable_vision)

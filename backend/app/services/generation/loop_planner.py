"""Planner for selecting the next generation tool in the harness loop."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from app.core.config import settings
from app.core.model_resolver import resolve_model
from app.models.generation import StageStatus
from app.services.generation.tool_registry import GenerationToolRegistry
from app.services.harness import compose_planner_instructions, load_generation_harness_config
from app.services.pipeline.graph import PipelineState

logger = logging.getLogger(__name__)


class LoopPlannerDecision(BaseModel):
    action: Literal["call_tool", "complete"] = "complete"
    tool_name: str | None = None
    reasoning: str = ""


@dataclass(frozen=True)
class LoopHistoryItem:
    tool_name: str
    stage: StageStatus
    outcome: str = "completed"


class GenerationLoopPlanner:
    def __init__(self):
        self._agent = None

    def max_iterations(self) -> int:
        return load_generation_harness_config().planner.max_iterations

    async def decide(
        self,
        *,
        state: PipelineState,
        registry: GenerationToolRegistry,
        history: list[LoopHistoryItem],
        forced_stage: StageStatus | None = None,
    ) -> LoopPlannerDecision:
        if forced_stage is not None:
            for tool in registry.list_tools():
                if tool.stage == forced_stage:
                    return LoopPlannerDecision(
                        action="call_tool",
                        tool_name=tool.name,
                        reasoning=f"forced start stage: {forced_stage.value}",
                    )

        config = load_generation_harness_config()
        if config.planner.mode != "llm":
            return self._deterministic_decide(state=state, registry=registry, history=history)

        try:
            return await self._llm_decide(state=state, registry=registry, history=history)
        except Exception as exc:
            logger.warning("planner_llm_failed_fallback_to_deterministic: %s", exc)
            return self._deterministic_decide(state=state, registry=registry, history=history)

    async def _llm_decide(
        self,
        *,
        state: PipelineState,
        registry: GenerationToolRegistry,
        history: list[LoopHistoryItem],
    ) -> LoopPlannerDecision:
        from pydantic_ai import Agent

        if self._agent is None:
            self._agent = Agent(
                model=resolve_model(settings.strong_model),
                output_type=LoopPlannerDecision,
                instructions=compose_planner_instructions(),
                retries=1,
            )

        prompt = self._build_prompt(state=state, registry=registry, history=history)
        result = await self._agent.run(prompt)
        decision = result.output
        if decision.action == "call_tool" and decision.tool_name not in registry.names():
            raise ValueError(f"unknown tool chosen by planner: {decision.tool_name}")
        return decision

    def _deterministic_decide(
        self,
        *,
        state: PipelineState,
        registry: GenerationToolRegistry,
        history: list[LoopHistoryItem],
    ) -> LoopPlannerDecision:
        completed = {item.tool_name for item in history if item.outcome in {"completed", "skipped"}}

        if "parse_document" not in completed and not state.document_metadata.get("char_count"):
            return LoopPlannerDecision(action="call_tool", tool_name="parse_document", reasoning="document not parsed")
        if "generate_outline" not in completed and not state.outline.get("items"):
            return LoopPlannerDecision(action="call_tool", tool_name="generate_outline", reasoning="outline missing")
        if "select_layouts" not in completed and not state.layout_selections:
            return LoopPlannerDecision(action="call_tool", tool_name="select_layouts", reasoning="layouts missing")
        if "generate_slides" not in completed and not state.slide_contents:
            return LoopPlannerDecision(action="call_tool", tool_name="generate_slides", reasoning="slide contents missing")
        if "resolve_assets" not in completed and not state.slides:
            return LoopPlannerDecision(action="call_tool", tool_name="resolve_assets", reasoning="slides not materialized")
        if "verify_slides" not in completed:
            return LoopPlannerDecision(action="call_tool", tool_name="verify_slides", reasoning="verification not run")
        return LoopPlannerDecision(action="complete", reasoning="all required tools completed")

    @staticmethod
    def _build_prompt(
        *,
        state: PipelineState,
        registry: GenerationToolRegistry,
        history: list[LoopHistoryItem],
    ) -> str:
        available_tools = [
            {
                "name": tool.name,
                "stage": tool.stage.value,
                "description": tool.description,
            }
            for tool in registry.list_tools()
        ]
        state_summary = {
            "document_parsed": bool(state.document_metadata),
            "outline_items": len(state.outline.get("items", [])),
            "layout_count": len(state.layout_selections),
            "slide_content_count": len(state.slide_contents),
            "slide_count": len(state.slides),
            "verification_issue_count": len(state.verification_issues),
            "failed_slide_indices": list(state.failed_slide_indices),
        }
        history_summary = [
            {
                "tool_name": item.tool_name,
                "stage": item.stage.value,
                "outcome": item.outcome,
            }
            for item in history
        ]
        return (
            "你正在为知演生成任务选择下一步工具。\n\n"
            f"state_summary={json.dumps(state_summary, ensure_ascii=False)}\n"
            f"history={json.dumps(history_summary, ensure_ascii=False)}\n"
            f"available_tools={json.dumps(available_tools, ensure_ascii=False)}\n\n"
            "如果任务还没完成，请输出 action=call_tool 和一个合法 tool_name；"
            "如果已经具备完成条件，请输出 action=complete。"
        )

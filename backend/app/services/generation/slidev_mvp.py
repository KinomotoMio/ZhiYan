"""Offline Slidev MVP orchestration for issue #178.

This service proves the existing harness can drive a mature external
presentation runtime without touching the current generation-job/UI pipeline.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha1
from functools import lru_cache
import json
from pathlib import Path
import re
import shlex
import subprocess
from typing import Any
from uuid import uuid4

from pydantic_ai.exceptions import UnexpectedModelBehavior

from app.core.config import settings
from app.services.document.parser import estimate_tokens, extract_structure_signals
from app.services.generation.agentic import (
    AgenticLoopResult,
    SubagentSpec,
    ToolDef,
    ToolExecutionResult,
    ToolRegistry,
    agentic_loop,
    build_dispatch_subagent_tool,
    build_load_skill_tool,
    build_run_skill_tool,
    build_skill_summaries,
    build_update_todo_tool,
    dispatch_tool_calls,
    filter_registry,
    run_parallel_subagents,
    summarize_state,
)
from app.services.generation.agentic.provider_failures import is_malformed_provider_response
from app.services.generation.agentic.todo import TodoManager
from app.services.generation.agentic.types import AgenticModelClient
from app.services.pipeline.graph import PipelineState
from app.services.sessions import session_store
from app.services.skill_runtime.executor import SkillExecutionError, execute_skill
from app.services.skill_runtime.registry import SkillRegistry

SLIDEV_ARTIFACT_ROOT = settings.project_root / "data" / "slidev-mvp"
SLIDEV_SANDBOX_DIR = settings.project_root / "design" / "slidev-mvp"
SLIDEV_SLIDES_FILENAME = "slides.md"
LONG_DECK_TRIGGER_PAGES = 12
LONG_DECK_CHUNK_SIZE = 3
SHORT_DECK_GENERATION_RETRY_LIMIT = 2
LONG_DECK_PLANNING_MAX_TURNS = 16
LONG_DECK_PLANNING_RETRY_LIMIT = 2
LONG_DECK_CHUNK_MAX_TURNS = 10
LONG_DECK_CHUNK_RETRY_LIMIT = 2
SLIDEV_SHARED_VISUAL_SCAFFOLD_MARKER = "slidev-shared-visual-scaffold"
SLIDEV_SUPPORTED_LAYOUTS = (
    "404",
    "center",
    "cover",
    "default",
    "end",
    "error",
    "fact",
    "full",
    "iframe",
    "iframe-left",
    "iframe-right",
    "image",
    "image-left",
    "image-right",
    "intro",
    "none",
    "quote",
    "section",
    "statement",
    "two-cols",
    "two-cols-header",
)
LONG_DECK_PLANNING_TOOLS = (
    "update_todo",
    "load_skill",
    "set_slidev_outline",
    "review_slidev_outline",
    "select_slidev_references",
)
SLIDEV_OUTLINE_ROLES = (
    "cover",
    "context",
    "framework",
    "detail",
    "comparison",
    "recommendation",
    "closing",
)
SLIDEV_NATIVE_PATTERN_GUIDE: dict[str, dict[str, Any]] = {
    "cover": {
        "preferred_layouts": ["cover", "center"],
        "preferred_patterns": ["hero-title", "short-positioning-line"],
        "visual_recipe": {
            "name": "cover-hero",
            "preferred_classes": ["deck-cover"],
            "required_signals": ["hero-title", "short-subtitle"],
            "description": "Hero 标题 + 短副标题 + 稀疏信息密度。",
        },
        "reason": "封面优先使用 Slidev 原生开场布局，突出标题与定位。",
    },
    "context": {
        "preferred_layouts": [],
        "preferred_patterns": ["callout", "quote", "compact-bullets"],
        "visual_recipe": {
            "name": "context-brief",
            "preferred_classes": ["deck-context"],
            "required_signals": ["compact-bullets", "quote-or-callout"],
            "description": "短背景引导 + quote/callout 或紧凑 bullets。",
        },
        "reason": "背景页更适合轻量结构提示，而不是重布局。",
    },
    "framework": {
        "preferred_layouts": [],
        "preferred_patterns": ["mermaid", "table", "grid", "div-grid"],
        "visual_recipe": {
            "name": "framework-visual",
            "preferred_classes": ["deck-framework"],
            "required_signals": ["visual-structure", "model-takeaway"],
            "description": "图表/网格承载模型，上方标题区，下方一句 takeaway。",
        },
        "reason": "框架页优先使用图、表、网格等原生结构语言承载模型。",
    },
    "detail": {
        "preferred_layouts": [],
        "preferred_patterns": ["callout", "quote", "div-grid", "mermaid"],
        "visual_recipe": {
            "name": "detail-focus",
            "preferred_classes": ["deck-detail"],
            "required_signals": ["focus-block"],
            "description": "单重点信息块 + 一条解释，不做平铺 bullets。",
        },
        "reason": "细节页应使用可聚焦的原生结构，而不是纯平铺 bullets。",
    },
    "comparison": {
        "preferred_layouts": ["two-cols"],
        "preferred_patterns": ["two-cols", "table", "before-after"],
        "visual_recipe": {
            "name": "comparison-split",
            "preferred_classes": ["deck-comparison"],
            "required_signals": ["split-compare", "contrast-labels"],
            "description": "双栏/表格强对照，左右两侧有明确标签与结论。",
        },
        "reason": "对比页优先使用 Slidev 双栏或表格结构建立左右对照。",
    },
    "recommendation": {
        "preferred_layouts": [],
        "preferred_patterns": ["decision-headline", "action-list", "callout"],
        "visual_recipe": {
            "name": "recommendation-actions",
            "preferred_classes": ["deck-recommendation"],
            "required_signals": ["decision-headline", "action-list"],
            "description": "一个决策 headline + 2-4 个动作项。",
        },
        "reason": "建议页优先使用决策 headline + 行动列表的原生结构表达。",
    },
    "closing": {
        "preferred_layouts": ["end", "center"],
        "preferred_patterns": ["takeaway", "next-step", "closing-hero"],
        "visual_recipe": {
            "name": "closing-takeaway",
            "preferred_classes": ["deck-closing"],
            "required_signals": ["closing-line", "next-step-or-takeaway"],
            "description": "收束 headline + takeaway / next steps + 结尾句。",
        },
        "reason": "收尾页优先使用 Slidev 原生结束布局或强收束结构。",
    },
}
_SUBAGENT_DEFAULT_TOOLS = ("load_skill", "run_skill")
_SUBAGENT_FORBIDDEN_TOOLS = {
    "dispatch_subagent",
    "review_slidev_outline",
    "review_slidev_deck",
    "validate_slidev_deck",
    "save_slidev_artifact",
}

ShellRunner = Callable[[Sequence[str], Path], Awaitable[subprocess.CompletedProcess[str]]]


class SlidevMvpError(RuntimeError):
    """Base error for Slidev MVP generation."""


class SlidevMvpNotFoundError(SlidevMvpError):
    """Raised when a referenced session or source cannot be found."""


class SlidevMvpValidationError(SlidevMvpError):
    """Raised when the request or generated deck is invalid."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str | None = None,
        next_action: str | None = None,
    ) -> None:
        self.message = message
        self.reason_code = reason_code
        self.next_action = next_action
        details = [message]
        if reason_code:
            details.append(f"reason={reason_code}")
        if next_action:
            details.append(f"next={next_action}")
        super().__init__(" | ".join(details))


class SlidevMvpProviderError(SlidevMvpError):
    """Raised when the upstream model/provider fails in a classified way."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        next_action: str | None = None,
    ) -> None:
        self.message = message
        self.reason_code = reason_code
        self.next_action = next_action
        details = [message, f"reason={reason_code}"]
        if next_action:
            details.append(f"next={next_action}")
        super().__init__(" | ".join(details))


class SlidevMvpBuildError(SlidevMvpError):
    """Raised when the local Slidev build command fails."""


@dataclass(slots=True)
class SlidevMvpArtifacts:
    deck_id: str
    title: str
    markdown: str
    artifact_dir: Path
    slides_path: Path
    build_output_dir: Path | None
    dev_command: str
    build_command: str
    validation: dict[str, Any]
    quality: dict[str, Any]
    agentic: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "deck_id": self.deck_id,
            "title": self.title,
            "markdown": self.markdown,
            "artifact_dir": str(self.artifact_dir),
            "slides_path": str(self.slides_path),
            "build_output_dir": str(self.build_output_dir) if self.build_output_dir else None,
            "dev_command": self.dev_command,
            "build_command": self.build_command,
            "validation": self.validation,
            "quality": self.quality,
            "agentic": self.agentic,
        }


@dataclass(slots=True)
class _ResolvedInputs:
    topic: str
    material: str
    num_pages: int
    title_hint: str
    source_hints: dict[str, Any]


@dataclass(slots=True)
class _RuntimeContext:
    deck_id: str
    artifact_dir: Path
    slides_path: Path
    requested_pages: int
    loaded_skills: set[str] = field(default_factory=set)
    used_subagent: bool = False
    outline_review: dict[str, Any] | None = None
    outline_review_hash: str | None = None
    deck_review: dict[str, Any] | None = None
    deck_review_hash: str | None = None
    validation: dict[str, Any] | None = None
    validation_hash: str | None = None
    reference_selection: dict[str, Any] | None = None
    reference_selection_hash: str | None = None
    pattern_hints: list[dict[str, Any]] = field(default_factory=list)
    latest_markdown: str = ""
    long_deck_mode: bool = False
    chunk_plan: list[dict[str, Any]] = field(default_factory=list)
    chunk_reports: list[dict[str, Any]] = field(default_factory=list)
    stage_history: list[dict[str, Any]] = field(default_factory=list)
    retry_events: list[dict[str, Any]] = field(default_factory=list)
    provider_errors: list[dict[str, Any]] = field(default_factory=list)
    save_failure: SlidevMvpValidationError | None = None
    saved_artifact: SlidevMvpArtifacts | None = None


@dataclass(slots=True)
class _ChunkSpec:
    chunk_id: str
    outline_items: list[dict[str, Any]]
    selected_layouts: list[dict[str, Any]]
    selected_blocks: list[dict[str, Any]]
    page_briefs: list[dict[str, Any]]

    @property
    def slide_numbers(self) -> list[int]:
        return [int(item.get("slide_number") or 0) for item in self.outline_items if isinstance(item, Mapping)]


@dataclass(slots=True)
class _ChunkExecution:
    spec: _ChunkSpec
    fragment_markdown: str
    review: dict[str, Any]
    validation: dict[str, Any]
    attempts: int
    normalization_report: dict[str, Any] = field(default_factory=dict)


class SlidevMvpService:
    """Run one offline Slidev MVP generation loop."""

    def __init__(
        self,
        *,
        workspace_id: str,
        skill_registry: SkillRegistry | None = None,
        artifact_root: Path | None = None,
        sandbox_dir: Path | None = None,
        harness_path: Path | None = None,
        shell_runner: ShellRunner | None = None,
        model: AgenticModelClient | None = None,
    ) -> None:
        self.workspace_id = workspace_id
        self.skill_registry = skill_registry or SkillRegistry()
        self.artifact_root = artifact_root or SLIDEV_ARTIFACT_ROOT
        self.sandbox_dir = sandbox_dir or SLIDEV_SANDBOX_DIR
        self.harness_path = harness_path or (settings.project_root / "harness.yaml")
        self.shell_runner = shell_runner or _default_shell_runner
        self.model = model
        self.last_loop_result: AgenticLoopResult | None = None
        self.last_state: PipelineState | None = None

    async def generate_deck(
        self,
        *,
        topic: str = "",
        content: str = "",
        session_id: str | None = None,
        source_ids: Sequence[str] | None = None,
        num_pages: int = 5,
        build: bool = False,
    ) -> SlidevMvpArtifacts:
        normalized_source_ids = [str(source_id).strip() for source_id in (source_ids or []) if str(source_id).strip()]
        resolved = await self._resolve_inputs(
            topic=topic,
            content=content,
            session_id=session_id,
            source_ids=normalized_source_ids,
            num_pages=num_pages,
        )

        todo_manager = TodoManager()
        state = PipelineState(
            raw_content=resolved.material,
            source_ids=normalized_source_ids,
            topic=resolved.topic,
            num_pages=resolved.num_pages,
            job_id=f"slidev-{uuid4().hex[:8]}",
        )
        state.document_metadata.update(
            {
                "title": resolved.title_hint,
                "estimated_tokens": estimate_tokens(resolved.material),
                "structure_signals": extract_structure_signals(resolved.material),
                "source_hints": resolved.source_hints,
                "generation_mode": "slidev-mvp",
            }
        )
        self.last_state = state

        deck_id = f"deck-{uuid4().hex[:12]}"
        artifact_dir = self.artifact_root / deck_id
        slides_path = artifact_dir / SLIDEV_SLIDES_FILENAME
        runtime = _RuntimeContext(
            deck_id=deck_id,
            artifact_dir=artifact_dir,
            slides_path=slides_path,
            requested_pages=resolved.num_pages,
        )
        self._record_stage(state=state, runtime=runtime, stage="inputs_ready", status="ok")
        registry = self._build_registry(state=state, runtime=runtime, todo_manager=todo_manager)

        if self._should_use_long_deck_mode(resolved.num_pages):
            loop_result = await self._run_long_deck_generation(
                resolved=resolved,
                state=state,
                runtime=runtime,
                todo_manager=todo_manager,
                registry=registry,
            )
        else:
            loop_result = await self._run_short_deck_generation(
                resolved=resolved,
                state=state,
                runtime=runtime,
                todo_manager=todo_manager,
                registry=registry,
            )
        self.last_loop_result = loop_result

        artifact = runtime.saved_artifact
        if artifact is None:
            raise _missing_artifact_error(runtime)
        agentic_summary = {
            "turns": loop_result.turns,
            "stop_reason": loop_result.stop_reason,
            "max_turns_reached": loop_result.max_turns_reached,
            "used_subagent": runtime.used_subagent,
            "loaded_skills": sorted(runtime.loaded_skills),
            "long_deck_mode": runtime.long_deck_mode,
            "stage_history": list(runtime.stage_history),
            "retry_summary": _build_retry_summary(runtime.retry_events),
            "provider_error_summary": _build_provider_error_summary(runtime.provider_errors),
            "final_state_summary": summarize_state(state),
        }
        artifact = SlidevMvpArtifacts(
            deck_id=artifact.deck_id,
            title=artifact.title,
            markdown=artifact.markdown,
            artifact_dir=artifact.artifact_dir,
            slides_path=artifact.slides_path,
            build_output_dir=artifact.build_output_dir,
            dev_command=artifact.dev_command,
            build_command=artifact.build_command,
            validation=artifact.validation,
            quality=artifact.quality,
            agentic=agentic_summary,
        )

        if build:
            build_output_dir = artifact.artifact_dir / "dist"
            await self._run_slidev_build(slides_path=artifact.slides_path, output_dir=build_output_dir)
            artifact = SlidevMvpArtifacts(
                deck_id=artifact.deck_id,
                title=artifact.title,
                markdown=artifact.markdown,
                artifact_dir=artifact.artifact_dir,
                slides_path=artifact.slides_path,
                build_output_dir=build_output_dir,
                dev_command=artifact.dev_command,
                build_command=self._build_command(artifact.slides_path, build_output_dir),
                validation=artifact.validation,
                quality=artifact.quality,
                agentic=artifact.agentic,
            )

        return artifact

    async def _resolve_inputs(
        self,
        *,
        topic: str,
        content: str,
        session_id: str | None,
        source_ids: Sequence[str],
        num_pages: int,
    ) -> _ResolvedInputs:
        await session_store.ensure_workspace(self.workspace_id)
        if session_id:
            try:
                await session_store.get_session(self.workspace_id, session_id)
            except ValueError as exc:
                raise SlidevMvpNotFoundError(str(exc)) from exc

        source_metas: list[dict[str, Any]] = []
        source_content = ""
        if source_ids:
            source_metas = await session_store.get_workspace_sources_by_ids(self.workspace_id, list(source_ids))
            if len(source_metas) != len(source_ids):
                found_ids = {str(meta.get("id")) for meta in source_metas}
                missing_ids = [source_id for source_id in source_ids if source_id not in found_ids]
                raise SlidevMvpNotFoundError(f"素材不存在: {', '.join(missing_ids)}")
            source_content = await session_store.get_combined_source_content(
                self.workspace_id,
                session_id or "",
                list(source_ids),
            )

        normalized_topic = str(topic or "").strip()
        normalized_content = str(content or "").strip()
        material_parts = [part for part in (source_content.strip(), normalized_content) if part]
        material = "\n\n---\n\n".join(material_parts).strip()
        if not material and not normalized_topic:
            raise SlidevMvpValidationError("请提供 topic、content 或 source_ids 之一。")

        title_hint = normalized_topic or _guess_title_from_content(material) or "Slidev MVP Deck"
        clamped_num_pages = max(2, min(int(num_pages), settings.max_slide_pages))
        return _ResolvedInputs(
            topic=normalized_topic or title_hint,
            material=material or normalized_topic,
            num_pages=clamped_num_pages,
            title_hint=title_hint,
            source_hints=_build_source_hints(source_metas),
        )

    def _should_use_long_deck_mode(self, num_pages: int) -> bool:
        return int(num_pages) >= LONG_DECK_TRIGGER_PAGES

    async def _run_short_deck_generation(
        self,
        *,
        resolved: _ResolvedInputs,
        state: PipelineState,
        runtime: _RuntimeContext,
        todo_manager: TodoManager,
        registry: ToolRegistry,
    ) -> AgenticLoopResult:
        last_error: SlidevMvpError | None = None
        for attempt in range(1, SHORT_DECK_GENERATION_RETRY_LIMIT + 1):
            self._prepare_generation_attempt(
                state=state,
                runtime=runtime,
                stage="short_generation",
                attempt=attempt,
            )
            try:
                loop_result = await agentic_loop(
                    user_prompt=self._build_user_prompt(resolved),
                    model=self.model,
                    state=state,
                    todo_manager=todo_manager,
                    skill_summaries=build_skill_summaries(self.skill_registry),
                    harness_path=self.harness_path,
                    tool_definitions=registry.to_model_tools(),
                    dispatch_tools=lambda calls: dispatch_tool_calls(calls, registry),
                    max_turns=24,
                )
                if runtime.saved_artifact is None:
                    runtime.saved_artifact = await self._controller_finalize_deck(
                        title=resolved.title_hint,
                        state=state,
                        runtime=runtime,
                    )
                self._record_stage(
                    state=state,
                    runtime=runtime,
                    stage="short_generation",
                    status="ok",
                    attempt=attempt,
                )
                return loop_result
            except UnexpectedModelBehavior as exc:
                provider_error = _provider_response_error(exc)
                self._record_provider_error(
                    state=state,
                    runtime=runtime,
                    stage="short_generation",
                    attempt=attempt,
                    error=provider_error,
                )
                last_error = provider_error
                if attempt >= SHORT_DECK_GENERATION_RETRY_LIMIT:
                    self._record_stage(
                        state=state,
                        runtime=runtime,
                        stage="short_generation",
                        status="failed",
                        attempt=attempt,
                        reason_code=provider_error.reason_code,
                    )
                    raise provider_error from exc
                self._record_retry(
                    state=state,
                    runtime=runtime,
                    stage="short_generation",
                    attempt=attempt,
                    reason_code=provider_error.reason_code,
                    message=provider_error.message,
                )
            except SlidevMvpValidationError as exc:
                last_error = exc
                retryable = _should_retry_generation_failure(
                    exc,
                    attempt=attempt,
                    retry_limit=SHORT_DECK_GENERATION_RETRY_LIMIT,
                )
                self._record_stage(
                    state=state,
                    runtime=runtime,
                    stage="short_generation",
                    status="retrying" if retryable else "failed",
                    attempt=attempt,
                    reason_code=exc.reason_code,
                )
                if not retryable:
                    raise
                self._record_retry(
                    state=state,
                    runtime=runtime,
                    stage="short_generation",
                    attempt=attempt,
                    reason_code=exc.reason_code or "generation_validation_failed",
                    message=exc.message,
                )
        if last_error is not None:
            raise last_error
        raise SlidevMvpValidationError("Slidev short deck generation ended without a result.")

    async def _run_long_deck_generation(
        self,
        *,
        resolved: _ResolvedInputs,
        state: PipelineState,
        runtime: _RuntimeContext,
        todo_manager: TodoManager,
        registry: ToolRegistry,
    ) -> AgenticLoopResult:
        runtime.long_deck_mode = True
        state.document_metadata["slidev_long_deck_mode"] = True

        planning_registry = filter_registry(registry, LONG_DECK_PLANNING_TOOLS)
        planning_result = await self._run_long_deck_planning(
            resolved=resolved,
            state=state,
            runtime=runtime,
            todo_manager=todo_manager,
            planning_registry=planning_registry,
        )
        chunk_specs = self._build_chunk_specs(state=state, runtime=runtime)
        runtime.chunk_plan = [_chunk_metadata(spec) for spec in chunk_specs]
        state.document_metadata["slidev_chunk_plan"] = list(runtime.chunk_plan)

        try:
            self._record_stage(state=state, runtime=runtime, stage="chunk_generation", status="started")
            chunk_executions = await self._run_chunk_generation(
                chunk_specs=chunk_specs,
                resolved=resolved,
                runtime=runtime,
                state=state,
            )
        except SlidevMvpValidationError:
            state.document_metadata["slidev_chunk_reports"] = list(runtime.chunk_reports)
            state.document_metadata["slidev_chunk_summary"] = _build_chunk_summary(
                runtime.chunk_plan,
                runtime.chunk_reports,
            )
            self._record_stage(state=state, runtime=runtime, stage="chunk_generation", status="failed")
            raise
        self._record_stage(state=state, runtime=runtime, stage="chunk_generation", status="ok")

        runtime.used_subagent = True
        runtime.chunk_reports = [_chunk_report_payload(execution) for execution in chunk_executions]
        state.document_metadata["slidev_chunk_reports"] = list(runtime.chunk_reports)
        state.document_metadata["slidev_chunk_summary"] = _build_chunk_summary(
            runtime.chunk_plan,
            runtime.chunk_reports,
        )

        markdown = self._assemble_chunked_markdown(
            title=resolved.title_hint,
            runtime=runtime,
            chunk_executions=chunk_executions,
        )
        self._record_stage(state=state, runtime=runtime, stage="deck_assembly", status="ok")
        runtime.latest_markdown = markdown
        runtime.saved_artifact = await self._controller_finalize_deck(
            title=resolved.title_hint,
            state=state,
            runtime=runtime,
            markdown=markdown,
        )
        return AgenticLoopResult(
            output_text="long deck generated via chunk orchestration",
            messages=planning_result.messages,
            turns=planning_result.turns,
            max_turns_reached=planning_result.max_turns_reached,
            stop_reason="slidev-artifact-saved",
            last_response=planning_result.last_response,
        )

    async def _run_long_deck_planning(
        self,
        *,
        resolved: _ResolvedInputs,
        state: PipelineState,
        runtime: _RuntimeContext,
        todo_manager: TodoManager,
        planning_registry: ToolRegistry,
    ) -> AgenticLoopResult:
        last_error: SlidevMvpError | None = None
        for attempt in range(1, LONG_DECK_PLANNING_RETRY_LIMIT + 1):
            self._prepare_generation_attempt(
                state=state,
                runtime=runtime,
                stage="long_deck_planning",
                attempt=attempt,
                preserve_long_deck_mode=True,
            )
            try:
                planning_result = await agentic_loop(
                    user_prompt=self._build_long_deck_planning_prompt(resolved),
                    model=self.model,
                    state=state,
                    todo_manager=todo_manager,
                    skill_summaries=build_skill_summaries(self.skill_registry),
                    harness_path=self.harness_path,
                    tool_definitions=planning_registry.to_model_tools(),
                    dispatch_tools=lambda calls: dispatch_tool_calls(calls, planning_registry),
                    max_turns=LONG_DECK_PLANNING_MAX_TURNS,
                )
                self._ensure_long_deck_planning_ready(runtime=runtime, state=state)
                self._record_stage(
                    state=state,
                    runtime=runtime,
                    stage="long_deck_planning",
                    status="ok",
                    attempt=attempt,
                )
                return planning_result
            except UnexpectedModelBehavior as exc:
                provider_error = _provider_response_error(exc)
                self._record_provider_error(
                    state=state,
                    runtime=runtime,
                    stage="long_deck_planning",
                    attempt=attempt,
                    error=provider_error,
                )
                last_error = provider_error
                if attempt >= LONG_DECK_PLANNING_RETRY_LIMIT:
                    self._record_stage(
                        state=state,
                        runtime=runtime,
                        stage="long_deck_planning",
                        status="failed",
                        attempt=attempt,
                        reason_code=provider_error.reason_code,
                    )
                    raise provider_error from exc
                self._record_retry(
                    state=state,
                    runtime=runtime,
                    stage="long_deck_planning",
                    attempt=attempt,
                    reason_code=provider_error.reason_code,
                    message=provider_error.message,
                )
            except SlidevMvpValidationError as exc:
                last_error = exc
                retryable = _should_retry_generation_failure(
                    exc,
                    attempt=attempt,
                    retry_limit=LONG_DECK_PLANNING_RETRY_LIMIT,
                )
                self._record_stage(
                    state=state,
                    runtime=runtime,
                    stage="long_deck_planning",
                    status="retrying" if retryable else "failed",
                    attempt=attempt,
                    reason_code=exc.reason_code,
                )
                if not retryable:
                    raise
                self._record_retry(
                    state=state,
                    runtime=runtime,
                    stage="long_deck_planning",
                    attempt=attempt,
                    reason_code=exc.reason_code or "planning_validation_failed",
                    message=exc.message,
                )
        if last_error is not None:
            raise last_error
        raise SlidevMvpValidationError("Slidev long deck planning ended without a result.")

    def _prepare_generation_attempt(
        self,
        *,
        state: PipelineState,
        runtime: _RuntimeContext,
        stage: str,
        attempt: int,
        preserve_long_deck_mode: bool = False,
    ) -> None:
        _reset_generation_state(
            state=state,
            runtime=runtime,
            preserve_long_deck_mode=preserve_long_deck_mode,
        )
        self._record_stage(
            state=state,
            runtime=runtime,
            stage=stage,
            status="started",
            attempt=attempt,
        )

    def _record_stage(
        self,
        *,
        state: PipelineState,
        runtime: _RuntimeContext,
        stage: str,
        status: str,
        attempt: int | None = None,
        reason_code: str | None = None,
    ) -> None:
        event: dict[str, Any] = {"stage": stage, "status": status}
        if attempt is not None:
            event["attempt"] = attempt
        if reason_code:
            event["reason_code"] = reason_code
        runtime.stage_history.append(event)
        state.document_metadata["slidev_stage_history"] = list(runtime.stage_history)
        state.document_metadata["slidev_current_stage"] = {"stage": stage, "status": status}

    def _record_retry(
        self,
        *,
        state: PipelineState,
        runtime: _RuntimeContext,
        stage: str,
        attempt: int,
        reason_code: str,
        message: str,
    ) -> None:
        event = {
            "stage": stage,
            "attempt": attempt,
            "reason_code": reason_code,
            "message": message,
        }
        runtime.retry_events.append(event)
        state.document_metadata["slidev_retry_events"] = list(runtime.retry_events)
        state.document_metadata["slidev_retry_summary"] = _build_retry_summary(runtime.retry_events)

    def _record_provider_error(
        self,
        *,
        state: PipelineState,
        runtime: _RuntimeContext,
        stage: str,
        attempt: int,
        error: SlidevMvpProviderError,
    ) -> None:
        event = {
            "stage": stage,
            "attempt": attempt,
            "reason_code": error.reason_code,
            "message": error.message,
        }
        runtime.provider_errors.append(event)
        state.document_metadata["slidev_provider_errors"] = list(runtime.provider_errors)
        state.document_metadata["slidev_provider_error_summary"] = _build_provider_error_summary(runtime.provider_errors)

    async def _controller_finalize_deck(
        self,
        *,
        title: str,
        state: PipelineState,
        runtime: _RuntimeContext,
        markdown: str | None = None,
    ) -> SlidevMvpArtifacts:
        self._record_stage(state=state, runtime=runtime, stage="controller_finalization", status="started")
        try:
            current_outline_hash = _outline_hash(state.outline)
            if runtime.outline_review is None:
                raise _save_gate_error(
                    reason_code="outline_review_missing",
                    message="还没有完成大纲正式审查，controller 不能 finalization。",
                    next_action="调用 review_slidev_outline()",
                )
            if not bool(runtime.outline_review.get("ok")):
                raise _save_gate_error(
                    reason_code="outline_review_failed",
                    message="Deck 大纲结构审查未通过，controller 不能 finalization。",
                    next_action="修正大纲后重新调用 review_slidev_outline()",
                )
            if runtime.outline_review_hash and runtime.outline_review_hash != current_outline_hash:
                raise _save_gate_error(
                    reason_code="outline_review_stale",
                    message="大纲在审查后发生了变化，controller 不能直接 finalization。",
                    next_action="重新调用 review_slidev_outline()",
                )
            if runtime.reference_selection is None:
                raise _save_gate_error(
                    reason_code="reference_selection_missing",
                    message="还没有完成 Slidev references 选择，controller 不能 finalization。",
                    next_action="调用 select_slidev_references()",
                )
            if runtime.reference_selection_hash and runtime.reference_selection_hash != current_outline_hash:
                raise _save_gate_error(
                    reason_code="reference_selection_stale",
                    message="大纲在选择 references 后发生了变化，controller 不能直接 finalization。",
                    next_action="重新调用 select_slidev_references()",
                )

            candidate_markdown = str(markdown or runtime.latest_markdown or "").strip()
            if not candidate_markdown:
                raise SlidevMvpValidationError(
                    "Controller 没有拿到可 finalization 的 deck markdown。",
                    reason_code="deck_markdown_missing",
                    next_action="先产出完整 deck markdown，并至少完成一次 review_slidev_deck/validate_slidev_deck。",
                )
            candidate_markdown = _apply_style_frontmatter_baseline(
                markdown=candidate_markdown,
                title=title,
                reference_selection=runtime.reference_selection or {},
            )

            runtime.save_failure = None
            outline_items = state.outline.get("items", []) if isinstance(state.outline, dict) else []
            runtime.deck_review = await self._review_markdown(
                markdown=candidate_markdown,
                outline_items=outline_items,
                selected_style=(runtime.reference_selection or {}).get("selected_style") or {},
                selected_theme=(runtime.reference_selection or {}).get("selected_theme") or {},
                selected_layouts=(runtime.reference_selection or {}).get("selected_layouts") or [],
                selected_blocks=(runtime.reference_selection or {}).get("selected_blocks") or [],
                page_briefs=(runtime.reference_selection or {}).get("page_briefs") or [],
                deck_chrome=(runtime.reference_selection or {}).get("deck_chrome") or {},
            )
            runtime.deck_review_hash = _text_hash(candidate_markdown)
            state.document_metadata["slidev_deck_review"] = runtime.deck_review

            runtime.validation = await self._validate_markdown(
                markdown=candidate_markdown,
                expected_pages=int(state.num_pages or runtime.requested_pages or 0),
                selected_style=(runtime.reference_selection or {}).get("selected_style") or {},
                selected_theme=(runtime.reference_selection or {}).get("selected_theme") or {},
                selected_layouts=(runtime.reference_selection or {}).get("selected_layouts") or [],
                selected_blocks=(runtime.reference_selection or {}).get("selected_blocks") or [],
                page_briefs=(runtime.reference_selection or {}).get("page_briefs") or [],
                deck_chrome=(runtime.reference_selection or {}).get("deck_chrome") or {},
            )
            runtime.validation_hash = _text_hash(candidate_markdown)
            state.document_metadata["slidev_validation"] = runtime.validation

            _ensure_save_prerequisites(runtime=runtime, state=state, markdown=candidate_markdown)
            artifact = await self._persist_artifact(
                title=title,
                markdown=candidate_markdown,
                runtime=runtime,
                state=state,
            )
            self._record_stage(state=state, runtime=runtime, stage="controller_finalization", status="ok")
            return artifact
        except SlidevMvpValidationError as exc:
            self._record_stage(
                state=state,
                runtime=runtime,
                stage="controller_finalization",
                status="failed",
                reason_code=exc.reason_code,
            )
            raise

    def _build_long_deck_planning_prompt(self, resolved: _ResolvedInputs) -> str:
        return (
            "你正在为长 Deck 做全局规划阶段，只完成规划，不要生成最终 markdown。\n\n"
            "必须严格按下面顺序执行：\n"
            "1. update_todo\n"
            "2. load_skill('slidev-syntax')\n"
            "3. load_skill('slidev-deck-quality')\n"
            "4. load_skill('slidev-design-system')\n"
            "5. set_slidev_outline(...)：为整份 deck 生成完整 outline\n"
            "6. review_slidev_outline()\n"
            "7. select_slidev_references()\n"
            "8. 用简短文本确认规划完成后停止，不要生成最终 markdown，不要调用 review_slidev_deck / validate_slidev_deck / save_slidev_artifact。\n\n"
            f"目标页数：{resolved.num_pages} 页\n"
            f"主题：{resolved.topic}\n"
            "要求：长 deck 需要保持全局 style 一致，并覆盖 cover / context / framework / comparison / closing 等结构型角色。\n\n"
            "输入材料：\n"
            f"{resolved.material}"
        )

    def _ensure_long_deck_planning_ready(self, *, runtime: _RuntimeContext, state: PipelineState) -> None:
        outline_items = state.outline.get("items", []) if isinstance(state.outline, dict) else []
        if not outline_items:
            raise SlidevMvpValidationError(
                "长 Deck 规划未产出 outline。",
                reason_code="outline_missing",
                next_action="先完成 set_slidev_outline(...)",
            )
        if runtime.outline_review is None or not bool(runtime.outline_review.get("ok")):
            raise SlidevMvpValidationError(
                "长 Deck 规划阶段未完成 outline review。",
                reason_code="outline_review_missing",
                next_action="完成 review_slidev_outline() 并修正问题。",
            )
        if runtime.reference_selection is None:
            raise SlidevMvpValidationError(
                "长 Deck 规划阶段未完成 references 选择。",
                reason_code="reference_selection_missing",
                next_action="完成 select_slidev_references()。",
            )

    def _build_chunk_specs(self, *, state: PipelineState, runtime: _RuntimeContext) -> list[_ChunkSpec]:
        outline_items = state.outline.get("items", []) if isinstance(state.outline, dict) else []
        selected_layouts_by_slide = {
            int(item.get("slide_number") or 0): dict(item)
            for item in ((runtime.reference_selection or {}).get("selected_layouts") or [])
            if isinstance(item, Mapping)
        }
        selected_blocks_by_slide = {
            int(item.get("slide_number") or 0): {
                **dict(item),
                "blocks": [dict(block) for block in (item.get("blocks") or []) if isinstance(block, Mapping)],
            }
            for item in ((runtime.reference_selection or {}).get("selected_blocks") or [])
            if isinstance(item, Mapping)
        }
        page_briefs_by_slide = {
            int(item.get("slide_number") or 0): dict(item)
            for item in ((runtime.reference_selection or {}).get("page_briefs") or [])
            if isinstance(item, Mapping)
        }
        specs: list[_ChunkSpec] = []
        for index, start in enumerate(range(0, len(outline_items), LONG_DECK_CHUNK_SIZE), start=1):
            items = [dict(item) for item in outline_items[start : start + LONG_DECK_CHUNK_SIZE] if isinstance(item, Mapping)]
            specs.append(
                _ChunkSpec(
                    chunk_id=f"chunk-{index}",
                    outline_items=items,
                    selected_layouts=[
                        selected_layouts_by_slide.get(int(item.get("slide_number") or 0), {})
                        for item in items
                    ],
                    selected_blocks=[
                        selected_blocks_by_slide.get(
                            int(item.get("slide_number") or 0),
                            {"slide_number": int(item.get("slide_number") or 0), "blocks": []},
                        )
                        for item in items
                    ],
                    page_briefs=[
                        page_briefs_by_slide.get(
                            int(item.get("slide_number") or 0),
                            {"slide_number": int(item.get("slide_number") or 0), "slide_role": str(item.get("slide_role") or "")},
                        )
                        for item in items
                    ],
                )
            )
        return specs

    async def _run_chunk_generation(
        self,
        *,
        chunk_specs: Sequence[_ChunkSpec],
        resolved: _ResolvedInputs,
        runtime: _RuntimeContext,
        state: PipelineState,
    ) -> list[_ChunkExecution]:
        pending_specs = list(chunk_specs)
        executions: dict[str, _ChunkExecution] = {}
        attempts_by_chunk: dict[str, int] = {spec.chunk_id: 0 for spec in chunk_specs}
        feedback_by_chunk: dict[str, str] = {}
        latest_reports: dict[str, dict[str, Any]] = {}

        for _attempt in range(1, LONG_DECK_CHUNK_RETRY_LIMIT + 1):
            if not pending_specs:
                break
            try:
                results = await run_parallel_subagents(
                    [
                        SubagentSpec(
                            task=self._build_chunk_task(
                                spec=spec,
                                resolved=resolved,
                                runtime=runtime,
                                retry_feedback=feedback_by_chunk.get(spec.chunk_id, ""),
                            ),
                            allowed_tool_names=[],
                            max_turns=LONG_DECK_CHUNK_MAX_TURNS,
                            system_prompt=(
                                "You are a Slidev chunk writer. Output only markdown for the assigned slides. "
                                "Do not include explanations or wrap the whole answer in code fences. "
                                "Use only supported Slidev layouts and fix every retry finding when provided."
                            ),
                        )
                        for spec in pending_specs
                    ],
                    registry=None,
                    model=self.model,
                )
            except UnexpectedModelBehavior as exc:
                provider_error = _provider_response_error(exc)
                self._record_provider_error(
                    state=state,
                    runtime=runtime,
                    stage="chunk_generation",
                    attempt=_attempt,
                    error=provider_error,
                )
                if _attempt >= LONG_DECK_CHUNK_RETRY_LIMIT:
                    self._record_stage(
                        state=state,
                        runtime=runtime,
                        stage="chunk_generation",
                        status="failed",
                        attempt=_attempt,
                        reason_code=provider_error.reason_code,
                    )
                    raise provider_error from exc
                self._record_retry(
                    state=state,
                    runtime=runtime,
                    stage="chunk_generation",
                    attempt=_attempt,
                    reason_code=provider_error.reason_code,
                    message=provider_error.message,
                )
                continue

            next_pending: list[_ChunkSpec] = []
            for spec, result in zip(pending_specs, results, strict=False):
                attempts_by_chunk[spec.chunk_id] += 1
                fragment_markdown, normalization_report = _normalize_chunk_fragment_with_report(
                    result.output_text,
                    max_slides=len(spec.outline_items),
                )
                review = await self._review_chunk_fragment(spec=spec, markdown=fragment_markdown, runtime=runtime)
                validation = await self._validate_chunk_fragment(spec=spec, markdown=fragment_markdown, runtime=runtime)
                if bool(review.get("ok")) and bool(validation.get("ok")):
                    latest_reports[spec.chunk_id] = _chunk_attempt_report_payload(
                        spec=spec,
                        review=review,
                        validation=validation,
                        attempts=attempts_by_chunk[spec.chunk_id],
                        status="passed",
                        normalization_report=normalization_report,
                    )
                    executions[spec.chunk_id] = _ChunkExecution(
                        spec=spec,
                        fragment_markdown=fragment_markdown,
                        review=review,
                        validation=validation,
                        attempts=attempts_by_chunk[spec.chunk_id],
                        normalization_report=normalization_report,
                    )
                    feedback_by_chunk.pop(spec.chunk_id, None)
                    continue
                latest_reports[spec.chunk_id] = _chunk_attempt_report_payload(
                    spec=spec,
                    review=review,
                    validation=validation,
                    attempts=attempts_by_chunk[spec.chunk_id],
                    status="failed",
                    normalization_report=normalization_report,
                )
                feedback_by_chunk[spec.chunk_id] = _format_chunk_retry_feedback(review=review, validation=validation)
                next_pending.append(spec)

            pending_specs = next_pending

        if pending_specs:
            runtime.chunk_reports = [
                latest_reports[spec.chunk_id]
                for spec in chunk_specs
                if spec.chunk_id in latest_reports
            ]
            failed_summaries = [
                _chunk_failure_summary(latest_reports.get(spec.chunk_id, {}))
                for spec in pending_specs
            ]
            raise SlidevMvpValidationError(
                "长 Deck 分块生成失败：" + "；".join(summary for summary in failed_summaries if summary),
                reason_code="chunk_generation_failed",
                next_action="检查 chunk_summary / chunk_reports 后重新生成。",
            )

        return [executions[spec.chunk_id] for spec in chunk_specs if spec.chunk_id in executions]

    def _build_chunk_task(
        self,
        *,
        spec: _ChunkSpec,
        resolved: _ResolvedInputs,
        runtime: _RuntimeContext,
        retry_feedback: str = "",
    ) -> str:
        selected_style = (runtime.reference_selection or {}).get("selected_style") or {}
        selected_theme = _selected_theme_payload(runtime.reference_selection or {})
        style_name = str(selected_style.get("name") or "default")
        style_tone = str(selected_style.get("tone") or "")
        deck_scaffold_class = str(selected_style.get("deck_scaffold_class") or "")
        theme_config = selected_theme.get("theme_config") or {}
        deck_chrome = dict((runtime.reference_selection or {}).get("deck_chrome") or {})
        baseline_constraints = [
            str(item).strip()
            for item in (selected_style.get("baseline_constraints") or [])
            if str(item).strip()
        ]
        supported_layouts = ", ".join(SLIDEV_SUPPORTED_LAYOUTS)
        lines = [
            f"为长 Deck 生成 {spec.chunk_id} 的 Slidev markdown fragment。",
            "只输出 fragment markdown，不要输出 JSON，不要输出解释。",
            "不要输出全局 frontmatter；只输出本 chunk 的连续 slides。",
            f"这个 chunk 必须输出且只输出 {len(spec.outline_items)} 页。",
            f"主题：{resolved.topic}",
            f"全局 style：{style_name} ({style_tone})",
            f"官方 theme 基底：{selected_theme.get('theme') or 'seriph'}",
            f"deck scaffold class：{deck_scaffold_class or 'none'}",
            f"themeConfig：{json.dumps(theme_config, ensure_ascii=False) if isinstance(theme_config, Mapping) and theme_config else 'none'}",
            "必须遵守全局 outline 与 references，不允许修改页顺序、slide_role、页数预算。",
            f"只能使用这些 Slidev 内置 layout：{supported_layouts}。",
            "不要发明 layout 名；如果推荐 layout 为空或不适配，请改用普通 markdown + class + table/div/mermaid 等结构。",
            f"deck chrome label：{deck_chrome.get('deck_label') or 'none'}",
            "共享 chrome cues："
            f" topline={', '.join(deck_chrome.get('topline_classes') or []) or 'none'};"
            f" kicker={', '.join(deck_chrome.get('kicker_classes') or []) or 'none'};"
            f" subtitle={', '.join(deck_chrome.get('subtitle_classes') or []) or 'none'};"
            f" footer={', '.join(deck_chrome.get('footer_classes') or []) or 'none'}",
            "shared visual scaffold：`hero-cover` / `metric-stack` / `map-with-insights` / `compare-panel` / `action-path` 已有统一视觉皮肤；优先输出这些语义 class，不要用长串 utility class 临时拼版。",
            "",
            "本 chunk 负责的页面：",
        ]
        for item, layout, blocks, brief in zip(
            spec.outline_items,
            spec.selected_layouts,
            spec.selected_blocks,
            spec.page_briefs,
            strict=False,
        ):
            block_names = ", ".join(
                str(block.get("name") or "")
                for block in (blocks.get("blocks") or [])
                if isinstance(block, Mapping)
            ) or "none"
            block_structures = " | ".join(
                _block_recipe_prompt(block)
                for block in (blocks.get("blocks") or [])
                if isinstance(block, Mapping)
            ) or "none"
            lines.append(
                f"- slide {item.get('slide_number')}: {item.get('title')} "
                f"[role={item.get('slide_role')}, goal={item.get('goal')}, "
                f"layout_recipe={layout.get('recipe_name') or 'none'}, layout={layout.get('layout') or 'none'}, "
                f"container={layout.get('container_classes') or 'none'}, content={layout.get('content_classes') or 'none'}, "
                f"required_patterns={','.join(layout.get('required_patterns') or []) or 'none'}, "
                f"required_visual={','.join(layout.get('required_visual_signals') or []) or 'none'}, "
                f"forbidden={','.join(layout.get('forbidden_patterns') or []) or 'none'}, "
                f"blocks={block_names}, block_recipe={block_structures}, must={_chunk_role_requirements(str(item.get('slide_role') or ''))}, "
                f"page_goal={brief.get('page_goal') or 'none'}, narrative_job={brief.get('narrative_job') or 'none'}, "
                f"preferred_composition={brief.get('preferred_composition') or 'none'}]"
            )
            if brief:
                lines.extend(
                    [
                        f"  hero claim: {brief.get('hero_fact_or_claim') or 'none'}",
                        f"  supporting points: {' | '.join(brief.get('supporting_points') or []) or 'none'}",
                        f"  must keep: {' | '.join(brief.get('must_keep') or []) or 'none'}",
                        f"  must avoid: {' | '.join(brief.get('must_avoid') or []) or 'none'}",
                    ]
                )
                lines.extend(_page_brief_scaffold_lines(brief=brief, layout=layout, deck_chrome=deck_chrome))
            role = str(item.get("slide_role") or "").strip().lower()
            if role == "comparison":
                lines.extend(
                    [
                        "  canonical comparison shell:",
                        "  ---",
                        "  layout: two-cols",
                        f"  class: {layout.get('container_classes') or 'deck-comparison'}",
                        "  ---",
                        f"  ## {item.get('title')}",
                        "  ::left::",
                        "  ### 左侧标签",
                        "  - 2-4 条要点",
                        "  ::right::",
                        "  ### 右侧标签",
                        "  - 2-4 条要点",
                        "  **Takeaway**: 用一句 verdict / takeaway 收束这页。",
                    ]
                )
            elif role == "closing":
                lines.extend(
                    [
                        "  canonical closing shell:",
                        "  ---",
                        f"  layout: {layout.get('layout') or 'end'}",
                        f"  class: {layout.get('container_classes') or 'deck-closing'}",
                        "  ---",
                        f"  ## {item.get('title')}",
                        "  **Takeaway**: 用一句 closing headline / takeaway 开场。",
                        "  1. next step / summary",
                        "  2. next step / summary",
                        "  3. next step / summary",
                    ]
                )
        lines.extend(
            [
                "",
                "全局视觉基线：",
                *(f"- {constraint}" for constraint in baseline_constraints),
                "" if baseline_constraints else "",
                "输出要求：",
                f"- 本 chunk 必须严格覆盖且仅覆盖这些 slides；页数必须精确等于 {len(spec.outline_items)}。",
                "- slide 之间用 `---` 分隔。",
                "- 每页只能使用一种开头顺序：若该页需要 `layout:`/`class:`/`transition:`/`background:`，先输出 fenced per-slide frontmatter，再输出对应 slide title 的 markdown heading；若不需要 frontmatter，才直接从标题 heading 开始。",
                "- 不允许把 bare `layout:`/`class:` 放在标题 heading 后面；不允许把 per-slide frontmatter 写进 ```yaml/```md 代码块。",
                "- 每一页都不要额外生成未分配的过渡页、总结页、封底页。",
                "- 需要使用对应的 layout/class/frontmatter 时，写成完整 fenced block。",
                "- 如果某页 selected layout 给出了 required_classes，就必须把这些 class 写进该页 frontmatter 的 `class:`。",
                "- 优先复用 deck chrome：在关键页使用 `slide-topline` / `section-kicker` / `slide-subtitle` / `slide-footer` 等 cue，而不是临时发明结构。",
                "- 对 semantic primitives（`metric-card` / `map-panel` / `insight-card` / `compare-side` / `action-step`）优先直接输出语义 class；不要把这些块写成仅靠 utility class 才成立的结构。",
                "- metric-stack / map-with-insights / compare-panel / action-path 是高优先级 composition primitives；优先兑现 page brief 指定的 preferred_composition。",
                "- cover/context/framework/comparison/closing 不允许退化成普通章节页；每页至少兑现一个明确的 recipe cue。",
                "- cover 页优先使用短 kicker + 标题 + 短副标题；不要写成长段说明。",
                "- context/framework 页优先带 section kicker，并控制 bullet 密度。",
                "- comparison 页必须使用 two-cols、table 或 before/after 这种明确对照结构。",
                "- comparison/closing 页必须出现一句明确 verdict / takeaway line。",
                "- closing 页必须包含 takeaway、summary、next step 三者之一；不能只写“谢谢/讨论/Q&A”。",
                "- comparison/framework/closing 不允许退化成普通 bullet dump。",
                "- comparison 页推荐 canonical skeleton：`layout: two-cols` + `::left::`/`::right::`，左右各有标签，并以一句 verdict / takeaway 收束；若不用 two-cols，则必须给出明确 compare table。",
                "- closing 页推荐 canonical skeleton：`layout: end`（不适配时允许 `center`）+ 一个 closing headline/takeaway line + 2-3 条 next steps 或 summary bullets。",
            ]
        )
        if retry_feedback:
            lines.extend(
                [
                    "",
                    "上一次生成未通过，请逐条修正这些问题后重新输出完整 fragment：",
                    retry_feedback,
                ]
            )
        lines.extend(["", "素材：", resolved.material])
        return "\n".join(lines)

    async def _review_chunk_fragment(
        self,
        *,
        spec: _ChunkSpec,
        markdown: str,
        runtime: _RuntimeContext,
    ) -> dict[str, Any]:
        return await self._review_markdown(
            markdown=_wrap_chunk_as_standalone_deck(markdown, title=spec.chunk_id),
            outline_items=spec.outline_items,
            selected_style=(runtime.reference_selection or {}).get("selected_style") or {},
            selected_theme=(runtime.reference_selection or {}).get("selected_theme") or {},
            selected_layouts=spec.selected_layouts,
            selected_blocks=spec.selected_blocks,
            page_briefs=spec.page_briefs,
            deck_chrome=(runtime.reference_selection or {}).get("deck_chrome") or {},
        )

    async def _validate_chunk_fragment(
        self,
        *,
        spec: _ChunkSpec,
        markdown: str,
        runtime: _RuntimeContext,
    ) -> dict[str, Any]:
        return await self._validate_markdown(
            markdown=_wrap_chunk_as_standalone_deck(markdown, title=spec.chunk_id),
            expected_pages=len(spec.outline_items),
            selected_style=(runtime.reference_selection or {}).get("selected_style") or {},
            selected_theme=(runtime.reference_selection or {}).get("selected_theme") or {},
            selected_layouts=spec.selected_layouts,
            selected_blocks=spec.selected_blocks,
            page_briefs=spec.page_briefs,
            deck_chrome=(runtime.reference_selection or {}).get("deck_chrome") or {},
        )

    async def _review_markdown(
        self,
        *,
        markdown: str,
        outline_items: Sequence[Mapping[str, Any]],
        selected_style: Mapping[str, Any],
        selected_theme: Mapping[str, Any],
        selected_layouts: Sequence[Mapping[str, Any]],
        selected_blocks: Sequence[Mapping[str, Any]],
        page_briefs: Sequence[Mapping[str, Any]],
        deck_chrome: Mapping[str, Any],
    ) -> dict[str, Any]:
        try:
            result = await execute_skill(
                "slidev-deck-quality",
                "review_deck.py",
                {
                    "slides": [],
                    "parameters": {
                        "markdown": markdown,
                        "outline_items": list(outline_items),
                        "selected_style": dict(selected_style),
                        "selected_theme": dict(selected_theme),
                        "selected_layouts": list(selected_layouts),
                        "selected_blocks": list(selected_blocks),
                        "page_briefs": list(page_briefs),
                        "deck_chrome": dict(deck_chrome),
                    },
                },
            )
        except SkillExecutionError as exc:
            raise SlidevMvpValidationError(
                f"slidev-deck-quality review 执行失败：{exc}",
                reason_code="deck_review_error",
                next_action="检查 review_deck.py 与 markdown 输入。",
            ) from exc
        if not isinstance(result, dict):
            raise SlidevMvpValidationError(
                "slidev-deck-quality review 必须返回 JSON 对象。",
                reason_code="deck_review_invalid",
                next_action="修正 review_deck.py 输出格式。",
            )
        return result

    async def _validate_markdown(
        self,
        *,
        markdown: str,
        expected_pages: int,
        selected_style: Mapping[str, Any],
        selected_theme: Mapping[str, Any],
        selected_layouts: Sequence[Mapping[str, Any]],
        selected_blocks: Sequence[Mapping[str, Any]],
        page_briefs: Sequence[Mapping[str, Any]],
        deck_chrome: Mapping[str, Any],
    ) -> dict[str, Any]:
        try:
            result = await execute_skill(
                "slidev-syntax",
                "validate_deck.py",
                {
                    "slides": [],
                    "parameters": {
                        "markdown": markdown,
                        "expected_pages": expected_pages,
                        "selected_style": dict(selected_style),
                        "selected_theme": dict(selected_theme),
                        "selected_layouts": list(selected_layouts),
                        "selected_blocks": list(selected_blocks),
                        "page_briefs": list(page_briefs),
                        "deck_chrome": dict(deck_chrome),
                    },
                },
            )
        except SkillExecutionError as exc:
            raise SlidevMvpValidationError(
                f"slidev-syntax validate 执行失败：{exc}",
                reason_code="validation_error",
                next_action="检查 validate_deck.py 与 markdown 输入。",
            ) from exc
        if not isinstance(result, dict):
            raise SlidevMvpValidationError(
                "slidev-syntax validate 必须返回 JSON 对象。",
                reason_code="validation_invalid",
                next_action="修正 validate_deck.py 输出格式。",
            )
        return result

    def _assemble_chunked_markdown(
        self,
        *,
        title: str,
        runtime: _RuntimeContext,
        chunk_executions: Sequence[_ChunkExecution],
    ) -> str:
        selected_theme = _selected_theme_payload(runtime.reference_selection or {})
        theme = str(selected_theme.get("theme") or "seriph")
        all_slides: list[str] = []
        for execution in chunk_executions:
            all_slides.extend(_parse_fragment_slides(execution.fragment_markdown))
        deck_body = _serialize_slidev_slides(all_slides)
        markdown = f"---\ntheme: {theme}\ntitle: {title}\n---\n\n{deck_body}".rstrip() + "\n"
        return _apply_style_frontmatter_baseline(
            markdown=markdown,
            title=title,
            reference_selection=runtime.reference_selection or {},
        )

    def _build_user_prompt(self, resolved: _ResolvedInputs) -> str:
        source_hint_text = _format_source_hints(resolved.source_hints)
        native_mapping_guide = "\n".join(
            (
                f"- {role}: layouts={', '.join(spec['preferred_layouts']) or 'none'}; "
                f"patterns={', '.join(spec['preferred_patterns'])}; "
                f"class={', '.join(spec.get('visual_recipe', {}).get('preferred_classes') or []) or 'none'}; "
                f"recipe={spec.get('visual_recipe', {}).get('description', '')}"
            )
            for role, spec in SLIDEV_NATIVE_PATTERN_GUIDE.items()
        )
        return (
            "请生成一份离线 Slidev MVP deck 的 markdown 源文件。\n\n"
            "必须严格按下面顺序执行，不要跳步：\n"
            "1. 第一轮先调用 update_todo，给出本次 deck 生成计划；除非计划状态发生明显变化，否则不要重复调用 update_todo。\n"
            "2. 再调用 load_skill，name 必须是 'slidev-syntax'。\n"
            "3. 再调用 load_skill，name 必须是 'slidev-deck-quality'。\n"
            "4. 再调用 load_skill，name 必须是 'slidev-design-system'。\n"
            "5. 用 set_slidev_outline 写入页级大纲，每页都必须包含 title / slide_role / content_shape / goal；这个 outline 是 deck contract，不是随手草稿。\n"
            "6. 调用 review_slidev_outline() 审查大纲结构，不要自己拼 review_outline.py 的参数。\n"
            "7. 调用 select_slidev_references()，先锁定 deck-level style/theme 与每页 layout/block references。\n"
            "7.1 把 tool 返回的 selected_style / selected_layouts / selected_blocks 当成执行协议：style 决定 deck 基底，layout 决定页 skeleton，blocks 决定页内信息密度与禁用项。\n"
            "7.2 selected_style 里的 deck_scaffold_class / themeConfig / baseline_constraints 也属于执行协议：把 deck scaffold 写进全局 frontmatter，并让每页兑现相应的 presentation cue。\n"
            "7.3 tool 还会返回 page_briefs：每页都要把 page_goal / narrative_job / hero_fact_or_claim / preferred_composition 落成单一主张，不要只把 outline 标题扩成 bullets。\n"
            "7.4 tool 还会返回 deck_chrome：优先使用 `slide-topline` / `section-kicker` / `slide-subtitle` / `slide-footer` 这些轻量 chrome cue，以及 `metric-stack` / `map-with-insights` / `compare-panel` / `action-path` 这些 composition primitives。\n"
            "7.5 deck 已内置 shared visual scaffold：优先复用语义 class（如 `metric-card` / `map-panel` / `insight-card` / `compare-side` / `action-step`），不要再给这些块附加大串 utility class 充当视觉设计。\n"
            "8. dispatch_subagent 是可选能力：只有在中间页需要额外起草且值得增加一次模型往返时才调用；简单 deck 直接在主循环完成即可。\n"
            "9. 产出完整的 Slidev markdown：第一张 slide 含全局 frontmatter，正文用 --- 分隔，并按 outline 顺序兑现每页 role；优先使用当前 role 对应的 Slidev native layout/pattern；framework/comparison/recommendation/closing 不能退化成无差别 bullet dump。\n"
            "10. 在交给 controller finalization 前，先调用 review_slidev_deck(markdown=...) 做结构审查，例如 {'markdown': '---\\n...'}；hard issues 会阻断保存，warnings 只用于提示改进。\n"
            "11. 再调用 validate_slidev_deck(markdown=...) 做语法审查，例如 {'markdown': '---\\n...'}。\n"
            "12. save_slidev_artifact 只作为兼容出口；controller 会对最终 markdown 重新执行 final review -> validate -> save。不要直接在文本里返回整份 deck。\n\n"
            "额外约束：\n"
            "- 不要直接调用 run_skill 来做 review_outline.py / review_deck.py / validate_deck.py。\n"
            "- subagent 的文本意见不能替代正式审查结果。\n"
            "- 默认采用官方 `seriph` theme 作为视觉基底，不要回退成 `theme: default`。\n"
            "- 全局 frontmatter 默认应包含 selected style 对应的 deck scaffold class 与 themeConfig，除非 tool 明确没有给出这些字段。\n"
            "- 每页先满足 role contract，再兑现对应 visual recipe；不要生成“像 markdown 文档章节”的页面。\n"
            "- page brief 是页级导演稿：先回答这一页在叙事中要完成什么，再决定 bullets/table/div；不要为了凑页数写泛泛的“说明性正文”。\n"
            "- 对 why-now / urgency / macro-shift 这类 context 页，优先使用 `metric-stack`：主数字或主判断 + 2-3 supporting cards + interpretation line。\n"
            "- 对 exposure / risk-map / task-landscape / axis 这类页面，优先使用 `map-with-insights`：左侧 map/quadrant/table，右侧 2-3 insight cards，再补一句 takeaway。\n"
            "- 对 recommendation / closing 页，优先使用 `action-path`：一条结论 headline + 2-4 条 next steps，不要退化成空泛 bullets。\n"
            "- shared visual scaffold 已经提供了 `hero-cover` / `metric-stack` / `map-with-insights` / `compare-panel` / `action-path` 的基础视觉皮肤；优先复用这些语义结构，不要再把视觉表达建立在长串 utility class 上。\n"
            "- 不要依赖大面积 ad-hoc inline `style=` 去硬拼视觉，优先使用 `layout:`、`class:`、Mermaid、table、quote、grid。\n"
            "- 如果 selected layout/block 给出 required_classes / required_visual_signals，就把它们落实成页 frontmatter class、section kicker、verdict/takeaway line、compare labels 等可观察结构。\n"
            "- 关键页应尽量出现 top chrome 或 footer chrome，而不是每页都只有标题开头；cover 之外的页优先给出 `slide-topline` 或 `section-kicker`。\n"
            "- `cover / context / framework / comparison / closing` 都应有明显页型节奏变化，而不是统一 heading + bullets。\n"
            "- 只在 review_slidev_outline / select_slidev_references / review_slidev_deck / validate_slidev_deck 都完成且通过后，才允许 save_slidev_artifact。\n"
            "- 如果你已经完成 markdown 与中间 review/validate，controller 会接手最终 final gate；不要因为记不清 save 顺序而中断 deck 生成。\n\n"
            "第一页语法约束：\n"
            "- 如果第一页就是 cover / center，请把 `layout`、`class` 直接写进开头的全局 frontmatter，不要先输出一个空 `---` 再开封面页。\n"
            "- 如果后续页面要使用 `layout:` / `class:` frontmatter，必须写成完整 fenced block：`---` / `layout: ...` / `class: ...` / `---`；不要输出裸 `layout:` 行。\n"
            "- 推荐第一张 slide 的开头示例：\n"
            "  ---\n"
            "  theme: seriph\n"
            "  title: Deck Title\n"
            "  class: theme-tech-launch deck-cover\n"
            "  themeConfig: {\"palette\": \"tech-launch\", \"density\": \"presentation\", \"emphasis\": \"launch-contrast\"}\n"
            "  layout: cover\n"
            "  ---\n"
            "  Launch Brief\n"
            "  # 标题\n"
            "  一句副标题\n\n"
            "重点页型 visual recipe：\n"
            "- cover: short kicker + hero title + short subtitle + sparse density；不能像普通正文标题页。\n"
            "- context: section kicker + compact bullets + quote/callout 至少一种；不能只有平铺 bullet dump。\n"
            "- framework: section kicker + Mermaid / table / grid + takeaway；不能只列条目。\n"
            "- comparison: `layout: two-cols` 或强 compare table，左右要有明确标签，并补一句 verdict。\n"
            "- closing: `layout: end` / `center` + takeaway / next steps + closing line；不能只是“谢谢”。\n\n"
            "Slidev native pattern 优先级（按当前 slide_role 兑现，不要把它们当新的主 taxonomy）：\n"
            f"{native_mapping_guide}\n\n"
            f"目标页数：约 {resolved.num_pages} 页\n"
            f"推荐页型集合：{', '.join(SLIDEV_OUTLINE_ROLES)}\n"
            f"主题：{resolved.topic}\n"
            f"素材概况：{source_hint_text}\n\n"
            "输入材料：\n"
            f"{resolved.material}"
        )

    def _build_registry(
        self,
        *,
        state: PipelineState,
        runtime: _RuntimeContext,
        todo_manager: TodoManager,
    ) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(build_update_todo_tool(todo_manager))

        load_skill_tool = build_load_skill_tool(self.skill_registry)

        async def _load_skill(args: dict[str, Any]) -> Any:
            name = str(args.get("name") or "").strip()
            if name:
                runtime.loaded_skills.add(name)
            return await load_skill_tool.handler(args)

        registry.register(
            ToolDef(
                name=load_skill_tool.name,
                description=load_skill_tool.description,
                input_schema=load_skill_tool.input_schema,
                handler=_load_skill,
            )
        )

        run_skill_tool = build_run_skill_tool(self.skill_registry)

        async def _run_skill(args: dict[str, Any]) -> Any:
            result = await run_skill_tool.handler(args)
            skill_name = str(args.get("name") or "").strip()
            script_name = str(args.get("script") or "").strip()
            parameters = args.get("parameters") or {}
            if not isinstance(parameters, dict):
                parameters = {}
            if skill_name == "slidev-deck-quality" and script_name == "review_outline.py":
                if not isinstance(result, dict):
                    raise SlidevMvpValidationError("slidev-deck-quality outline review must return a JSON object.")
                runtime.outline_review = result
                runtime.outline_review_hash = _outline_hash(state.outline)
                state.document_metadata["slidev_outline_review"] = result
            if skill_name == "slidev-deck-quality" and script_name == "review_deck.py":
                if not isinstance(result, dict):
                    raise SlidevMvpValidationError("slidev-deck-quality deck review must return a JSON object.")
                runtime.latest_markdown = str(parameters.get("markdown") or "")
                runtime.deck_review = result
                runtime.deck_review_hash = _text_hash(runtime.latest_markdown)
                state.document_metadata["slidev_deck_review"] = result
            if skill_name == "slidev-syntax" and script_name == "validate_deck.py":
                if not isinstance(result, dict):
                    raise SlidevMvpValidationError("slidev-syntax validation must return a JSON object.")
                runtime.latest_markdown = str(parameters.get("markdown") or "")
                runtime.validation = result
                runtime.validation_hash = _text_hash(runtime.latest_markdown)
                state.document_metadata["slidev_validation"] = result
            return result

        registry.register(
            ToolDef(
                name=run_skill_tool.name,
                description=run_skill_tool.description,
                input_schema=run_skill_tool.input_schema,
                handler=_run_skill,
            )
        )

        dispatch_subagent_tool = build_dispatch_subagent_tool(registry, model=self.model)

        async def _dispatch_subagent(args: dict[str, Any]) -> Any:
            runtime.used_subagent = True
            normalized_args = dict(args)
            raw_tools = normalized_args.get("tools")
            if raw_tools is None:
                normalized_args["tools"] = list(_SUBAGENT_DEFAULT_TOOLS)
            elif isinstance(raw_tools, list):
                normalized_args["tools"] = [
                    str(name).strip()
                    for name in raw_tools
                    if str(name).strip() and str(name).strip() not in _SUBAGENT_FORBIDDEN_TOOLS
                ]
            return await dispatch_subagent_tool.handler(normalized_args)

        registry.register(
            ToolDef(
                name=dispatch_subagent_tool.name,
                description=dispatch_subagent_tool.description,
                input_schema=dispatch_subagent_tool.input_schema,
                handler=_dispatch_subagent,
            )
        )

        registry.register(build_set_slidev_outline_tool(state))
        registry.register(self._build_review_slidev_outline_tool(state=state, runtime=runtime, run_skill=_run_skill))
        registry.register(self._build_select_slidev_references_tool(state=state, runtime=runtime))
        registry.register(self._build_review_slidev_deck_tool(state=state, runtime=runtime, run_skill=_run_skill))
        registry.register(self._build_validate_slidev_deck_tool(state=state, runtime=runtime, run_skill=_run_skill))
        registry.register(self._build_save_slidev_artifact_tool(state=state, runtime=runtime))
        return registry

    def _build_review_slidev_outline_tool(
        self,
        *,
        state: PipelineState,
        runtime: _RuntimeContext,
        run_skill: Callable[[dict[str, Any]], Awaitable[Any]],
    ) -> ToolDef:
        async def _handler(args: dict[str, Any]) -> Any:
            del args
            outline_items = state.outline.get("items", []) if isinstance(state.outline, dict) else []
            if not outline_items:
                raise SlidevMvpValidationError(
                    "还没有可审查的大纲，请先调用 set_slidev_outline。",
                    reason_code="outline_missing",
                    next_action="先调用 set_slidev_outline(items)",
                )
            return await run_skill(
                {
                    "name": "slidev-deck-quality",
                    "script": "review_outline.py",
                    "parameters": {
                        "outline_items": outline_items,
                        "expected_pages": int(state.num_pages or runtime.requested_pages or len(outline_items)),
                    },
                }
            )

        return ToolDef(
            name="review_slidev_outline",
            description="Review the current Slidev outline stored in state. The tool reads outline_items from state automatically.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_handler,
        )

    def _build_select_slidev_references_tool(
        self,
        *,
        state: PipelineState,
        runtime: _RuntimeContext,
    ) -> ToolDef:
        async def _handler(args: dict[str, Any]) -> Any:
            del args
            outline_items = state.outline.get("items", []) if isinstance(state.outline, dict) else []
            if not outline_items:
                raise SlidevMvpValidationError(
                    "还没有可选的 Slidev references，请先调用 set_slidev_outline。",
                    reason_code="reference_outline_missing",
                    next_action="先调用 set_slidev_outline(items)，再调用 select_slidev_references()",
                )

            result = _select_slidev_references(
                outline_items=outline_items,
                topic=str(state.topic or state.document_metadata.get("title") or ""),
                num_pages=int(state.num_pages or runtime.requested_pages or len(outline_items)),
                material_excerpt=str(state.raw_content or "")[:1500],
            )

            runtime.reference_selection = result
            runtime.reference_selection_hash = _outline_hash(state.outline)
            state.document_metadata["slidev_selected_style"] = result.get("selected_style") or {}
            state.document_metadata["slidev_selected_theme"] = result.get("selected_theme") or {}
            state.document_metadata["slidev_theme_reason"] = str((result.get("selected_theme") or {}).get("theme_reason") or "")
            state.document_metadata["slidev_selected_layouts"] = result.get("selected_layouts") or []
            state.document_metadata["slidev_selected_blocks"] = result.get("selected_blocks") or []
            state.document_metadata["slidev_page_briefs"] = result.get("page_briefs") or []
            state.document_metadata["slidev_deck_chrome"] = result.get("deck_chrome") or {}
            state.document_metadata["slidev_reference_selection"] = result.get("selection_summary") or {}
            return result

        return ToolDef(
            name="select_slidev_references",
            description="Select a deck-level style plus per-slide layout/block references from the current outline.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_handler,
        )

    def _build_review_slidev_deck_tool(
        self,
        *,
        state: PipelineState,
        runtime: _RuntimeContext,
        run_skill: Callable[[dict[str, Any]], Awaitable[Any]],
    ) -> ToolDef:
        async def _handler(args: dict[str, Any]) -> Any:
            markdown = str(args.get("markdown") or "")
            if not markdown.strip():
                raise SlidevMvpValidationError(
                    "review_slidev_deck 需要完整 markdown。",
                    reason_code="deck_markdown_missing",
                    next_action="调用 review_slidev_deck({'markdown': '<完整 deck markdown>'})",
                )
            outline_items = state.outline.get("items", []) if isinstance(state.outline, dict) else []
            return await run_skill(
                {
                    "name": "slidev-deck-quality",
                    "script": "review_deck.py",
                    "parameters": {
                        "markdown": markdown,
                        "outline_items": outline_items,
                        "selected_style": (runtime.reference_selection or {}).get("selected_style") or {},
                        "selected_theme": (runtime.reference_selection or {}).get("selected_theme") or {},
                        "selected_layouts": (runtime.reference_selection or {}).get("selected_layouts") or [],
                        "selected_blocks": (runtime.reference_selection or {}).get("selected_blocks") or [],
                        "page_briefs": (runtime.reference_selection or {}).get("page_briefs") or [],
                        "deck_chrome": (runtime.reference_selection or {}).get("deck_chrome") or {},
                    },
                }
            )

        return ToolDef(
            name="review_slidev_deck",
            description="Review the final Slidev markdown with the current outline context. Pass only the final markdown string.",
            input_schema={
                "type": "object",
                "properties": {"markdown": {"type": "string"}},
                "required": ["markdown"],
                "additionalProperties": False,
            },
            handler=_handler,
        )

    def _build_validate_slidev_deck_tool(
        self,
        *,
        state: PipelineState,
        runtime: _RuntimeContext,
        run_skill: Callable[[dict[str, Any]], Awaitable[Any]],
    ) -> ToolDef:
        async def _handler(args: dict[str, Any]) -> Any:
            markdown = str(args.get("markdown") or "")
            if not markdown.strip():
                raise SlidevMvpValidationError(
                    "validate_slidev_deck 需要完整 markdown。",
                    reason_code="validation_markdown_missing",
                    next_action="调用 validate_slidev_deck({'markdown': '<完整 deck markdown>'})",
                )
            return await run_skill(
                {
                    "name": "slidev-syntax",
                    "script": "validate_deck.py",
                    "parameters": {
                        "markdown": markdown,
                        "expected_pages": int(state.num_pages or runtime.requested_pages or 0),
                        "selected_style": (runtime.reference_selection or {}).get("selected_style") or {},
                        "selected_theme": (runtime.reference_selection or {}).get("selected_theme") or {},
                        "selected_layouts": (runtime.reference_selection or {}).get("selected_layouts") or [],
                        "selected_blocks": (runtime.reference_selection or {}).get("selected_blocks") or [],
                        "page_briefs": (runtime.reference_selection or {}).get("page_briefs") or [],
                        "deck_chrome": (runtime.reference_selection or {}).get("deck_chrome") or {},
                    },
                }
            )

        return ToolDef(
            name="validate_slidev_deck",
            description="Validate the final Slidev markdown syntax. Pass only the final markdown string.",
            input_schema={
                "type": "object",
                "properties": {"markdown": {"type": "string"}},
                "required": ["markdown"],
                "additionalProperties": False,
            },
            handler=_handler,
        )

    def _build_save_slidev_artifact_tool(
        self,
        *,
        state: PipelineState,
        runtime: _RuntimeContext,
    ) -> ToolDef:
        async def _handler(args: dict[str, Any]) -> ToolExecutionResult:
            title = str(args.get("title") or "").strip()
            markdown = str(args.get("markdown") or "")
            if not title:
                raise ValueError("save_slidev_artifact requires a non-empty 'title'")
            if not markdown.strip():
                raise ValueError("save_slidev_artifact requires non-empty markdown")
            runtime.latest_markdown = markdown
            try:
                _ensure_save_prerequisites(runtime=runtime, state=state, markdown=markdown)
            except SlidevMvpValidationError as exc:
                runtime.save_failure = exc
                raise

            artifact = await self._persist_artifact(title=title, markdown=markdown, runtime=runtime, state=state)
            runtime.save_failure = None
            runtime.saved_artifact = artifact
            return ToolExecutionResult(
                content={
                    "deck_id": artifact.deck_id,
                    "artifact_dir": str(artifact.artifact_dir),
                    "slides_path": str(artifact.slides_path),
                    "slide_count": artifact.validation.get("slide_count"),
                    "quality": artifact.quality,
                },
                stop_loop=True,
                metadata={"stop_reason": "slidev-artifact-saved"},
            )

        return ToolDef(
            name="save_slidev_artifact",
            description="Persist the final Slidev markdown artifact after validation passes. This must be the final step.",
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "markdown": {"type": "string"},
                },
                "required": ["title", "markdown"],
                "additionalProperties": False,
            },
            handler=_handler,
        )

    async def _persist_artifact(
        self,
        *,
        title: str,
        markdown: str,
        runtime: _RuntimeContext,
        state: PipelineState,
    ) -> SlidevMvpArtifacts:
        baseline_markdown = _apply_style_frontmatter_baseline(
            markdown=markdown,
            title=title,
            reference_selection=runtime.reference_selection or {},
        )
        normalized_markdown, normalization = _normalize_slidev_composition(baseline_markdown)
        runtime.artifact_dir.mkdir(parents=True, exist_ok=True)
        runtime.slides_path.write_text(normalized_markdown.rstrip() + "\n", encoding="utf-8")
        self._ensure_runtime_link(runtime.artifact_dir)

        slide_count = _count_slidev_slides(normalized_markdown)
        outline_items = state.outline.get("items", []) if isinstance(state.outline, dict) else []
        pattern_hints = _extract_pattern_hints(outline_items)
        visual_hints = _extract_visual_hints(outline_items)
        reference_selection = runtime.reference_selection or {}
        selected_style = dict(reference_selection.get("selected_style") or {})
        selected_theme = _selected_theme_payload(reference_selection)
        selected_layouts = list(reference_selection.get("selected_layouts") or [])
        selected_blocks = list(reference_selection.get("selected_blocks") or [])
        page_briefs = list(reference_selection.get("page_briefs") or [])
        deck_chrome = dict(reference_selection.get("deck_chrome") or {})
        chunk_summary = _build_chunk_summary(runtime.chunk_plan, runtime.chunk_reports)
        retry_summary = _build_retry_summary(runtime.retry_events)
        provider_error_summary = _build_provider_error_summary(runtime.provider_errors)
        runtime.pattern_hints = pattern_hints
        titles_by_slide_number = {
            int(item.get("slide_number") or index + 1): str(item.get("title") or f"Slide {index + 1}")
            for index, item in enumerate(outline_items)
            if isinstance(item, dict)
        }
        state.slide_contents = [
            {
                "slide_number": slide_number,
                "title": titles_by_slide_number.get(slide_number, f"Slide {slide_number}"),
            }
            for slide_number in range(1, slide_count + 1)
        ]
        structure_warnings = _collect_structure_warnings(runtime.outline_review, runtime.deck_review, runtime.validation)
        reference_fidelity_summary = (runtime.deck_review or {}).get("reference_fidelity_summary", {})
        page_brief_fidelity_summary = (runtime.deck_review or {}).get("page_brief_fidelity_summary", {})
        deck_chrome_usage_summary = (
            (runtime.deck_review or {}).get("deck_chrome_usage_summary")
            or (runtime.validation or {}).get("deck_chrome_usage_summary")
            or {}
        )
        theme_fidelity_summary = (
            (runtime.deck_review or {}).get("theme_fidelity_summary")
            or (runtime.validation or {}).get("theme_fidelity_summary")
            or {}
        )
        state.document_metadata.update(
            {
                "slidev_slide_count": slide_count,
                "slidev_long_deck_mode": runtime.long_deck_mode,
                "slidev_validation": runtime.validation or {},
                "slidev_outline_review": runtime.outline_review or {},
                "slidev_deck_review": runtime.deck_review or {},
                "slidev_structure_warnings": structure_warnings,
                "slidev_pattern_hints": pattern_hints,
                "slidev_visual_hints": visual_hints,
                "slidev_selected_style": selected_style,
                "slidev_selected_theme": selected_theme,
                "slidev_theme_reason": str(selected_theme.get("theme_reason") or ""),
                "slidev_selected_layouts": selected_layouts,
                "slidev_selected_blocks": selected_blocks,
                "slidev_page_briefs": page_briefs,
                "slidev_deck_chrome": deck_chrome,
                "slidev_native_usage": (runtime.validation or {}).get("native_usage_summary", {}),
                "slidev_mapping_summary": _build_mapping_summary(pattern_hints, runtime.validation or {}),
                "slidev_visual_recipe_summary": _build_visual_recipe_summary(
                    visual_hints,
                    runtime.deck_review or {},
                    runtime.validation or {},
                ),
                "slidev_reference_fidelity": reference_fidelity_summary,
                "slidev_page_brief_fidelity": page_brief_fidelity_summary,
                "slidev_deck_chrome_usage": deck_chrome_usage_summary,
                "slidev_theme_fidelity": theme_fidelity_summary,
                "slidev_chunk_plan": list(runtime.chunk_plan),
                "slidev_chunk_reports": list(runtime.chunk_reports),
                "slidev_chunk_summary": chunk_summary,
                "slidev_retry_summary": retry_summary,
                "slidev_provider_error_summary": provider_error_summary,
                "slidev_stage_history": list(runtime.stage_history),
                "slidev_composition_normalization": {
                    "blank_first_slide_detected": bool(normalization.get("blank_first_slide_detected")),
                    "double_separator_frontmatter_detected": bool(
                        normalization.get("double_separator_frontmatter_detected")
                    ),
                    "normalized_double_separator_frontmatter_count": int(
                        normalization.get("normalized_double_separator_frontmatter_count") or 0
                    ),
                    "stray_metadata_repaired_count": int(normalization.get("stray_metadata_repaired_count") or 0),
                    "empty_slide_repaired_count": int(normalization.get("empty_slide_repaired_count") or 0),
                    "normalizer_actions": list(normalization.get("normalizer_actions") or []),
                },
                "slidev_blank_first_slide_detected": bool(normalization.get("blank_first_slide_detected")),
                "slidev_artifact_dir": str(runtime.artifact_dir),
                "slidev_slides_path": str(runtime.slides_path),
            }
        )

        return SlidevMvpArtifacts(
            deck_id=runtime.deck_id,
            title=title,
            markdown=normalized_markdown,
            artifact_dir=runtime.artifact_dir,
            slides_path=runtime.slides_path,
            build_output_dir=None,
            dev_command=self._dev_command(runtime.slides_path),
            build_command=self._build_command(runtime.slides_path, runtime.artifact_dir / "dist"),
            validation=runtime.validation or {},
            quality={
                "outline_review": runtime.outline_review or {},
                "deck_review": runtime.deck_review or {},
                "structure_warnings": structure_warnings,
                "pattern_hints": pattern_hints,
                "visual_hints": visual_hints,
                "selected_style": selected_style,
                "selected_theme": str(selected_theme.get("theme") or "seriph"),
                "theme_reason": str(selected_theme.get("theme_reason") or ""),
                "selected_layouts": selected_layouts,
                "selected_blocks": selected_blocks,
                "page_briefs": page_briefs,
                "deck_chrome": deck_chrome,
                "mapping_summary": _build_mapping_summary(pattern_hints, runtime.validation or {}),
                "visual_recipe_summary": _build_visual_recipe_summary(
                    visual_hints,
                    runtime.deck_review or {},
                    runtime.validation or {},
                ),
                "reference_fidelity_summary": reference_fidelity_summary,
                "page_brief_fidelity_summary": page_brief_fidelity_summary,
                "deck_chrome_usage_summary": deck_chrome_usage_summary,
                "theme_fidelity_summary": theme_fidelity_summary,
                "chunk_summary": chunk_summary,
                "chunk_reports": list(runtime.chunk_reports),
                "retry_summary": retry_summary,
                "provider_error_summary": provider_error_summary,
                "stage_history": list(runtime.stage_history),
                "composition_normalization": {
                    "blank_first_slide_detected": bool(normalization.get("blank_first_slide_detected")),
                    "double_separator_frontmatter_detected": bool(
                        normalization.get("double_separator_frontmatter_detected")
                    ),
                    "normalized_double_separator_frontmatter_count": int(
                        normalization.get("normalized_double_separator_frontmatter_count") or 0
                    ),
                    "stray_metadata_repaired_count": int(normalization.get("stray_metadata_repaired_count") or 0),
                    "empty_slide_repaired_count": int(normalization.get("empty_slide_repaired_count") or 0),
                    "normalizer_actions": list(normalization.get("normalizer_actions") or []),
                },
                "blank_first_slide_detected": bool(normalization.get("blank_first_slide_detected")),
            },
            agentic={},
        )

    async def _run_slidev_build(self, *, slides_path: Path, output_dir: Path) -> None:
        package_json = self.sandbox_dir / "package.json"
        if not package_json.exists():
            raise SlidevMvpBuildError(f"Slidev sandbox 未初始化: {package_json}")

        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        if not (self.sandbox_dir / "node_modules").exists():
            await self._run_shell(["pnpm", "install"], cwd=self.sandbox_dir, failure_prefix="Slidev sandbox install failed")

        self._ensure_runtime_link(slides_path.parent)
        output_dir.mkdir(parents=True, exist_ok=True)
        await self._run_shell(
            ["./node_modules/.bin/slidev", "build", slides_path.name, "--out", output_dir.name],
            cwd=slides_path.parent,
            failure_prefix="Slidev build failed",
        )

    async def _run_shell(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        failure_prefix: str,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return await self.shell_runner(command, cwd)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            details = stderr or stdout or str(exc)
            raise SlidevMvpBuildError(f"{failure_prefix}: {details[:800]}") from exc

    def _dev_command(self, slides_path: Path) -> str:
        cmd = ["./node_modules/.bin/slidev", slides_path.name]
        return f"cd {shlex.quote(str(slides_path.parent))} && {' '.join(shlex.quote(part) for part in cmd)}"

    def _build_command(self, slides_path: Path, output_dir: Path) -> str:
        cmd = ["./node_modules/.bin/slidev", "build", slides_path.name, "--out", output_dir.name]
        return f"cd {shlex.quote(str(slides_path.parent))} && {' '.join(shlex.quote(part) for part in cmd)}"

    def _ensure_runtime_link(self, artifact_dir: Path) -> None:
        runtime_link = artifact_dir / "node_modules"
        sandbox_node_modules = self.sandbox_dir / "node_modules"
        if runtime_link.is_symlink() and runtime_link.resolve() == sandbox_node_modules.resolve():
            return
        if runtime_link.exists():
            raise SlidevMvpBuildError(f"artifact runtime path already exists and is not managed by Slidev MVP: {runtime_link}")
        runtime_link.symlink_to(sandbox_node_modules, target_is_directory=True)


def build_set_slidev_outline_tool(state: PipelineState) -> ToolDef:
    async def _handler(args: dict[str, Any]) -> str:
        items = args.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("set_slidev_outline requires a non-empty 'items' array")

        outline_items: list[dict[str, Any]] = []
        for index, raw in enumerate(items, start=1):
            if not isinstance(raw, dict):
                raise ValueError("set_slidev_outline items must be objects")
            title = str(raw.get("title") or "").strip()
            if not title:
                raise ValueError("set_slidev_outline items require a non-empty title")
            slide_role = str(raw.get("slide_role") or "").strip().lower()
            if slide_role not in SLIDEV_OUTLINE_ROLES:
                raise ValueError(
                    f"set_slidev_outline slide_role must be one of {SLIDEV_OUTLINE_ROLES}; got {slide_role!r}"
                )
            content_shape = str(raw.get("content_shape") or "").strip()
            if not content_shape:
                raise ValueError("set_slidev_outline items require a non-empty content_shape")
            goal = str(raw.get("goal") or "").strip()
            if not goal:
                raise ValueError("set_slidev_outline items require a non-empty goal")
            raw_slide_number = raw.get("slide_number", index)
            try:
                slide_number = int(raw_slide_number)
            except (TypeError, ValueError) as exc:
                raise ValueError("set_slidev_outline slide_number must be an integer") from exc
            if slide_number <= 0:
                raise ValueError("set_slidev_outline slide_number must be a positive integer")
            pattern_hint = _build_slidev_pattern_hint(slide_role=slide_role, content_shape=content_shape)
            visual_hint = _build_slidev_visual_hint(slide_role=slide_role, content_shape=content_shape)
            outline_items.append(
                {
                    "slide_number": slide_number,
                    "title": title,
                    "slide_role": slide_role,
                    "content_shape": content_shape,
                    "goal": goal,
                    "slidev_pattern_hint": pattern_hint,
                    "slidev_visual_hint": visual_hint,
                }
            )

        slide_numbers = [int(item["slide_number"]) for item in outline_items]
        if len(slide_numbers) != len(set(slide_numbers)):
            raise ValueError("set_slidev_outline slide_number values must be unique")
        expected_numbers = list(range(1, len(outline_items) + 1))
        if sorted(slide_numbers) != expected_numbers:
            raise ValueError("set_slidev_outline slide_number values must form a continuous 1..N sequence")

        state.outline = {"items": outline_items}
        state.num_pages = max(int(state.num_pages or 0), len(outline_items))
        state.document_metadata["slidev_pattern_hints"] = [
            {
                "slide_number": int(item["slide_number"]),
                "title": str(item["title"]),
                "slide_role": str(item["slide_role"]),
                "preferred_layouts": list(item.get("slidev_pattern_hint", {}).get("preferred_layouts") or []),
                "preferred_patterns": list(item.get("slidev_pattern_hint", {}).get("preferred_patterns") or []),
            }
            for item in outline_items
        ]
        state.document_metadata["slidev_visual_hints"] = [
            {
                "slide_number": int(item["slide_number"]),
                "title": str(item["title"]),
                "slide_role": str(item["slide_role"]),
                "visual_recipe": dict(item.get("slidev_visual_hint") or {}),
            }
            for item in outline_items
        ]
        role_preview = "，".join(f"{item['title']}({item['slide_role']})" for item in outline_items[:4])
        suffix = "，..." if len(outline_items) > 4 else ""
        hint_preview = "；".join(
            _pattern_hint_preview(item.get("slidev_pattern_hint", {})) for item in outline_items[:3] if isinstance(item, dict)
        )
        hint_suffix = f" Native hints: {hint_preview}" if hint_preview else ""
        return f"Recorded Slidev outline with {len(outline_items)} planned slides: {role_preview}{suffix}{hint_suffix}"

    return ToolDef(
        name="set_slidev_outline",
        description="Record the planned Slidev slide outline so the harness state reflects the deck plan.",
        input_schema={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "slide_number": {"type": "integer"},
                            "title": {"type": "string"},
                            "slide_role": {"type": "string", "enum": list(SLIDEV_OUTLINE_ROLES)},
                            "content_shape": {"type": "string"},
                            "goal": {"type": "string"},
                        },
                        "required": ["title", "slide_role", "content_shape", "goal"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["items"],
            "additionalProperties": False,
        },
        handler=_handler,
    )


async def _default_shell_runner(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(command),
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
        )

    return await asyncio.to_thread(_run)


def _build_source_hints(source_metas: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, int] = {}
    for meta in source_metas:
        category = str(meta.get("fileCategory") or meta.get("file_category") or "unknown").strip().lower()
        by_category[category] = by_category.get(category, 0) + 1
    return {
        "total_sources": len(source_metas),
        "by_file_category": by_category,
    }


def _format_source_hints(source_hints: Mapping[str, Any]) -> str:
    total_sources = int(source_hints.get("total_sources") or 0)
    by_category = source_hints.get("by_file_category") or {}
    if not total_sources:
        return "仅使用 topic/content 文本输入"
    if not isinstance(by_category, Mapping) or not by_category:
        return f"{total_sources} 个来源文件"
    details = ", ".join(f"{name}:{count}" for name, count in sorted(by_category.items()))
    return f"{total_sources} 个来源文件 ({details})"


def _guess_title_from_content(material: str) -> str:
    for line in material.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:80]
    return ""


def _sanitize_markdown_fragment(text: str) -> str:
    raw = str(text or "").strip()
    fenced = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```$", raw, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return raw


def _normalize_chunk_fragment(text: str, *, max_slides: int) -> str:
    normalized, _report = _normalize_chunk_fragment_with_report(text, max_slides=max_slides)
    return normalized


def _normalize_chunk_fragment_with_report(text: str, *, max_slides: int) -> tuple[str, dict[str, Any]]:
    fragment = _sanitize_markdown_fragment(text)
    fragment = _strip_scaffold_slide_labels(fragment)
    fragment = _normalize_compact_frontmatter_openers(fragment)
    fragment = _normalize_fake_frontmatter_code_fences(fragment)
    fragment = _normalize_unfenced_slide_frontmatter(fragment)
    fragment = _normalize_chunk_heading_boundaries(fragment, max_slides=max_slides)
    fragment = _normalize_compact_frontmatter_openers(fragment)
    fragment = _normalize_fake_frontmatter_code_fences(fragment)
    fragment = _normalize_unclosed_code_fences(fragment)
    slides: list[str] = []
    promoted_internal_frontmatter = False
    for slide in _parse_fragment_slides(fragment):
        normalized_slide, slide_report = _normalize_chunk_slide_with_report(slide)
        slides.append(normalized_slide)
        promoted_internal_frontmatter = promoted_internal_frontmatter or bool(
            slide_report.get("promoted_internal_frontmatter")
        )
    slides, compaction_report = _compact_stray_metadata_slides(slides)
    if max_slides > 0:
        slides = slides[:max_slides]
    if not slides:
        return fragment, {
            "promoted_internal_frontmatter": False,
            "normalizer_actions": [],
            "stray_metadata_repaired_count": 0,
            "empty_slide_repaired_count": 0,
        }
    normalizer_actions: list[str] = []
    if promoted_internal_frontmatter:
        normalizer_actions.append("promoted_internal_frontmatter")
    if int(compaction_report.get("stray_metadata_repaired_count") or 0) > 0:
        normalizer_actions.append("stray_metadata_slide_compacted")
    return (
        _serialize_slidev_slides(slides),
        {
            "promoted_internal_frontmatter": promoted_internal_frontmatter,
            "normalizer_actions": normalizer_actions,
            "stray_metadata_repaired_count": int(compaction_report.get("stray_metadata_repaired_count") or 0),
            "empty_slide_repaired_count": int(compaction_report.get("empty_slide_repaired_count") or 0),
        },
    )


def _normalize_fake_frontmatter_code_fences(fragment: str) -> str:
    lines = str(fragment or "").splitlines()
    if lines:
        normalized: list[str] = []
        index = 0
        while index < len(lines):
            stripped = lines[index].strip()
            if re.match(r"^```(?:ya?ml)?\s*$", stripped, re.IGNORECASE):
                block, next_index = _consume_yaml_frontmatter_opener(lines, index + 1)
                if block:
                    normalized.extend(["---", *block, "---"])
                    index = next_index
                    continue
            normalized.append(lines[index])
            index += 1
        fragment = "\n".join(normalized)

    pattern = re.compile(r"```(?:ya?ml)?\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)

    def _replace(match: re.Match[str]) -> str:
        lines = _extract_frontmatter_lines_from_block(match.group(1))
        if not lines:
            return match.group(0)
        return "\n".join(["---", *lines, "---"])

    return pattern.sub(_replace, str(fragment or ""))


def _normalize_compact_frontmatter_openers(fragment: str) -> str:
    lines = str(fragment or "").splitlines()
    if not lines:
        return str(fragment or "")

    allowed = {"layout", "class", "transition", "background"}
    normalized: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if stripped.startswith("---"):
            remainder = stripped[3:].lstrip()
            key = _frontmatter_key(remainder)
            if key in allowed:
                normalized.extend(["---", remainder])
                continue
        normalized.append(raw_line)
    return "\n".join(normalized)


def _normalize_unfenced_slide_frontmatter(fragment: str) -> str:
    lines = str(fragment or "").splitlines()
    if not lines:
        return str(fragment or "")

    result: list[str] = []
    index = 0
    at_slide_start = True

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if at_slide_start and stripped == "---":
            block, next_index = _consume_slide_frontmatter_block(lines, index + 1)
            if block is not None:
                result.extend(["---", *block, "---"])
                index = next_index
                at_slide_start = False
                continue
            index += 1
            continue

        if at_slide_start:
            block, next_index = _consume_unfenced_frontmatter_lines(lines, index)
            if block:
                result.extend(["---", *block, "---"])
                index = next_index
                at_slide_start = False
                continue

        if stripped == "---":
            result.append("---")
            at_slide_start = True
            index += 1
            continue

        result.append(line)
        if stripped:
            at_slide_start = False
        index += 1

    return "\n".join(result).strip()


def _normalize_chunk_slide(slide: str) -> str:
    normalized, _report = _normalize_chunk_slide_with_report(slide)
    return normalized


def _normalize_chunk_slide_with_report(slide: str) -> tuple[str, dict[str, Any]]:
    normalized = str(slide or "").strip()
    if not normalized:
        return normalized, {"promoted_internal_frontmatter": False}
    normalized = _strip_scaffold_slide_heading(normalized)
    normalized, promoted_internal_frontmatter = _promote_internal_frontmatter_after_heading(normalized)
    normalized = _move_internal_frontmatter_to_top(normalized)
    normalized = _balance_html_container_tags(normalized)
    return normalized.strip(), {"promoted_internal_frontmatter": promoted_internal_frontmatter}


def _strip_scaffold_slide_labels(fragment: str) -> str:
    lines = str(fragment or "").splitlines()
    if not lines:
        return str(fragment or "")
    result: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^#\s*slide\s+\d+\s*[:：].+$", stripped, re.IGNORECASE):
            lookahead = "\n".join(lines[index + 1 : index + 10])
            if "```yaml" in lookahead or "```yml" in lookahead or re.search(r"^\s*#{1,3}\s+\S+", lookahead, re.MULTILINE):
                continue
        result.append(line)
    return "\n".join(result).strip()


def _strip_scaffold_slide_heading(slide: str) -> str:
    lines = slide.splitlines()
    if not lines:
        return slide
    first_nonempty_index = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first_nonempty_index is None:
        return slide
    first_line = lines[first_nonempty_index].strip()
    if not re.match(r"^#\s*slide\s+\d+\s*[:：].+$", first_line, re.IGNORECASE):
        return slide
    next_lines = lines[first_nonempty_index + 1 :]
    if any(re.match(r"^\s*#{1,3}\s+\S+", line) for line in next_lines) or any("layout:" in line for line in next_lines):
        del lines[first_nonempty_index]
        while first_nonempty_index < len(lines) and not lines[first_nonempty_index].strip():
            del lines[first_nonempty_index]
        return "\n".join(lines).strip()
    return slide


def _move_internal_frontmatter_to_top(slide: str) -> str:
    if slide.startswith("---\n"):
        return slide

    lines = slide.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == "---":
            start = index
            break
    if start is None:
        return slide

    end = None
    for index in range(start + 1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        return slide

    block_lines = _extract_frontmatter_lines_from_block("\n".join(lines[start + 1 : end]))
    if not block_lines:
        return slide

    before = "\n".join(lines[:start]).strip()
    after = "\n".join(lines[end + 1 :]).strip()
    body_parts = [part for part in (before, after) if part]
    body = "\n\n".join(body_parts).strip()
    if not body:
        return "\n".join(["---", *block_lines, "---"]).strip()
    return "\n".join(["---", *block_lines, "---", "", body]).strip()


def _promote_internal_frontmatter_after_heading(slide: str) -> tuple[str, bool]:
    normalized = str(slide or "").strip()
    if not normalized or normalized.startswith("---\n"):
        return normalized, False

    lines = normalized.splitlines()
    first_nonempty_index = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first_nonempty_index is None:
        return normalized, False
    if not _looks_like_heading_boundary(lines[first_nonempty_index].strip()):
        return normalized, False

    block_start = None
    plain_text_lines = 0
    index = first_nonempty_index + 1
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        key = _frontmatter_key(stripped)
        if key in {"layout", "class", "transition", "background"}:
            block_start = index
            break
        if (
            stripped.startswith(("---", "#", "-", "*", ">", "|", "::", "```", "~~~", "<"))
            or re.match(r"^\d+\.\s", stripped)
        ):
            return normalized, False
        plain_text_lines += 1
        if plain_text_lines > 2:
            return normalized, False
        index += 1

    if block_start is None:
        return normalized, False

    block, next_index = _consume_unfenced_frontmatter_lines(lines, block_start)
    if not block or not any(line.strip() for line in lines[next_index:]):
        return normalized, False

    body_lines = [lines[first_nonempty_index], *lines[first_nonempty_index + 1 : block_start], *lines[next_index:]]
    promoted = ["---", *block, "---", "", *body_lines]
    return "\n".join(promoted).strip(), True


def _extract_frontmatter_lines_from_block(block: str) -> list[str]:
    allowed = {"layout", "class", "transition", "background"}
    lines: list[str] = []
    for raw_line in str(block or "").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped == "---":
            continue
        key = _frontmatter_key(stripped)
        if key not in allowed:
            return []
        lines.append(stripped)
    return lines


def _consume_yaml_frontmatter_opener(lines: Sequence[str], start_index: int) -> tuple[list[str], int]:
    index = start_index
    while index < len(lines) and not lines[index].strip():
        index += 1

    if index >= len(lines):
        return [], start_index

    saw_inner_fence = lines[index].strip() == "---"
    if saw_inner_fence:
        index += 1

    block, next_index = _consume_unfenced_frontmatter_lines(lines, index)
    if not block:
        return [], start_index

    index = next_index
    if saw_inner_fence:
        if index >= len(lines) or lines[index].strip() != "---":
            return [], start_index
        index += 1

    if index < len(lines) and lines[index].strip() == "```":
        index += 1

    return [line.strip() for line in block], index


def _balance_html_container_tags(slide: str) -> str:
    balanced = slide.rstrip()
    for tag in ("div", "section", "p"):
        open_count = len(re.findall(rf"<{tag}(?=[\s>])[^>]*>", balanced))
        close_count = len(re.findall(rf"</{tag}>", balanced))
        if open_count > close_count:
            balanced += "\n" + "\n".join(f"</{tag}>" for _ in range(open_count - close_count))
    return balanced


def _consume_unfenced_frontmatter_lines(lines: Sequence[str], start_index: int) -> tuple[list[str], int]:
    allowed = {"layout", "class", "transition", "background"}
    index = start_index
    block: list[str] = []
    while index < len(lines):
        raw_line = lines[index].rstrip()
        stripped = raw_line.strip()
        if not stripped:
            break
        key = _frontmatter_key(stripped)
        if key not in allowed:
            break
        block.append(raw_line)
        index += 1
    return block, index


def _normalize_chunk_heading_boundaries(fragment: str, *, max_slides: int) -> str:
    if max_slides <= 1:
        return fragment
    if "\n---\n" in fragment or fragment.strip().startswith("---\n"):
        parsed = _parse_fragment_slides(fragment)
        if len(parsed) >= 2:
            return fragment
    lines = str(fragment or "").splitlines()
    if not lines:
        return fragment

    slides: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if _looks_like_heading_boundary(stripped) and current and not _looks_like_frontmatter_only_chunk(current):
            slides.append(current)
            current = []
        current.append(line)
    if current:
        slides.append(current)

    meaningful_slides = ["\n".join(chunk).strip() for chunk in slides if "\n".join(chunk).strip()]
    if len(meaningful_slides) < 2:
        return fragment
    return "\n\n---\n\n".join(meaningful_slides[:max_slides]).rstrip()


def _looks_like_heading_boundary(stripped_line: str) -> bool:
    if not stripped_line.startswith("#"):
        return False
    return bool(re.match(r"^#{1,3}\s+\S+", stripped_line))


def _looks_like_frontmatter_only_chunk(lines: Sequence[str]) -> bool:
    meaningful = [line.strip() for line in lines if line.strip()]
    if not meaningful:
        return False
    allowed = {"layout", "class", "transition", "background"}
    normalized = [line for line in meaningful if line != "---"]
    if not normalized:
        return False
    return all((_frontmatter_key(line) in allowed) for line in normalized)


def _normalize_unclosed_code_fences(fragment: str) -> str:
    lines = str(fragment or "").splitlines()
    fence_stack: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            marker = "```"
        elif stripped.startswith("~~~"):
            marker = "~~~"
        else:
            continue
        if fence_stack and fence_stack[-1] == marker:
            fence_stack.pop()
        else:
            fence_stack.append(marker)
    if not fence_stack:
        return fragment
    closing_lines = [marker for marker in reversed(fence_stack)]
    return str(fragment).rstrip() + "\n" + "\n".join(closing_lines)


def _chunk_role_requirements(role: str) -> str:
    normalized = role.strip().lower()
    requirements = {
        "cover": "hero title + short subtitle; avoid bullet-heavy body",
        "context": "brief context with quote/callout or compact bullets",
        "framework": "use mermaid/table/grid plus one takeaway line",
        "detail": "one focused point with supporting detail, not a flat dump",
        "comparison": "must use two-cols, table, or before/after compare structure",
        "recommendation": "one decision headline plus 2-4 action items",
        "closing": "must include takeaway, summary, or next step; not just thanks/Q&A",
    }
    return requirements.get(normalized, "follow the assigned role and keep the structure explicit")


def _wrap_chunk_as_standalone_deck(fragment: str, *, title: str) -> str:
    normalized = _sanitize_markdown_fragment(fragment)
    if re.match(r"^---\s*\n.*?\n---\s*(?:\n|$)", normalized, re.DOTALL):
        return normalized
    return f"---\ntheme: seriph\ntitle: {title}\n---\n\n{normalized}".rstrip() + "\n"


def _parse_fragment_slides(fragment: str) -> list[str]:
    return _parse_slidev_slides(_wrap_chunk_as_standalone_deck(fragment, title="chunk"))


def _format_chunk_retry_feedback(*, review: Mapping[str, Any], validation: Mapping[str, Any]) -> str:
    lines: list[str] = []
    seen_codes: set[str] = set()
    review_issues = review.get("issues") if isinstance(review, Mapping) else []
    review_warnings = review.get("warnings") if isinstance(review, Mapping) else []
    validation_issues = validation.get("issues") if isinstance(validation, Mapping) else []
    validation_warnings = validation.get("warnings") if isinstance(validation, Mapping) else []

    for prefix, items in (
        ("review issue", review_issues),
        ("validation issue", validation_issues),
        ("review warning", review_warnings),
        ("validation warning", validation_warnings),
    ):
        if not isinstance(items, list):
            continue
        for item in items[:6]:
            if not isinstance(item, Mapping):
                continue
            code = str(item.get("code") or "unknown")
            message = str(item.get("message") or "").strip()
            seen_codes.add(code)
            lines.append(f"- {prefix} [{code}]: {message}")

    if {"unfenced_slide_frontmatter", "frontmatter_inside_code_fence"} & seen_codes:
        lines.append("- Rewrite slide frontmatter as real Slidev fences before the slide heading. Never use ```yaml blocks for layout/class.")
        lines.append("- Canonical opening example: `---` / `layout: two-cols` / `class: deck-comparison` / `---` / `## Slide Title`.")
    if {"comparison_native_pattern_missing", "comparison_role_mismatch"} & seen_codes:
        lines.append("- For the comparison slide, use `layout: two-cols` plus `::left::` and `::right::`, or one explicit compare table.")
        lines.append("- Keep explicit left/right labels and end the slide with one verdict / takeaway line.")
    if "closing_role_mismatch" in seen_codes:
        lines.append("- For the closing slide, use `layout: end` (or `center` if needed) and include one clear takeaway line plus 2-3 next steps.")
        lines.append("- Do not end with only `谢谢` / `Q&A` / `讨论`; it must read like a real closing slide.")
    if "unbalanced_html_tags" in seen_codes:
        lines.append("- Close every `<div>`, `<section>`, and `<p>` tag before the slide separator.")

    return "\n".join(lines) if lines else "- Fix the previous structural and syntax issues, then regenerate the full fragment."


def _chunk_metadata(spec: _ChunkSpec) -> dict[str, Any]:
    slide_numbers = spec.slide_numbers
    titles = [str(item.get("title") or "") for item in spec.outline_items]
    return {
        "chunk_id": spec.chunk_id,
        "slide_numbers": slide_numbers,
        "slide_count": len(slide_numbers),
        "titles": titles,
    }


def _chunk_report_payload(execution: _ChunkExecution) -> dict[str, Any]:
    return _chunk_attempt_report_payload(
        spec=execution.spec,
        review=execution.review,
        validation=execution.validation,
        attempts=execution.attempts,
        status="passed",
        normalization_report=execution.normalization_report,
    )


def _chunk_attempt_report_payload(
    *,
    spec: _ChunkSpec,
    review: Mapping[str, Any],
    validation: Mapping[str, Any],
    attempts: int,
    status: str,
    normalization_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    review_warnings = review.get("warnings") if isinstance(review, Mapping) else []
    review_issues = review.get("issues") if isinstance(review, Mapping) else []
    validation_warnings = validation.get("warnings") if isinstance(validation, Mapping) else []
    validation_issues = validation.get("issues") if isinstance(validation, Mapping) else []
    return {
        "chunk_id": spec.chunk_id,
        "slide_numbers": spec.slide_numbers,
        "titles": [str(item.get("title") or "") for item in spec.outline_items],
        "attempts": attempts,
        "status": status,
        "normalizer_actions": list((normalization_report or {}).get("normalizer_actions") or []),
        "normalizer_repaired_internal_frontmatter": bool(
            (normalization_report or {}).get("promoted_internal_frontmatter")
        ),
        "stray_metadata_repaired_count": int((normalization_report or {}).get("stray_metadata_repaired_count") or 0),
        "empty_slide_repaired_count": int((normalization_report or {}).get("empty_slide_repaired_count") or 0),
        "review_ok": bool(review.get("ok")),
        "validation_ok": bool(validation.get("ok")),
        "review_warning_count": len(review_warnings) if isinstance(review_warnings, list) else 0,
        "review_issue_count": len(review_issues) if isinstance(review_issues, list) else 0,
        "validation_warning_count": len(validation_warnings) if isinstance(validation_warnings, list) else 0,
        "validation_issue_count": len(validation_issues) if isinstance(validation_issues, list) else 0,
        "review_issue_codes": _issue_codes(review_issues),
        "review_warning_codes": _issue_codes(review_warnings),
        "validation_issue_codes": _issue_codes(validation_issues),
        "validation_warning_codes": _issue_codes(validation_warnings),
        "review_issues": _compact_findings(review_issues),
        "review_warnings": _compact_findings(review_warnings),
        "validation_issues": _compact_findings(validation_issues),
        "validation_warnings": _compact_findings(validation_warnings),
    }


def _issue_codes(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    codes: list[str] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        code = str(item.get("code") or "").strip()
        if code:
            codes.append(code)
    return codes


def _compact_findings(items: Any, *, limit: int = 3) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []
    findings: list[dict[str, str]] = []
    for item in items[:limit]:
        if not isinstance(item, Mapping):
            continue
        findings.append({"code": str(item.get("code") or ""), "message": str(item.get("message") or "")})
    return findings


def _chunk_failure_summary(report: Mapping[str, Any]) -> str:
    if not isinstance(report, Mapping):
        return ""
    chunk_id = str(report.get("chunk_id") or "unknown")
    review_codes = list(report.get("review_issue_codes") or [])
    validation_codes = list(report.get("validation_issue_codes") or [])
    if not review_codes and not validation_codes:
        return f"{chunk_id} 重试后仍失败"
    parts: list[str] = []
    if review_codes:
        parts.append(f"review={','.join(review_codes)}")
    if validation_codes:
        parts.append(f"validation={','.join(validation_codes)}")
    return f"{chunk_id}({'; '.join(parts)})"


def _build_chunk_summary(
    chunk_plan: Sequence[Mapping[str, Any]],
    chunk_reports: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    report_by_chunk = {
        str(report.get("chunk_id") or ""): report
        for report in chunk_reports
        if isinstance(report, Mapping) and str(report.get("chunk_id") or "").strip()
    }
    completed = 0
    retried = 0
    failed_chunks: list[str] = []
    for report in report_by_chunk.values():
        completed += 1
        if int(report.get("attempts") or 0) > 1:
            retried += 1
        if str(report.get("status") or "") != "passed":
            failed_chunks.append(str(report.get("chunk_id") or ""))
    return {
        "planned_chunks": len(chunk_plan),
        "completed_chunks": completed,
        "retried_chunks": retried,
        "failed_chunks": failed_chunks,
        "chunk_ids": [str(item.get("chunk_id") or "") for item in chunk_plan if isinstance(item, Mapping)],
    }


def _build_retry_summary(retry_events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    retries_by_stage: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for event in retry_events:
        if not isinstance(event, Mapping):
            continue
        stage = str(event.get("stage") or "unknown")
        reason = str(event.get("reason_code") or "unknown")
        retries_by_stage[stage] = retries_by_stage.get(stage, 0) + 1
        reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "total_retries": len(retry_events),
        "retries_by_stage": retries_by_stage,
        "reasons": reasons,
        "events": [dict(event) for event in retry_events if isinstance(event, Mapping)],
    }


def _build_provider_error_summary(provider_errors: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    errors_by_reason: dict[str, int] = {}
    errors_by_stage: dict[str, int] = {}
    for event in provider_errors:
        if not isinstance(event, Mapping):
            continue
        stage = str(event.get("stage") or "unknown")
        reason = str(event.get("reason_code") or "provider_unknown")
        errors_by_stage[stage] = errors_by_stage.get(stage, 0) + 1
        errors_by_reason[reason] = errors_by_reason.get(reason, 0) + 1
    return {
        "total_provider_errors": len(provider_errors),
        "errors_by_stage": errors_by_stage,
        "errors_by_reason": errors_by_reason,
        "events": [dict(event) for event in provider_errors if isinstance(event, Mapping)],
    }


def _reset_generation_state(
    *,
    state: PipelineState,
    runtime: _RuntimeContext,
    preserve_long_deck_mode: bool,
) -> None:
    state.outline = {}
    state.slide_contents = []
    for key in [name for name in list(state.document_metadata) if name.startswith("slidev_")]:
        if preserve_long_deck_mode and key == "slidev_long_deck_mode":
            continue
        state.document_metadata.pop(key, None)

    runtime.outline_review = None
    runtime.outline_review_hash = None
    runtime.deck_review = None
    runtime.deck_review_hash = None
    runtime.validation = None
    runtime.validation_hash = None
    runtime.reference_selection = None
    runtime.reference_selection_hash = None
    runtime.pattern_hints = []
    runtime.latest_markdown = ""
    runtime.chunk_plan = []
    runtime.chunk_reports = []
    runtime.save_failure = None
    runtime.saved_artifact = None
    if not preserve_long_deck_mode:
        runtime.long_deck_mode = False


def _should_retry_generation_failure(
    exc: SlidevMvpValidationError,
    *,
    attempt: int,
    retry_limit: int,
) -> bool:
    if attempt >= retry_limit:
        return False
    retryable_reasons = {
        "outline_missing",
        "outline_review_missing",
        "outline_review_failed",
        "outline_review_stale",
        "reference_selection_missing",
        "reference_selection_stale",
        "deck_markdown_missing",
        "deck_review_missing",
        "deck_review_failed",
        "deck_review_stale",
        "validation_missing",
        "validation_failed",
        "validation_stale",
        "chunk_generation_failed",
    }
    return str(exc.reason_code or "") in retryable_reasons


def _count_slidev_slides(markdown: str) -> int:
    return len(_parse_slidev_slides(markdown))


def _build_slidev_pattern_hint(*, slide_role: str, content_shape: str) -> dict[str, Any]:
    base = dict(SLIDEV_NATIVE_PATTERN_GUIDE.get(slide_role, {"preferred_layouts": [], "preferred_patterns": [], "reason": ""}))
    layouts = list(base.get("preferred_layouts") or [])
    patterns = list(base.get("preferred_patterns") or [])
    lower_shape = content_shape.strip().lower()

    if "compare" in lower_shape or "response" in lower_shape:
        if "two-cols" not in layouts:
            layouts.append("two-cols")
        if "table" not in patterns:
            patterns.append("table")
    if "quote" in lower_shape and "quote" not in layouts:
        layouts.append("quote")
    if "section" in lower_shape and "section" not in layouts:
        layouts.append("section")
    if "timeline" in lower_shape or "diagram" in lower_shape:
        if "mermaid" not in patterns:
            patterns.append("mermaid")
    if "grid" in lower_shape:
        for name in ("grid", "div-grid"):
            if name not in patterns:
                patterns.append(name)
    if "callout" in lower_shape and "callout" not in patterns:
        patterns.append("callout")

    return {
        "preferred_layouts": layouts,
        "preferred_patterns": patterns,
        "reason": base.get("reason") or f"{slide_role} 应优先兑现其 Slidev native pattern。",
    }


def _build_slidev_visual_hint(*, slide_role: str, content_shape: str) -> dict[str, Any]:
    base = dict(SLIDEV_NATIVE_PATTERN_GUIDE.get(slide_role, {}).get("visual_recipe") or {})
    lower_shape = content_shape.strip().lower()
    preferred_classes = [str(name).strip() for name in (base.get("preferred_classes") or []) if str(name).strip()]
    required_signals = [str(name).strip() for name in (base.get("required_signals") or []) if str(name).strip()]

    if "quote" in lower_shape and "quote-or-callout" not in required_signals:
        required_signals.append("quote-or-callout")
    if "compare" in lower_shape and "split-compare" not in required_signals:
        required_signals.append("split-compare")
    if any(token in lower_shape for token in ("diagram", "grid", "framework")) and "visual-structure" not in required_signals:
        required_signals.append("visual-structure")
    if "action" in lower_shape and "action-list" not in required_signals:
        required_signals.append("action-list")

    return {
        "name": str(base.get("name") or f"{slide_role}-visual"),
        "preferred_classes": preferred_classes,
        "required_signals": required_signals,
        "description": str(base.get("description") or f"{slide_role} should follow a stable Slidev visual recipe."),
    }


def _pattern_hint_preview(pattern_hint: Mapping[str, Any]) -> str:
    layouts = pattern_hint.get("preferred_layouts") or []
    patterns = pattern_hint.get("preferred_patterns") or []
    layout_text = ",".join(str(name) for name in layouts[:2]) or "none"
    pattern_text = ",".join(str(name) for name in patterns[:2]) or "none"
    return f"layouts={layout_text}; patterns={pattern_text}"


def _frontmatter_scalar_value(block: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", block, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _replace_or_append_frontmatter_scalar(block: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^\s*{re.escape(key)}:\s*.+?\s*$", re.MULTILINE)
    line = f"{key}: {value}"
    if pattern.search(block):
        return pattern.sub(line, block, count=1)
    return "\n".join([block.rstrip(), line]).strip()


def _merge_class_tokens(*raw_values: str) -> str:
    tokens: list[str] = []
    for raw in raw_values:
        for token in re.split(r"\s+", str(raw or "").strip()):
            if token and token not in tokens:
                tokens.append(token)
    return " ".join(tokens)


def _style_scaffold_tokens(selected_style: Mapping[str, Any] | None) -> dict[str, str]:
    style = dict(selected_style or {})
    tokens = {
        "accent": "#D92D20",
        "accent_soft": "rgba(217,45,32,0.10)",
        "surface": "rgba(255,255,255,0.92)",
        "surface_alt": "rgba(250,250,250,0.88)",
        "border": "rgba(23,23,23,0.08)",
        "text": "#171717",
        "muted": "#5F5F6B",
        "shadow": "0 18px 42px rgba(15,23,42,0.10)",
    }
    for key, value in dict(style.get("scaffold_tokens") or {}).items():
        key_text = str(key).strip()
        value_text = str(value).strip()
        if key_text and value_text:
            tokens[key_text] = value_text
    return tokens


def _shared_visual_scaffold_payload(reference_selection: Mapping[str, Any] | None) -> dict[str, Any]:
    selected_style = dict((reference_selection or {}).get("selected_style") or {})
    deck_chrome = dict((reference_selection or {}).get("deck_chrome") or {})
    if not selected_style and not deck_chrome:
        return {}
    return {
        "marker": SLIDEV_SHARED_VISUAL_SCAFFOLD_MARKER,
        "style_name": str(selected_style.get("name") or "default"),
        "root_class": str(selected_style.get("deck_scaffold_class") or "").strip(),
        "scaffold_tokens": _style_scaffold_tokens(selected_style),
        "shared_cues": [str(item) for item in (deck_chrome.get("shared_cues") or []) if str(item).strip()],
        "primitive_names": [
            str(item.get("name") or "")
            for item in (deck_chrome.get("composition_primitives") or [])
            if isinstance(item, Mapping) and str(item.get("name") or "").strip()
        ],
    }


def _render_shared_visual_scaffold_block(reference_selection: Mapping[str, Any] | None) -> str:
    scaffold = _shared_visual_scaffold_payload(reference_selection)
    if not scaffold:
        return ""
    tokens = dict(scaffold.get("scaffold_tokens") or {})
    accent = tokens["accent"]
    accent_soft = tokens["accent_soft"]
    surface = tokens["surface"]
    surface_alt = tokens["surface_alt"]
    border = tokens["border"]
    text = tokens["text"]
    muted = tokens["muted"]
    shadow = tokens["shadow"]
    return (
        "<style>\n"
        f"/* {SLIDEV_SHARED_VISUAL_SCAFFOLD_MARKER} */\n"
        ":root {\n"
        f"  --zh-slidev-accent: {accent};\n"
        f"  --zh-slidev-accent-soft: {accent_soft};\n"
        f"  --zh-slidev-surface: {surface};\n"
        f"  --zh-slidev-surface-alt: {surface_alt};\n"
        f"  --zh-slidev-border: {border};\n"
        f"  --zh-slidev-ink: {text};\n"
        f"  --zh-slidev-muted: {muted};\n"
        f"  --zh-slidev-shadow: {shadow};\n"
        "}\n"
        ".slidev-layout {\n"
        "  color: var(--zh-slidev-ink);\n"
        "}\n"
        ".slide-topline,\n"
        ".section-kicker,\n"
        ".slide-footer {\n"
        "  display: flex;\n"
        "  align-items: center;\n"
        "  gap: 0.5rem;\n"
        "  text-transform: uppercase;\n"
        "  letter-spacing: 0.18em;\n"
        "  font-size: 0.72rem;\n"
        "  color: var(--zh-slidev-muted);\n"
        "}\n"
        ".slide-topline {\n"
        "  justify-content: space-between;\n"
        "  margin-bottom: 1rem;\n"
        "}\n"
        ".section-kicker {\n"
        "  margin-bottom: 0.75rem;\n"
        "}\n"
        ".slide-subtitle {\n"
        "  margin: 0.85rem 0 1.15rem;\n"
        "  max-width: 48rem;\n"
        "  font-size: 1.05rem;\n"
        "  line-height: 1.55;\n"
        "  color: var(--zh-slidev-muted);\n"
        "}\n"
        ".slide-footer {\n"
        "  margin-top: 1.2rem;\n"
        "  padding-top: 0.75rem;\n"
        "  border-top: 1px solid var(--zh-slidev-border);\n"
        "}\n"
        ".metric-stack,\n"
        ".action-path,\n"
        ".insight-stack {\n"
        "  display: grid;\n"
        "  gap: 1rem;\n"
        "}\n"
        ".metric-grid,\n"
        ".supporting-grid {\n"
        "  display: grid;\n"
        "  grid-template-columns: repeat(2, minmax(0, 1fr));\n"
        "  gap: 0.9rem;\n"
        "}\n"
        ".metric-card,\n"
        ".compare-side,\n"
        ".action-step,\n"
        ".map-panel,\n"
        ".interpretation-card {\n"
        "  border: 1px solid var(--zh-slidev-border);\n"
        "  border-radius: 1.25rem;\n"
        "  background: linear-gradient(180deg, var(--zh-slidev-surface), var(--zh-slidev-surface-alt));\n"
        "  box-shadow: var(--zh-slidev-shadow);\n"
        "}\n"
        ".metric-card,\n"
        ".compare-side,\n"
        ".action-step,\n"
        ".interpretation-card {\n"
        "  padding: 1rem 1.15rem;\n"
        "}\n"
        ".metric-card strong,\n"
        ".verdict-line strong {\n"
        "  display: block;\n"
        "  margin-bottom: 0.35rem;\n"
        "  color: var(--zh-slidev-ink);\n"
        "  letter-spacing: -0.03em;\n"
        "}\n"
        ".metric-card--hero strong,\n"
        ".metric-stack > .metric-card strong {\n"
        "  font-size: clamp(2.3rem, 4vw, 3.8rem);\n"
        "}\n"
        ".metric-card,\n"
        ".interpretation-card,\n"
        ".compare-side,\n"
        ".action-step,\n"
        ".map-panel,\n"
        ".verdict-line {\n"
        "  line-height: 1.55;\n"
        "}\n"
        ".interpretation-card,\n"
        ".verdict-line {\n"
        "  border-left: 4px solid var(--zh-slidev-accent);\n"
        "}\n"
        ".interpretation-card,\n"
        ".verdict-line {\n"
        "  padding: 0.95rem 1.1rem;\n"
        "}\n"
        ".verdict-line {\n"
        "  margin-top: 1rem;\n"
        "  border-radius: 1rem;\n"
        "  background: var(--zh-slidev-accent-soft);\n"
        "}\n"
        ".map-with-insights {\n"
        "  display: grid;\n"
        "  grid-template-columns: minmax(0, 1.15fr) minmax(16rem, 0.85fr);\n"
        "  gap: 1rem;\n"
        "  align-items: start;\n"
        "}\n"
        ".map-panel {\n"
        "  min-height: 16rem;\n"
        "  padding: 1.1rem 1.2rem;\n"
        "}\n"
        ".map-panel table {\n"
        "  width: 100%;\n"
        "  border-collapse: collapse;\n"
        "  font-size: 0.92rem;\n"
        "}\n"
        ".map-panel th,\n"
        ".map-panel td {\n"
        "  padding: 0.5rem 0.35rem;\n"
        "  border-bottom: 1px solid var(--zh-slidev-border);\n"
        "  text-align: left;\n"
        "}\n"
        ".map-panel blockquote,\n"
        ".map-panel p {\n"
        "  margin-top: 0.75rem;\n"
        "}\n"
        ".insight-card {\n"
        "  position: relative;\n"
        "}\n"
        ".compare-panel {\n"
        "  gap: 1rem;\n"
        "}\n"
        ".compare-panel .compare-side {\n"
        "  min-height: 11rem;\n"
        "}\n"
        ".action-step {\n"
        "  display: block;\n"
        "}\n"
        ".deck-cover h1,\n"
        ".deck-cover h2 {\n"
        "  max-width: 12ch;\n"
        "  letter-spacing: -0.04em;\n"
        "}\n"
        ".deck-cover .slide-subtitle {\n"
        "  max-width: 42rem;\n"
        "}\n"
        ".deck-context,\n"
        ".deck-framework,\n"
        ".deck-comparison,\n"
        ".deck-recommendation,\n"
        ".deck-closing {\n"
        "  padding-top: 0.35rem;\n"
        "}\n"
        "@media (max-width: 900px) {\n"
        "  .map-with-insights,\n"
        "  .metric-grid,\n"
        "  .supporting-grid {\n"
        "    grid-template-columns: 1fr;\n"
        "  }\n"
        "}\n"
        "</style>"
    )


def _apply_shared_visual_scaffold(
    *,
    markdown: str,
    reference_selection: Mapping[str, Any] | None,
) -> str:
    text = str(markdown or "").strip()
    if not text or SLIDEV_SHARED_VISUAL_SCAFFOLD_MARKER in text:
        return text
    style_block = _render_shared_visual_scaffold_block(reference_selection)
    if not style_block:
        return text
    match = re.match(r"^(---\s*\n.*?\n---\s*\n?)(.*)$", text, re.DOTALL)
    if not match:
        return f"{style_block}\n\n{text}".strip()
    frontmatter = match.group(1).rstrip()
    body = match.group(2).lstrip()
    slide_match = re.match(r"^(---\s*\n(.*?)\n---\s*\n?)(.*)$", body, re.DOTALL)
    if slide_match and _looks_like_slide_frontmatter(slide_match.group(2).splitlines()):
        first_slide_frontmatter = slide_match.group(1).rstrip()
        first_slide_body = slide_match.group(3).lstrip()
        rebuilt_body = f"{first_slide_frontmatter}\n\n{style_block}\n\n{first_slide_body}".strip()
        return f"{frontmatter}\n\n{rebuilt_body}".strip()
    return f"{frontmatter}\n\n{style_block}\n\n{body}".strip()


def _style_frontmatter_block(*, title: str, reference_selection: Mapping[str, Any] | None) -> str:
    selected_theme = _selected_theme_payload(reference_selection)
    selected_style = dict((reference_selection or {}).get("selected_style") or {})
    lines = [
        f"theme: {selected_theme.get('theme') or 'seriph'}",
        f"title: {title}",
    ]
    deck_scaffold_class = str(selected_style.get("deck_scaffold_class") or "").strip()
    if deck_scaffold_class:
        lines.append(f"class: {deck_scaffold_class}")
    theme_config = selected_theme.get("theme_config") or selected_style.get("theme_config") or {}
    if isinstance(theme_config, Mapping) and theme_config:
        lines.append(f"themeConfig: {json.dumps(theme_config, ensure_ascii=False)}")
    return "\n".join(lines).strip()


def _apply_style_frontmatter_baseline(
    *,
    markdown: str,
    title: str,
    reference_selection: Mapping[str, Any] | None,
) -> str:
    text = str(markdown or "").strip()
    base_block = _style_frontmatter_block(title=title, reference_selection=reference_selection)
    selected_style = dict((reference_selection or {}).get("selected_style") or {})
    base_class = str(selected_style.get("deck_scaffold_class") or "").strip()

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if match:
        existing_block = match.group(1).strip()
        body = match.group(2).strip()
        existing_class = _frontmatter_scalar_value(existing_block, "class")
        merged_block = _merge_frontmatter_blocks(existing_block, base_block)
        if base_class:
            merged_class = _merge_class_tokens(
                base_class,
                existing_class,
                _frontmatter_scalar_value(merged_block, "class"),
            )
            merged_block = _replace_or_append_frontmatter_scalar(merged_block, "class", merged_class)
    else:
        merged_block = base_block
        body = text

    if not body:
        normalized = f"---\n{merged_block}\n---\n"
    else:
        normalized = f"---\n{merged_block}\n---\n\n{body.rstrip()}\n"
    return _apply_shared_visual_scaffold(markdown=normalized, reference_selection=reference_selection) + "\n"


def _selected_theme_payload(reference_selection: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(reference_selection, Mapping):
        return {
            "theme": "seriph",
            "theme_reason": "Use the official seriph theme as the default Slidev baseline.",
            "theme_mode": "official-theme-plus-light-overrides",
            "theme_config": {},
        }
    payload = dict(reference_selection.get("selected_theme") or {})
    if not payload:
        style = dict(reference_selection.get("selected_style") or {})
        payload = {
            "theme": str(style.get("theme") or "seriph"),
            "theme_reason": str(
                style.get("theme_reason")
                or "Use the official seriph theme as the default Slidev baseline."
            ),
            "theme_mode": str(style.get("theme_mode") or "official-theme-plus-light-overrides"),
            "theme_config": dict(style.get("theme_config") or {}),
        }
    payload["theme"] = str(payload.get("theme") or "seriph")
    payload["theme_reason"] = str(
        payload.get("theme_reason") or "Use the official seriph theme as the default Slidev baseline."
    )
    payload["theme_mode"] = str(payload.get("theme_mode") or "official-theme-plus-light-overrides")
    payload["theme_config"] = dict(payload.get("theme_config") or {})
    return payload


@lru_cache(maxsize=None)
def _load_slidev_reference_collection(reference_root: str, group: str) -> tuple[dict[str, Any], ...]:
    directory = Path(reference_root) / group
    payloads: list[dict[str, Any]] = []
    if not directory.exists():
        return tuple()
    for json_path in sorted(directory.glob("*.json")):
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            payload = dict(raw)
            payload["source_path"] = str(json_path)
            payloads.append(payload)
    return tuple(payloads)


def _load_slidev_reference_assets() -> dict[str, list[dict[str, Any]]]:
    reference_root = settings.skills_dir / "slidev-design-system" / "references"
    return {
        "styles": [dict(item) for item in _load_slidev_reference_collection(str(reference_root), "styles")],
        "layouts": [dict(item) for item in _load_slidev_reference_collection(str(reference_root), "layouts")],
        "blocks": [dict(item) for item in _load_slidev_reference_collection(str(reference_root), "blocks")],
    }


def _reference_string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in (value or []) if str(item).strip()]


def _score_style_reference(style: Mapping[str, Any], *, topic: str, material_excerpt: str, num_pages: int) -> tuple[int, int]:
    haystack = f"{topic} {material_excerpt}".lower()
    matched = [signal for signal in _reference_string_list(style.get("selection_signals")) if signal.lower() in haystack]
    tie_break = 1 if num_pages >= 10 and str(style.get("name") or "") in {"tech-launch", "structured-insight"} else 0
    return (len(matched), tie_break)


def _select_style_reference(*, styles: Sequence[Mapping[str, Any]], topic: str, material_excerpt: str, num_pages: int) -> dict[str, Any]:
    ranked: list[tuple[tuple[int, int], dict[str, Any]]] = []
    for style in styles:
        score = _score_style_reference(style, topic=topic, material_excerpt=material_excerpt, num_pages=num_pages)
        ranked.append((score, dict(style)))
    ranked.sort(key=lambda item: (item[0][0], item[0][1], str(item[1].get("name") or "")), reverse=True)
    selected = dict(ranked[0][1]) if ranked else {
        "name": "tech-launch",
        "theme": "seriph",
        "tone": "tech-product-launch",
        "selection_signals": [],
        "required_classes": [],
        "anti_patterns": ["plain-bullet-dump", "unstyled-document-section"],
        "theme_reason": "Use the official seriph theme as the default Slidev baseline.",
        "theme_mode": "official-theme-plus-light-overrides",
        "description": "Fallback style when no static references are available.",
        "deck_scaffold_class": "theme-tech-launch",
        "theme_config": {"palette": "tech-launch", "density": "presentation", "emphasis": "launch-contrast"},
        "scaffold_tokens": {
            "accent": "#D92D20",
            "accent_soft": "rgba(217,45,32,0.10)",
            "surface": "rgba(255,255,255,0.92)",
            "surface_alt": "rgba(250,250,250,0.88)",
            "border": "rgba(23,23,23,0.08)",
            "text": "#171717",
            "muted": "#5F5F6B",
            "shadow": "0 18px 42px rgba(15,23,42,0.10)",
        },
        "baseline_constraints": [
            "cover should feel like a launch slide, not a report heading",
            "comparison and closing slides need a visible verdict or takeaway line",
        ],
    }
    haystack = f"{topic} {material_excerpt}".lower()
    matched_signals = [signal for signal in _reference_string_list(selected.get("selection_signals")) if signal.lower() in haystack]
    selected["required_classes"] = _reference_string_list(selected.get("required_classes"))
    selected["anti_patterns"] = _reference_string_list(selected.get("anti_patterns"))
    selected["selection_signals"] = _reference_string_list(selected.get("selection_signals"))
    selected["theme"] = str(selected.get("theme") or "seriph")
    selected["tone"] = str(selected.get("tone") or "structured-slidev")
    selected["theme_reason"] = str(
        selected.get("theme_reason") or "Use the official seriph theme as the default Slidev baseline."
    )
    selected["theme_mode"] = str(selected.get("theme_mode") or "official-theme-plus-light-overrides")
    selected["deck_scaffold_class"] = str(selected.get("deck_scaffold_class") or "").strip()
    selected["theme_config"] = dict(selected.get("theme_config") or {})
    selected["scaffold_tokens"] = {
        str(key): str(value)
        for key, value in dict(selected.get("scaffold_tokens") or {}).items()
        if str(key).strip() and str(value).strip()
    }
    selected["baseline_constraints"] = _reference_string_list(selected.get("baseline_constraints"))
    selected["matched_signals"] = matched_signals
    selected["selection_reason"] = (
        f"Selected style `{selected.get('name')}` because it best matches topic/material signals "
        f"{matched_signals or ['fallback-baseline']} while keeping a deterministic Slidev baseline."
    )
    return selected


def _select_layout_reference(*, item: Mapping[str, Any], layouts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    slide_number = int(item.get("slide_number") or 0)
    title = str(item.get("title") or f"Slide {slide_number}")
    role = str(item.get("slide_role") or "").strip().lower()
    content_shape = str(item.get("content_shape") or "").strip().lower()
    pattern_hint = _build_slidev_pattern_hint(slide_role=role, content_shape=content_shape)
    visual_hint = _build_slidev_visual_hint(slide_role=role, content_shape=content_shape)
    candidates = [dict(layout) for layout in layouts if role in _reference_string_list(layout.get("applies_to_roles"))]
    selected = candidates[0] if candidates else {
        "name": str(visual_hint.get("name") or role or "default"),
        "preferred_layout": None,
        "required_patterns": list(pattern_hint.get("preferred_patterns") or []),
        "required_classes": list(visual_hint.get("preferred_classes") or []),
        "forbidden_patterns": ["plain-bullet-dump", "unstyled-document-section"],
        "description": str(visual_hint.get("description") or "Fallback layout reference."),
        "required_visual_signals": list(visual_hint.get("required_signals") or []),
    }
    selected["required_patterns"] = _reference_string_list(selected.get("required_patterns"))
    selected["required_classes"] = _reference_string_list(selected.get("required_classes"))
    selected["forbidden_patterns"] = _reference_string_list(selected.get("forbidden_patterns"))
    selected["required_visual_signals"] = _reference_string_list(selected.get("required_visual_signals")) or _reference_string_list(visual_hint.get("required_signals"))
    preferred_layout = str(selected.get("preferred_layout") or "").strip() or _preferred_layout_for_hint(pattern_hint)
    matched_shape_signals = [
        signal
        for signal in selected["required_patterns"] + selected["required_visual_signals"]
        if signal.lower().replace("_", "-") in content_shape
    ]
    return {
        "slide_number": slide_number,
        "title": title,
        "slide_role": role,
        "recipe_name": str(selected.get("name") or role or "default"),
        "layout": preferred_layout or None,
        "preferred_layout": preferred_layout or None,
        "container_classes": " ".join(selected["required_classes"]),
        "content_classes": "",
        "required_patterns": list(selected["required_patterns"]),
        "required_visual_signals": list(selected["required_visual_signals"]),
        "required_classes": list(selected["required_classes"]),
        "anti_patterns": _reference_string_list(selected.get("anti_patterns")),
        "forbidden_patterns": list(selected["forbidden_patterns"]),
        "description": str(selected.get("description") or ""),
        "matched_shape_signals": matched_shape_signals,
        "selection_reason": (
            f"Use layout recipe `{selected.get('name')}` for role `{role or 'unknown'}` because it matches "
            f"required patterns {selected['required_patterns']} and visual signals {selected['required_visual_signals']}."
        ),
    }


def _preferred_layout_for_hint(pattern_hint: Mapping[str, Any]) -> str | None:
    layouts = [str(name).strip() for name in (pattern_hint.get("preferred_layouts") or []) if str(name).strip()]
    return layouts[0] if layouts else None


def _select_block_references(*, item: Mapping[str, Any], blocks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    slide_number = int(item.get("slide_number") or 0)
    title = str(item.get("title") or f"Slide {slide_number}")
    role = str(item.get("slide_role") or "").strip().lower()
    content_shape = str(item.get("content_shape") or "").strip().lower()
    applicable = [dict(block) for block in blocks if role in _reference_string_list(block.get("applies_to_roles"))]
    preferred_order = {
        "cover": ["hero-title"],
        "context": ["compact-bullets", "quote-callout"],
        "framework": ["framework-explainer"],
        "detail": ["compact-bullets", "quote-callout"],
        "comparison": ["compare-split"],
        "recommendation": ["takeaway-next-steps", "compact-bullets"],
        "closing": ["takeaway-next-steps"],
    }.get(role, ["compact-bullets"])
    order_map = {name: index for index, name in enumerate(preferred_order)}
    applicable.sort(key=lambda block: (order_map.get(str(block.get("name") or ""), 99), str(block.get("name") or "")))
    if role in {"context", "detail", "recommendation"}:
        selected = applicable[:2]
    else:
        selected = applicable[:1]
    if not selected:
        selected = [
            {
                "name": "compact-bullets",
                "recommended_structure": "2-4 compact bullets with one framing line",
                "required_signals": ["compact-bullets"],
                "visual_constraints": ["max 4 bullets"],
                "anti_patterns": ["unstyled-document-section"],
            }
        ]
    normalized_blocks: list[dict[str, Any]] = []
    for block in selected:
        payload = dict(block)
        payload["required_signals"] = _reference_string_list(payload.get("required_signals"))
        payload["visual_constraints"] = _reference_string_list(payload.get("visual_constraints"))
        payload["anti_patterns"] = _reference_string_list(payload.get("anti_patterns"))
        payload["selection_reason"] = (
            f"Use block `{payload.get('name')}` for role `{role or 'unknown'}` to realize structure `{payload.get('recommended_structure')}`."
        )
        payload["matched_shape_signals"] = [
            signal for signal in payload["required_signals"] if signal.lower().replace("_", "-") in content_shape
        ]
        normalized_blocks.append(payload)
    return {
        "slide_number": slide_number,
        "title": title,
        "slide_role": role,
        "blocks": normalized_blocks,
    }


def _synthesize_slidev_page_briefs(
    *,
    outline_items: Sequence[Mapping[str, Any]],
    topic: str,
    material_excerpt: str,
    selected_layouts: Sequence[Mapping[str, Any]],
    selected_blocks: Sequence[Mapping[str, Any]],
    selected_style: Mapping[str, Any],
) -> list[dict[str, Any]]:
    layout_map = {
        int(item.get("slide_number") or 0): dict(item)
        for item in selected_layouts
        if isinstance(item, Mapping)
    }
    block_map = {
        int(item.get("slide_number") or 0): [dict(block) for block in (item.get("blocks") or []) if isinstance(block, Mapping)]
        for item in selected_blocks
        if isinstance(item, Mapping)
    }
    thesis = _slidev_deck_thesis(topic=topic, material_excerpt=material_excerpt)
    briefs: list[dict[str, Any]] = []
    for item in outline_items:
        if not isinstance(item, Mapping):
            continue
        slide_number = int(item.get("slide_number") or 0)
        title = str(item.get("title") or f"Slide {slide_number}").strip()
        role = str(item.get("slide_role") or "").strip().lower()
        goal = str(item.get("goal") or "").strip()
        layout = layout_map.get(slide_number, {})
        blocks = block_map.get(slide_number, [])
        preferred_composition = _page_brief_composition(
            item=item,
            topic=topic,
            material_excerpt=material_excerpt,
        )
        brief = {
            "slide_number": slide_number,
            "title": title,
            "slide_role": role,
            "page_goal": goal or _default_page_goal(role),
            "narrative_job": _default_narrative_job(role),
            "hero_fact_or_claim": _page_brief_claim(
                title=title,
                goal=goal,
                role=role,
                thesis=thesis,
            ),
            "supporting_points": _page_brief_supporting_points(
                title=title,
                role=role,
                preferred_composition=preferred_composition,
                blocks=blocks,
            ),
            "preferred_composition": preferred_composition,
            "must_keep": _page_brief_must_keep(role=role, preferred_composition=preferred_composition),
            "must_avoid": _page_brief_must_avoid(role=role, preferred_composition=preferred_composition),
            "must_keep_signals": _page_brief_keep_signals(role=role, preferred_composition=preferred_composition),
            "must_avoid_patterns": _page_brief_avoid_patterns(role=role, preferred_composition=preferred_composition),
            "layout_recipe": str(layout.get("recipe_name") or ""),
            "layout": str(layout.get("layout") or ""),
            "block_recipes": [str(block.get("name") or "") for block in blocks if isinstance(block, Mapping)],
            "style_name": str(selected_style.get("name") or ""),
        }
        briefs.append(brief)
    return briefs


def _slidev_deck_thesis(*, topic: str, material_excerpt: str) -> str:
    topic_text = str(topic or "").strip()
    material_text = str(material_excerpt or "").strip()
    if not topic_text and not material_text:
        return "这份 deck 需要把变化趋势转成清晰的判断与行动。"
    if any(token in f"{topic_text} {material_text}".lower() for token in ("future of work", "future work", "work", "job")) or any(
        token in f"{topic_text}{material_text}" for token in ("未来工作", "工作", "就业", "岗位")
    ):
        return "AI 对未来工作的影响已经进入现实决策窗口，需要用结构化页面说明 urgency、exposure 与 action path。"
    return f"{topic_text or material_text[:48]} 需要被收口成一条清晰 thesis，而不是松散的信息堆叠。"


def _default_page_goal(role: str) -> str:
    return {
        "cover": "建立主题定位并给出开场 framing",
        "context": "解释为什么这件事现在值得关注",
        "framework": "给出可复用的结构模型",
        "detail": "用一页支撑一个关键判断",
        "comparison": "把两种路径或状态清晰对照",
        "recommendation": "把判断收口成行动建议",
        "closing": "用一句结论和下一步完成收束",
    }.get(role, "让这一页承担单一叙事任务")


def _default_narrative_job(role: str) -> str:
    return {
        "cover": "set the narrative frame",
        "context": "establish urgency",
        "framework": "provide the mental model",
        "detail": "support one argument with evidence",
        "comparison": "show contrast and trade-offs",
        "recommendation": "turn analysis into actions",
        "closing": "land the takeaway and next move",
    }.get(role, "move the deck forward with one clear claim")


def _page_brief_composition(
    *,
    item: Mapping[str, Any],
    topic: str,
    material_excerpt: str,
) -> str:
    role = str(item.get("slide_role") or "").strip().lower()
    title = str(item.get("title") or "").strip().lower()
    goal = str(item.get("goal") or "").strip().lower()
    content_shape = str(item.get("content_shape") or "").strip().lower()
    haystack = " ".join(part for part in (title, goal, content_shape, str(topic or "").lower(), str(material_excerpt or "").lower()) if part)
    urgency_tokens = ("why now", "why-now", "now", "urgency", "trend", "signal", "采用", "现在", "背景", "紧迫", "变化")
    map_tokens = (
        "map",
        "risk",
        "exposure",
        "landscape",
        "matrix",
        "quadrant",
        "axis",
        "task",
        "风险",
        "暴露",
        "象限",
        "地图",
        "版图",
        "岗位",
        "职业",
        "工作",
        "role",
        "roles",
        "job",
        "jobs",
        "which",
        "哪些",
    )
    if role == "cover":
        return "cover-hero"
    if role == "comparison":
        return "compare-panel"
    if role in {"recommendation", "closing"}:
        return "action-path"
    if role == "context":
        return "metric-stack" if any(token in haystack for token in urgency_tokens) or int(item.get("slide_number") or 0) <= 2 else "metric-stack"
    if role in {"framework", "detail", "context"} and any(token in haystack for token in map_tokens):
        return "map-with-insights"
    if role == "framework":
        return "map-with-insights"
    return "metric-stack"


def _page_brief_claim(*, title: str, goal: str, role: str, thesis: str) -> str:
    if role == "cover":
        return title
    if role == "context":
        return f"{title} 不是远期趋势，而是已经影响组织与个人决策的现实变化。"
    if role in {"framework", "detail"}:
        return f"{title} 需要被解释成一个可读的结构，而不是散乱结论。"
    if role == "comparison":
        return f"{title} 必须让观众一眼看出两侧差异与最终判断。"
    if role in {"recommendation", "closing"}:
        return f"{title} 应把分析转成明确 takeaway 与下一步。"
    return goal or thesis


def _page_brief_supporting_points(
    *,
    title: str,
    role: str,
    preferred_composition: str,
    blocks: Sequence[Mapping[str, Any]],
) -> list[str]:
    block_names = [str(block.get("name") or "") for block in blocks if isinstance(block, Mapping)]
    defaults = {
        "metric-stack": [
            "1 个 hero fact 或 headline metric",
            "2-3 个 supporting cards / data cues",
            "1 句 interpretation / why it matters",
        ],
        "map-with-insights": [
            "左侧 map / quadrant / table / mermaid",
            "右侧 2-3 个 insight cards",
            "1 句 takeaway / source line",
        ],
        "compare-panel": [
            "左右标签必须显式出现",
            "每侧 2-4 条对照点",
            "1 句 verdict / takeaway",
        ],
        "action-path": [
            "1 句 headline / recommendation",
            "2-4 条 next steps / actions",
            "1 句 closing or priority cue",
        ],
        "cover-hero": [
            "1 条短 kicker",
            "1 个 hero title",
            "1 条短 subtitle",
        ],
    }
    points = list(defaults.get(preferred_composition, []))
    if role == "framework" and "framework-explainer" in block_names and "1 个结构化模型" not in points:
        points.insert(0, "1 个结构化模型 / diagram")
    if title and points:
        points[0] = points[0].replace("1 个", f"{title} 这页要先落成 1 个", 1) if points[0].startswith("1 个") else points[0]
    return points[:4]


def _page_brief_must_keep(*, role: str, preferred_composition: str) -> list[str]:
    by_composition = {
        "cover-hero": ["短 kicker", "hero title", "短 subtitle"],
        "metric-stack": ["hero fact / claim", "2-3 supporting cards", "interpretation line"],
        "map-with-insights": ["map or quadrant panel", "2-3 insight cards", "takeaway or source line"],
        "compare-panel": ["paired labels", "left/right contrast", "verdict line"],
        "action-path": ["takeaway headline", "2-4 next steps", "closing cue"],
    }
    keep = list(by_composition.get(preferred_composition, []))
    if role == "framework" and "takeaway or source line" not in keep:
        keep.append("modeled takeaway")
    return keep


def _page_brief_must_avoid(*, role: str, preferred_composition: str) -> list[str]:
    by_composition = {
        "cover-hero": ["文档式封面", "长段说明"],
        "metric-stack": ["标题 + 大段 bullets", "只有抽象判断没有数据 cue"],
        "map-with-insights": ["纯 bullets", "没有左右分工的平铺结构"],
        "compare-panel": ["未标注左右", "没有 verdict 的对照页"],
        "action-path": ["普通 bullet dump", "谢谢/Q&A 结尾"],
    }
    avoid = list(by_composition.get(preferred_composition, []))
    if role == "closing" and "谢谢/Q&A 结尾" not in avoid:
        avoid.append("谢谢/Q&A 结尾")
    return avoid


def _page_brief_keep_signals(*, role: str, preferred_composition: str) -> list[str]:
    mapping = {
        "cover-hero": ["launch-kicker", "hero-title", "short-subtitle"],
        "metric-stack": ["metric-stack", "hero-metric", "interpretation-line"],
        "map-with-insights": ["map-with-insights", "visual-structure", "insight-card", "source-or-takeaway"],
        "compare-panel": ["compare-panel", "split-compare", "contrast-labels", "verdict-line"],
        "action-path": ["action-path", "next-step-or-takeaway", "action-list"],
    }
    keep = list(mapping.get(preferred_composition, []))
    if role == "closing" and "closing-line" not in keep:
        keep.append("closing-line")
    return keep


def _page_brief_avoid_patterns(*, role: str, preferred_composition: str) -> list[str]:
    patterns = {
        "metric-stack": ["plain-bullet-dump", "unstyled-document-section"],
        "map-with-insights": ["plain-bullet-dump", "unstyled-document-section"],
        "compare-panel": ["unlabeled-compare", "unstyled-document-section"],
        "action-path": ["plain-bullet-dump", "generic-thanks"],
        "cover-hero": ["unstyled-document-section", "long-paragraph-cover"],
    }
    result = list(patterns.get(preferred_composition, []))
    if role == "closing" and "generic-thanks" not in result:
        result.append("generic-thanks")
    return result


def _build_slidev_deck_chrome(
    *,
    topic: str,
    num_pages: int,
    selected_style: Mapping[str, Any],
    page_briefs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    deck_label = _slidev_deck_label(topic)
    scaffold_tokens = _style_scaffold_tokens(selected_style)
    return {
        "deck_label": deck_label,
        "style_name": str(selected_style.get("name") or ""),
        "page_number_format": "two-digit" if num_pages >= 10 else "compact",
        "topline_classes": ["slide-topline", "uppercase", "tracking-[0.18em]", "text-xs", "opacity-70"],
        "kicker_classes": ["section-kicker", "uppercase", "tracking-[0.18em]", "text-xs", "opacity-70"],
        "subtitle_classes": ["slide-subtitle", "text-lg", "opacity-80"],
        "footer_classes": ["slide-footer", "text-xs", "opacity-65"],
        "shared_cues": [
            "slide-topline",
            "section-kicker",
            "slide-subtitle",
            "slide-footer",
            "metric-card",
            "interpretation-card",
            "map-panel",
            "compare-side",
            "action-step",
        ],
        "composition_primitives": [
            {
                "name": "hero-cover",
                "required_classes": ["deck-cover", "slide-topline", "slide-subtitle"],
                "description": "launch-style cover with a topline cue, hero title, and a short subtitle",
            },
            {
                "name": "metric-stack",
                "required_classes": ["metric-stack", "metric-card", "interpretation-card"],
                "description": "hero metric or claim plus 2-3 supporting cards and one interpretation line",
            },
            {
                "name": "map-with-insights",
                "required_classes": ["map-with-insights", "map-panel", "insight-card"],
                "description": "left map or matrix plus right-side insight cards and a takeaway/source line",
            },
            {
                "name": "compare-panel",
                "required_classes": ["compare-panel", "compare-side", "verdict-line"],
                "description": "paired contrast with explicit side labels and one verdict line",
            },
            {
                "name": "action-path",
                "required_classes": ["action-path", "action-step", "verdict-line"],
                "description": "takeaway headline plus 2-4 steps or next actions",
            },
        ],
        "chrome_rules": [
            "non-cover slides should usually expose either a slide-topline or section-kicker",
            "metric/map/compare/action compositions should use semantic classes instead of ad-hoc inline style",
            "footer or source line should appear on research-heavy or closing slides",
        ],
        "shared_visual_scaffold": {
            "marker": SLIDEV_SHARED_VISUAL_SCAFFOLD_MARKER,
            "root_class": str(selected_style.get("deck_scaffold_class") or "").strip(),
            "scaffold_tokens": scaffold_tokens,
            "primitive_names": ["hero-cover", "metric-stack", "map-with-insights", "compare-panel", "action-path"],
        },
        "briefed_slide_count": len(page_briefs),
    }


def _slidev_deck_label(topic: str) -> str:
    text = str(topic or "").strip()
    lowered = text.lower()
    if any(token in lowered for token in ("ai", "artificial intelligence")) or "人工智能" in text:
        if any(token in lowered for token in ("future work", "future of work", "work")) or any(
            token in text for token in ("未来工作", "工作")
        ):
            return "AI x Future Work"
        return "AI Brief"
    return text[:32] or "Deck Brief"


def _slide_role_container_class(*, brief: Mapping[str, Any], layout: Mapping[str, Any]) -> str:
    explicit = str(layout.get("container_classes") or "").strip()
    if explicit:
        return explicit
    role = str(brief.get("slide_role") or "").strip().lower()
    return {
        "cover": "deck-cover",
        "context": "deck-context",
        "framework": "deck-framework",
        "detail": "deck-context",
        "comparison": "deck-comparison",
        "recommendation": "deck-recommendation",
        "closing": "deck-closing",
    }.get(role, "deck-context")


def _page_brief_scaffold_lines(
    *,
    brief: Mapping[str, Any],
    layout: Mapping[str, Any],
    deck_chrome: Mapping[str, Any],
) -> list[str]:
    composition = str(brief.get("preferred_composition") or "").strip()
    title = str(brief.get("title") or "Slide").strip()
    deck_label = str(deck_chrome.get("deck_label") or "Deck").strip()
    container_class = _slide_role_container_class(brief=brief, layout=layout)
    lines = [
        f"  deck chrome cue: add a lightweight `<div class=\"slide-topline\">{deck_label} / {brief.get('slide_number') or ''}</div>` or equivalent section kicker when the page is not cover-only.",
    ]
    if composition == "cover-hero":
        lines.extend(
            [
                "  canonical hero-cover shell:",
                "  ---",
                f"  layout: {layout.get('layout') or 'cover'}",
                f"  class: {container_class}",
                "  ---",
                f"  <div class=\"slide-topline\">{deck_label}</div>",
                "  <div class=\"section-kicker\">launch framing / short cue</div>",
                f"  # {title}",
                "  <div class=\"slide-subtitle\">一句短 subtitle / positioning line</div>",
            ]
        )
    elif composition == "metric-stack":
        lines.extend(
            [
                "  canonical metric-stack shell:",
                "  ---",
                f"  class: {container_class}",
                "  ---",
                f"  <div class=\"slide-topline\">{deck_label} / why now</div>",
                "  <div class=\"section-kicker\">why now / urgency cue</div>",
                f"  ## {title}",
                "  <div class=\"slide-subtitle\">一句 why-now / urgency 判断</div>",
                "  <div class=\"metric-stack\">",
                "    <div class=\"metric-card metric-card--hero\"><strong>主数字 / 主判断</strong><div>一句解释</div></div>",
                "    <div class=\"metric-grid\">",
                "      <div class=\"metric-card\">supporting card</div>",
                "      <div class=\"metric-card\">supporting card</div>",
                "    </div>",
                "    <div class=\"interpretation-card\">Interpretation / why it matters</div>",
                "  </div>",
            ]
        )
    elif composition == "map-with-insights":
        lines.extend(
            [
                "  canonical map-with-insights shell:",
                "  ---",
                f"  class: {container_class}",
                "  ---",
                f"  <div class=\"slide-topline\">{deck_label} / exposure map</div>",
                f"  ## {title}",
                "  <div class=\"section-kicker\">左侧 map / 右侧 insights</div>",
                "  <div class=\"map-with-insights\">",
                "    <div class=\"map-panel\">用 quadrant / table / mermaid / matrix 呈现暴露或风险地图</div>",
                "    <div class=\"insight-stack\">",
                "      <div class=\"metric-card insight-card\">headline fact</div>",
                "      <div class=\"metric-card insight-card\">insight</div>",
                "      <div class=\"interpretation-card\">takeaway / source</div>",
                "    </div>",
                "  </div>",
            ]
        )
    elif composition == "compare-panel":
        lines.extend(
            [
                "  canonical compare-panel shell:",
                "  ---",
                f"  layout: {layout.get('layout') or 'two-cols'}",
                f"  class: {(layout.get('container_classes') or 'deck-comparison').strip()} compare-panel",
                "  ---",
                f"  ## {title}",
                "  ::left::",
                "  <div class=\"compare-side\">左侧标签 + 2-4 条要点</div>",
                "  ::right::",
                "  <div class=\"compare-side\">右侧标签 + 2-4 条要点</div>",
                "  <div class=\"verdict-line\">一句 verdict / takeaway</div>",
            ]
        )
    elif composition == "action-path":
        lines.extend(
            [
                "  canonical action-path shell:",
                "  ---",
                f"  class: {container_class}",
                "  ---",
                f"  <div class=\"slide-topline\">{deck_label} / next move</div>",
                f"  ## {title}",
                "  <div class=\"verdict-line\">一句结论 headline / recommendation</div>",
                "  <div class=\"action-path\">",
                "    <div class=\"action-step\">1. action</div>",
                "    <div class=\"action-step\">2. action</div>",
                "    <div class=\"action-step\">3. action</div>",
                "  </div>",
                "  <div class=\"slide-footer\">priority / owner / source</div>",
            ]
        )
    return lines


def _select_slidev_references(
    *,
    outline_items: Sequence[Mapping[str, Any]],
    topic: str,
    num_pages: int,
    material_excerpt: str,
) -> dict[str, Any]:
    assets = _load_slidev_reference_assets()
    selected_style = _select_style_reference(
        styles=assets.get("styles") or [],
        topic=topic,
        material_excerpt=material_excerpt,
        num_pages=num_pages,
    )
    selected_theme = _selected_theme_payload({"selected_style": selected_style})
    selected_layouts: list[dict[str, Any]] = []
    selected_blocks: list[dict[str, Any]] = []
    for item in outline_items:
        if not isinstance(item, Mapping):
            continue
        selected_layouts.append(_select_layout_reference(item=item, layouts=assets.get("layouts") or []))
        selected_blocks.append(_select_block_references(item=item, blocks=assets.get("blocks") or []))
    page_briefs = _synthesize_slidev_page_briefs(
        outline_items=outline_items,
        topic=topic,
        material_excerpt=material_excerpt,
        selected_layouts=selected_layouts,
        selected_blocks=selected_blocks,
        selected_style=selected_style,
    )
    deck_chrome = _build_slidev_deck_chrome(
        topic=topic,
        num_pages=num_pages,
        selected_style=selected_style,
        page_briefs=page_briefs,
    )

    return {
        "selected_style": selected_style,
        "selected_theme": selected_theme,
        "selected_layouts": selected_layouts,
        "selected_blocks": selected_blocks,
        "page_briefs": page_briefs,
        "deck_chrome": deck_chrome,
        "selection_summary": {
            "style_name": selected_style["name"],
            "style_reason": selected_style["selection_reason"],
            "style_match_signals": list(selected_style.get("matched_signals") or []),
            "selected_theme": selected_theme["theme"],
            "theme_reason": selected_theme["theme_reason"],
            "deck_scaffold_class": str(selected_style.get("deck_scaffold_class") or ""),
            "theme_config": dict(selected_theme.get("theme_config") or {}),
            "baseline_constraints": list(selected_style.get("baseline_constraints") or []),
            "selected_layout_names": [item.get("recipe_name") for item in selected_layouts],
            "selected_block_names": [
                block.get("name")
                for item in selected_blocks
                for block in (item.get("blocks") or [])
                if isinstance(block, Mapping)
            ],
            "page_brief_compositions": [
                {
                    "slide_number": int(brief.get("slide_number") or 0),
                    "slide_role": str(brief.get("slide_role") or ""),
                    "preferred_composition": str(brief.get("preferred_composition") or ""),
                }
                for brief in page_briefs
                if isinstance(brief, Mapping)
            ],
            "deck_chrome_label": str(deck_chrome.get("deck_label") or ""),
            "shared_visual_scaffold_marker": str(
                ((deck_chrome.get("shared_visual_scaffold") or {}).get("marker") or "")
            ),
            "deck_chrome_primitives": [
                str(item.get("name") or "")
                for item in (deck_chrome.get("composition_primitives") or [])
                if isinstance(item, Mapping)
            ],
            "slide_recipes": [
                {
                    "slide_number": int(layout.get("slide_number") or 0),
                    "slide_role": str(layout.get("slide_role") or ""),
                    "layout_recipe": str(layout.get("recipe_name") or ""),
                    "layout_reason": str(layout.get("selection_reason") or ""),
                    "block_recipes": [
                        str(block.get("name") or "")
                        for block in ((selected_blocks[index].get("blocks") or []) if index < len(selected_blocks) else [])
                        if isinstance(block, Mapping)
                    ],
                }
                for index, layout in enumerate(selected_layouts)
            ],
            "material_excerpt_used": bool(material_excerpt.strip()),
            "num_pages": num_pages,
            "reference_root": str(settings.skills_dir / "slidev-design-system" / "references"),
        },
    }


def _block_recipe_prompt(block: Mapping[str, Any]) -> str:
    name = str(block.get("name") or "block").strip()
    structure = str(block.get("recommended_structure") or "").strip()
    constraints = [
        str(item).strip()
        for item in (block.get("visual_constraints") or [])
        if str(item).strip()
    ]
    parts = [name]
    if structure:
        parts.append(structure)
    if constraints:
        parts.append(" / ".join(constraints[:2]))
    return " - ".join(parts)


def _extract_pattern_hints(outline_items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for item in outline_items:
        if not isinstance(item, Mapping):
            continue
        hint = item.get("slidev_pattern_hint") or {}
        if not isinstance(hint, Mapping):
            hint = {}
        hints.append(
            {
                "slide_number": int(item.get("slide_number") or 0),
                "title": str(item.get("title") or ""),
                "slide_role": str(item.get("slide_role") or ""),
                "content_shape": str(item.get("content_shape") or ""),
                "preferred_layouts": list(hint.get("preferred_layouts") or []),
                "preferred_patterns": list(hint.get("preferred_patterns") or []),
                "reason": str(hint.get("reason") or ""),
            }
        )
    return hints


def _extract_visual_hints(outline_items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for item in outline_items:
        if not isinstance(item, Mapping):
            continue
        hint = item.get("slidev_visual_hint") or {}
        if not isinstance(hint, Mapping):
            hint = {}
        hints.append(
            {
                "slide_number": int(item.get("slide_number") or 0),
                "title": str(item.get("title") or ""),
                "slide_role": str(item.get("slide_role") or ""),
                "recipe_name": str(hint.get("name") or ""),
                "preferred_classes": list(hint.get("preferred_classes") or []),
                "required_signals": list(hint.get("required_signals") or []),
                "description": str(hint.get("description") or ""),
            }
        )
    return hints


def _build_mapping_summary(pattern_hints: Sequence[Mapping[str, Any]], validation: Mapping[str, Any]) -> dict[str, Any]:
    recommended_layouts = sorted(
        {
            str(layout).strip()
            for hint in pattern_hints
            for layout in (hint.get("preferred_layouts") or [])
            if str(layout).strip()
        }
    )
    recommended_patterns = sorted(
        {
            str(pattern).strip()
            for hint in pattern_hints
            for pattern in (hint.get("preferred_patterns") or [])
            if str(pattern).strip()
        }
    )
    native_usage = validation.get("native_usage_summary") if isinstance(validation, Mapping) else {}
    if not isinstance(native_usage, Mapping):
        native_usage = {}
    return {
        "hinted_slide_count": len(pattern_hints),
        "recommended_layouts": recommended_layouts,
        "recommended_patterns": recommended_patterns,
        "observed_layouts": list(native_usage.get("layouts") or []),
        "native_slide_count": int(native_usage.get("native_slide_count") or 0),
        "plain_slide_count": int(native_usage.get("plain_slide_count") or 0),
    }


def _build_visual_recipe_summary(
    visual_hints: Sequence[Mapping[str, Any]],
    deck_review: Mapping[str, Any] | None,
    validation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    slide_reports = deck_review.get("slide_reports") if isinstance(deck_review, Mapping) else []
    if not isinstance(slide_reports, list):
        slide_reports = []
    matched = 0
    weak = 0
    missing = 0
    for report in slide_reports:
        if not isinstance(report, Mapping):
            continue
        status = str(report.get("visual_recipe_status") or "").strip().lower()
        if status == "matched":
            matched += 1
        elif status == "weak":
            weak += 1
        elif status == "missing":
            missing += 1

    native_usage = validation.get("native_usage_summary") if isinstance(validation, Mapping) else {}
    if not isinstance(native_usage, Mapping):
        native_usage = {}
    recipe_classes = native_usage.get("recipe_classes") or {}
    if not isinstance(recipe_classes, Mapping):
        recipe_classes = {}
    return {
        "hinted_slide_count": len(visual_hints),
        "expected_recipe_names": [str(hint.get("recipe_name") or "") for hint in visual_hints if str(hint.get("recipe_name") or "")],
        "matched_recipe_count": matched,
        "weak_recipe_count": weak,
        "missing_recipe_count": missing,
        "recipe_classes": {str(key): int(value) for key, value in recipe_classes.items()},
        "blank_first_slide_detected": bool(
            (isinstance(deck_review, Mapping) and deck_review.get("blank_first_slide_detected"))
            or (isinstance(validation, Mapping) and validation.get("blank_first_slide_detected"))
        ),
    }


def _compact_stray_metadata_deck(markdown: str) -> tuple[str, dict[str, Any]]:
    prefix, _body = _split_global_frontmatter_block(str(markdown or ""))
    slides = _parse_slidev_slides(markdown)
    if not slides:
        return markdown, {"stray_metadata_repaired_count": 0, "empty_slide_repaired_count": 0}
    compacted_slides, report = _compact_stray_metadata_slides(slides)
    if not compacted_slides:
        return markdown, report
    if int(report.get("stray_metadata_repaired_count") or 0) == 0:
        return markdown, report
    deck_body = _serialize_slidev_slides(compacted_slides)
    normalized = f"{prefix}{deck_body}\n" if prefix else f"{deck_body}\n"
    return normalized, report


def _compact_stray_metadata_slides(slides: Sequence[str]) -> tuple[list[str], dict[str, Any]]:
    if not slides:
        return [], {"stray_metadata_repaired_count": 0, "empty_slide_repaired_count": 0}
    compacted = [str(slide).strip() for slide in slides if str(slide).strip()]
    repaired_actions: list[dict[str, Any]] = []
    index = 0
    while index < len(compacted):
        payload = _stray_metadata_payload(compacted[index])
        if not payload:
            index += 1
            continue
        merged = False
        if index + 1 < len(compacted):
            compacted[index + 1] = _merge_stray_metadata_into_slide(compacted[index + 1], payload)
            repaired_actions.append({"target": index + 1, "source": index, "keys": sorted(payload)})
            del compacted[index]
            merged = True
        elif index > 0:
            compacted[index - 1] = _merge_stray_metadata_into_slide(compacted[index - 1], payload)
            repaired_actions.append({"target": index - 1, "source": index, "keys": sorted(payload)})
            del compacted[index]
            merged = True
        if not merged:
            index += 1
    return compacted, {
        "stray_metadata_repaired_count": len(repaired_actions),
        "empty_slide_repaired_count": len(repaired_actions),
        "stray_metadata_actions": repaired_actions,
    }


def _stray_metadata_payload(slide: str) -> dict[str, list[str]]:
    body = _strip_slide_frontmatter(slide)
    nonempty = [line.strip() for line in body.splitlines() if line.strip()]
    if not nonempty or len(nonempty) > 2:
        return {}
    allowed = {"container", "kicker", "subtitle", "eyebrow", "topline", "footer"}
    payload: dict[str, list[str]] = {}
    for line in nonempty:
        key = _frontmatter_key(line)
        if key in allowed:
            payload.setdefault(key, []).append(line.split(":", 1)[1].strip())
            continue
        html_match = re.match(r'^<div class="([^"]+)">(.*?)</div>$', line)
        if not html_match:
            return {}
        class_name = html_match.group(1).strip()
        html_value = html_match.group(2).strip()
        html_key = {
            "slide-topline": "topline",
            "section-kicker": "kicker",
            "slide-subtitle": "subtitle",
            "slide-footer": "footer",
        }.get(class_name)
        if html_key not in allowed or not html_value:
            return {}
        payload.setdefault(html_key, []).append(html_value)
    return payload


def _merge_stray_metadata_into_slide(slide: str, payload: Mapping[str, Sequence[str]]) -> str:
    merged = str(slide or "").strip()
    if not merged:
        return merged
    container_values = [str(value).strip() for value in (payload.get("container") or []) if str(value).strip()]
    for value in container_values:
        merged = _prepend_slide_frontmatter_classes(merged, value)
    cue_lines: list[str] = []
    for key, class_name in (
        ("topline", "slide-topline"),
        ("eyebrow", "section-kicker"),
        ("kicker", "section-kicker"),
        ("subtitle", "slide-subtitle"),
        ("footer", "slide-footer"),
    ):
        for value in payload.get(key) or []:
            text = str(value).strip()
            if not text:
                continue
            cue_lines.append(f'<div class="{class_name}">{text}</div>')
    if not cue_lines:
        return merged
    frontmatter = _frontmatter_block(merged)
    body = _strip_slide_frontmatter(merged).strip()
    parts = ["\n".join(cue_lines).strip(), body] if body else ["\n".join(cue_lines).strip()]
    rebuilt_body = "\n\n".join(part for part in parts if part).strip()
    if frontmatter:
        return "\n".join(["---", frontmatter, "---", "", rebuilt_body]).strip()
    return rebuilt_body


def _prepend_slide_frontmatter_classes(slide: str, class_value: str) -> str:
    frontmatter = _frontmatter_block(slide)
    classes = [token.strip() for token in re.split(r"\s+", str(class_value or "").strip()) if token.strip()]
    body = _strip_slide_frontmatter(slide).strip()
    if frontmatter:
        updated = frontmatter
        existing = _frontmatter_scalar_value(frontmatter, "class")
        merged_classes = _merge_class_tokens(existing, " ".join(classes))
        updated = _replace_or_append_frontmatter_scalar(updated, "class", merged_classes)
        return "\n".join(["---", updated, "---", "", body]).strip()
    if not classes:
        return slide
    return "\n".join(["---", f"class: {' '.join(classes)}", "---", "", body]).strip()


def _normalize_slidev_composition(markdown: str) -> tuple[str, dict[str, Any]]:
    normalized, metadata = _normalize_leading_first_slide_frontmatter(markdown)
    normalized, separator_metadata = _normalize_double_separator_slide_frontmatter(normalized)
    metadata.update(separator_metadata)
    normalized, compaction_metadata = _compact_stray_metadata_deck(normalized)
    metadata.update(compaction_metadata)
    normalizer_actions = list(metadata.get("normalizer_actions") or [])
    if bool(metadata.get("blank_first_slide_detected")):
        normalizer_actions.append("blank_first_slide_normalized")
    if bool(metadata.get("double_separator_frontmatter_detected")):
        normalizer_actions.append("double_separator_frontmatter_normalized")
    if int(metadata.get("stray_metadata_repaired_count") or 0) > 0:
        normalizer_actions.append("stray_metadata_slide_compacted")
    metadata["normalizer_actions"] = sorted(set(normalizer_actions))
    return normalized, metadata


def _normalize_leading_first_slide_frontmatter(markdown: str) -> tuple[str, dict[str, Any]]:
    text = str(markdown or "")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not match:
        return text, {"blank_first_slide_detected": False, "normalized_first_slide_frontmatter": False}

    global_frontmatter = match.group(1)
    body = match.group(2)
    body_match = re.match(r"^\s*---\s*\n(.*?)\n---\s*\n?(.*)$", body, re.DOTALL)
    if not body_match:
        return text, {"blank_first_slide_detected": False, "normalized_first_slide_frontmatter": False}

    slide_frontmatter = body_match.group(1)
    remaining = body_match.group(2)
    slide_lines = slide_frontmatter.splitlines()
    if not _looks_like_slide_frontmatter(slide_lines) or not remaining.strip():
        return text, {"blank_first_slide_detected": False, "normalized_first_slide_frontmatter": False}

    merged_frontmatter = _merge_frontmatter_blocks(global_frontmatter, slide_frontmatter)
    normalized = f"---\n{merged_frontmatter}\n---\n\n{remaining.lstrip()}".rstrip() + "\n"
    return normalized, {"blank_first_slide_detected": True, "normalized_first_slide_frontmatter": True}


def _normalize_double_separator_slide_frontmatter(markdown: str) -> tuple[str, dict[str, Any]]:
    text = str(markdown or "")
    prefix, body = _split_global_frontmatter_block(text)
    if not body.strip():
        return text, {"double_separator_frontmatter_detected": False, "normalized_double_separator_frontmatter_count": 0}

    lines = body.splitlines()
    normalized_lines: list[str] = []
    index = 0
    inside_fence = False
    normalized_count = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            inside_fence = not inside_fence

        if not inside_fence and stripped == "---":
            probe_index = index + 1
            while probe_index < len(lines) and not lines[probe_index].strip():
                probe_index += 1
            if probe_index < len(lines) and lines[probe_index].strip() == "---":
                frontmatter_block, next_index = _consume_slide_frontmatter_block(lines, probe_index + 1)
                if frontmatter_block is not None:
                    normalized_lines.extend(["---", *frontmatter_block, "---"])
                    normalized_count += 1
                    index = next_index
                    continue

        normalized_lines.append(line)
        index += 1

    normalized_body = "\n".join(normalized_lines).strip()
    normalized_body = re.sub(
        r"(?m)^---\s*\n\s*---\s*\n(?=(?:layout|class|transition|background):)",
        "---\n",
        normalized_body,
    )
    normalized = prefix + normalized_body
    if normalized_body:
        normalized = normalized.rstrip() + "\n"
    return normalized, {
        "double_separator_frontmatter_detected": normalized_count > 0,
        "normalized_double_separator_frontmatter_count": normalized_count,
    }


def _merge_frontmatter_blocks(base: str, extra: str) -> str:
    merged: list[str] = []
    key_positions: dict[str, int] = {}

    def _register(lines: Sequence[str], *, replace_existing: bool) -> None:
        for raw_line in lines:
            line = raw_line.rstrip()
            key = _frontmatter_key(line)
            if key and key in key_positions and replace_existing:
                merged[key_positions[key]] = line
                continue
            if key:
                key_positions[key] = len(merged)
            merged.append(line)

    _register(base.splitlines(), replace_existing=False)
    _register(extra.splitlines(), replace_existing=True)
    return "\n".join(merged).strip()


def _frontmatter_key(line: str) -> str | None:
    if not line or line.startswith((" ", "\t", "-", "#")):
        return None
    if ":" not in line:
        return None
    return line.split(":", 1)[0].strip() or None


def _parse_slidev_slides(markdown: str) -> list[str]:
    text = markdown.strip()
    if not text:
        return []
    first_slide_frontmatter = _extract_first_slide_frontmatter_from_global(text)
    body = _strip_global_frontmatter(text)
    if not body.strip():
        return []

    slides: list[str] = []
    current: list[str] = []
    lines = body.splitlines()
    index = 0
    inside_fence = False
    pending_frontmatter: list[str] | None = None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            inside_fence = not inside_fence

        if not inside_fence and stripped == "---":
            if current:
                slide_text = "\n".join(current).strip()
                if slide_text:
                    slides.append(slide_text)
                current = []
            frontmatter_block, next_index = _consume_slide_frontmatter_block(lines, index + 1)
            if frontmatter_block is not None:
                pending_frontmatter = frontmatter_block
                index = next_index
                continue
            index += 1
            continue

        if pending_frontmatter:
            current.extend(["---", *pending_frontmatter, "---"])
            pending_frontmatter = None
        current.append(line)
        index += 1

    if pending_frontmatter:
        current.extend(["---", *pending_frontmatter, "---"])
    slide_text = "\n".join(current).strip()
    if slide_text:
        slides.append(slide_text)
    if slides and first_slide_frontmatter:
        slides[0] = "\n".join(["---", *first_slide_frontmatter, "---", slides[0]])
    return slides


def _serialize_slidev_slides(slides: Sequence[str]) -> str:
    serialized: list[str] = []
    for index, raw_slide in enumerate(slides):
        slide = str(raw_slide or "").strip()
        if not slide:
            continue
        if index == 0:
            serialized.append(slide)
            continue
        if slide.startswith("---\n"):
            serialized.append(slide)
        else:
            serialized.append(f"---\n\n{slide}")
    return "\n\n".join(serialized).rstrip()


def _split_global_frontmatter_block(text: str) -> tuple[str, str]:
    match = re.match(r"^(---\s*\n.*?\n---\s*\n?)(.*)$", text, re.DOTALL)
    if not match:
        return "", text
    return match.group(1), match.group(2)


def _strip_global_frontmatter(text: str) -> str:
    match = re.match(r"^---\s*\n.*?\n---\s*\n?", text, re.DOTALL)
    if match:
        return text[match.end():]
    return text


def _extract_first_slide_frontmatter_from_global(text: str) -> list[str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not match:
        return []
    allowed = {"layout", "class", "transition", "background"}
    lines: list[str] = []
    for raw_line in match.group(1).splitlines():
        key = _frontmatter_key(raw_line.rstrip())
        if key in allowed:
            lines.append(raw_line.rstrip())
    return lines


def _strip_slide_frontmatter(slide: str) -> str:
    return re.sub(r"^---\s*\n.*?\n---\s*\n?", "", str(slide or ""), count=1, flags=re.DOTALL)


def _frontmatter_block(slide: str) -> str:
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", str(slide or ""), re.DOTALL)
    return match.group(1) if match else ""


def _consume_slide_frontmatter_block(lines: Sequence[str], start_index: int) -> tuple[list[str] | None, int]:
    index = start_index
    block: list[str] = []
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped == "---":
            return (block if _looks_like_slide_frontmatter(block) else None, index + 1)
        block.append(lines[index])
        index += 1
    return None, start_index


def _looks_like_slide_frontmatter(lines: Sequence[str]) -> bool:
    meaningful = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    if not meaningful:
        return False
    return all(":" in line and not line.startswith("::") for line in meaningful)


def _text_hash(text: str) -> str:
    return sha1(text.encode("utf-8")).hexdigest()


def _outline_hash(outline: Mapping[str, Any] | None) -> str:
    payload = outline if isinstance(outline, Mapping) else {}
    return sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _collect_structure_warnings(*reports: dict[str, Any] | None) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for report in reports:
        if not isinstance(report, dict):
            continue
        entries = report.get("warnings") or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            code = str(entry.get("code") or "").strip()
            message = str(entry.get("message") or "").strip()
            if not code or not message:
                continue
            key = (code, message)
            if key in seen:
                continue
            seen.add(key)
            warnings.append({"code": code, "message": message})
    return warnings


def _save_gate_error(*, reason_code: str, message: str, next_action: str) -> SlidevMvpValidationError:
    return SlidevMvpValidationError(message, reason_code=reason_code, next_action=next_action)


def _provider_response_error(exc: UnexpectedModelBehavior) -> SlidevMvpProviderError:
    provider_message = str(exc).strip() or type(exc).__name__
    if is_malformed_provider_response(exc):
        reason_code = "provider_malformed_response"
        message = "上游模型返回了不完整或异常的响应，Slidev deck 生成已中止。"
        next_action = "请重试生成；若持续失败，请切换模型或稍后重试。"
    else:
        reason_code = "provider_unexpected_behavior"
        message = "上游模型返回了未分类的异常行为，Slidev deck 生成已中止。"
        next_action = "请检查模型/provider 配置或更换模型后重试。"
    if provider_message:
        message = f"{message} provider={provider_message}"
    return SlidevMvpProviderError(
        message,
        reason_code=reason_code,
        next_action=next_action,
    )


def _ensure_save_prerequisites(
    *,
    runtime: _RuntimeContext,
    state: PipelineState,
    markdown: str,
) -> None:
    if runtime.outline_review is None:
        raise _save_gate_error(
            reason_code="outline_review_missing",
            message="还没有完成大纲正式审查，不能保存 artifact。",
            next_action="调用 review_slidev_outline()",
        )
    if not bool(runtime.outline_review.get("ok")):
        raise _save_gate_error(
            reason_code="outline_review_failed",
            message="Deck 大纲结构审查未通过，不能保存 artifact。",
            next_action="修正大纲后重新调用 review_slidev_outline()",
        )
    if runtime.outline_review_hash and runtime.outline_review_hash != _outline_hash(state.outline):
        raise _save_gate_error(
            reason_code="outline_review_stale",
            message="大纲在审查后发生了变化，不能直接保存 artifact。",
            next_action="重新调用 review_slidev_outline()",
        )
    if runtime.reference_selection is None:
        raise _save_gate_error(
            reason_code="reference_selection_missing",
            message="还没有完成 Slidev references 选择，不能保存 artifact。",
            next_action="调用 select_slidev_references()",
        )
    if runtime.reference_selection_hash and runtime.reference_selection_hash != _outline_hash(state.outline):
        raise _save_gate_error(
            reason_code="reference_selection_stale",
            message="大纲在选择 references 后发生了变化，不能直接保存 artifact。",
            next_action="重新调用 select_slidev_references()",
        )
    if runtime.deck_review is None:
        raise _save_gate_error(
            reason_code="deck_review_missing",
            message="还没有完成 deck 结构审查，不能保存 artifact。",
            next_action="调用 review_slidev_deck({'markdown': '<完整 deck markdown>'})",
        )
    if not bool(runtime.deck_review.get("ok")):
        raise _save_gate_error(
            reason_code="deck_review_failed",
            message="Deck 结构审查未通过，不能保存 artifact。",
            next_action="修正 markdown 后重新调用 review_slidev_deck(...)",
        )
    if runtime.deck_review_hash and runtime.deck_review_hash != _text_hash(markdown):
        raise _save_gate_error(
            reason_code="deck_review_stale",
            message="Markdown 在结构审查后发生了变化，不能直接保存 artifact。",
            next_action="重新调用 review_slidev_deck(...)",
        )
    if runtime.validation is None:
        raise _save_gate_error(
            reason_code="validation_missing",
            message="还没有完成 Slidev 语法校验，不能保存 artifact。",
            next_action="调用 validate_slidev_deck({'markdown': '<完整 deck markdown>'})",
        )
    if not bool(runtime.validation.get("ok")):
        raise _save_gate_error(
            reason_code="validation_failed",
            message="Deck 静态校验未通过，不能保存 artifact。",
            next_action="修正 markdown 后重新调用 validate_slidev_deck(...)",
        )
    if runtime.validation_hash and runtime.validation_hash != _text_hash(markdown):
        raise _save_gate_error(
            reason_code="validation_stale",
            message="Markdown 在语法校验后发生了变化，不能直接保存 artifact。",
            next_action="重新调用 validate_slidev_deck(...)",
        )


def _missing_artifact_error(runtime: _RuntimeContext) -> SlidevMvpValidationError:
    if runtime.save_failure is not None:
        return runtime.save_failure
    if runtime.outline_review is None:
        return _save_gate_error(
            reason_code="outline_review_missing",
            message="Agent 未完成大纲正式审查，因此没有保存 Slidev artifact。",
            next_action="调用 review_slidev_outline()",
        )
    if not bool(runtime.outline_review.get("ok")):
        return _save_gate_error(
            reason_code="outline_review_failed",
            message="Deck 大纲结构审查未通过，因此没有保存 Slidev artifact。",
            next_action="修正大纲后重新调用 review_slidev_outline()",
        )
    if runtime.reference_selection is None:
        return _save_gate_error(
            reason_code="reference_selection_missing",
            message="Agent 未完成 Slidev references 选择，因此没有保存 Slidev artifact。",
            next_action="调用 select_slidev_references()",
        )
    if runtime.deck_review is None:
        return _save_gate_error(
            reason_code="deck_review_missing",
            message="Agent 未完成 deck 结构审查，因此没有保存 Slidev artifact。",
            next_action="调用 review_slidev_deck({'markdown': '<完整 deck markdown>'})",
        )
    if not bool(runtime.deck_review.get("ok")):
        return _save_gate_error(
            reason_code="deck_review_failed",
            message="Deck 结构审查未通过，因此没有保存 Slidev artifact。",
            next_action="修正 markdown 后重新调用 review_slidev_deck(...)",
        )
    if runtime.validation is None:
        return _save_gate_error(
            reason_code="validation_missing",
            message="Agent 未完成 Slidev 语法校验，因此没有保存 Slidev artifact。",
            next_action="调用 validate_slidev_deck({'markdown': '<完整 deck markdown>'})",
        )
    if not bool(runtime.validation.get("ok")):
        return _save_gate_error(
            reason_code="validation_failed",
            message="Deck 静态校验未通过，因此没有保存 Slidev artifact。",
            next_action="修正 markdown 后重新调用 validate_slidev_deck(...)",
        )
    return _save_gate_error(
        reason_code="artifact_not_saved",
        message="Agent 没有在 review/validate 通过后调用 save_slidev_artifact。",
        next_action="调用 save_slidev_artifact({'title': '<deck title>', 'markdown': '<完整 deck markdown>'})",
    )

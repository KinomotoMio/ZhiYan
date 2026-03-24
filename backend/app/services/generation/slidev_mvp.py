"""Offline Slidev MVP orchestration for issue #178.

This service proves the existing harness can drive a mature external
presentation runtime without touching the current generation-job/UI pipeline.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha1
import json
from pathlib import Path
import re
import shlex
import subprocess
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.services.document.parser import estimate_tokens, extract_structure_signals
from app.services.generation.agentic import (
    AgenticLoopResult,
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
    summarize_state,
)
from app.services.generation.agentic.todo import TodoManager
from app.services.generation.agentic.types import AgenticModelClient
from app.services.pipeline.graph import PipelineState
from app.services.sessions import session_store
from app.services.skill_runtime.registry import SkillRegistry

SLIDEV_ARTIFACT_ROOT = settings.project_root / "data" / "slidev-mvp"
SLIDEV_SANDBOX_DIR = settings.project_root / "design" / "slidev-mvp"
SLIDEV_SLIDES_FILENAME = "slides.md"
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
    pattern_hints: list[dict[str, Any]] = field(default_factory=list)
    save_failure: SlidevMvpValidationError | None = None
    saved_artifact: SlidevMvpArtifacts | None = None


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
        registry = self._build_registry(state=state, runtime=runtime, todo_manager=todo_manager)

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
        self.last_loop_result = loop_result

        if runtime.saved_artifact is None:
            raise _missing_artifact_error(runtime)

        artifact = runtime.saved_artifact
        agentic_summary = {
            "turns": loop_result.turns,
            "stop_reason": loop_result.stop_reason,
            "max_turns_reached": loop_result.max_turns_reached,
            "used_subagent": runtime.used_subagent,
            "loaded_skills": sorted(runtime.loaded_skills),
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
            "4. 用 set_slidev_outline 写入页级大纲，每页都必须包含 title / slide_role / content_shape / goal；这个 outline 是 deck contract，不是随手草稿。\n"
            "5. 调用 review_slidev_outline() 审查大纲结构，不要自己拼 review_outline.py 的参数。\n"
            "6. dispatch_subagent 是可选能力：只有在中间页需要额外起草且值得增加一次模型往返时才调用；简单 deck 直接在主循环完成即可。\n"
            "7. 产出完整的 Slidev markdown：第一张 slide 含全局 frontmatter，正文用 --- 分隔，并按 outline 顺序兑现每页 role；优先使用当前 role 对应的 Slidev native layout/pattern；framework/comparison/recommendation/closing 不能退化成无差别 bullet dump。\n"
            "8. 在保存前调用 review_slidev_deck(markdown=...) 做结构审查，例如 {'markdown': '---\\n...'}；hard issues 会阻断保存，warnings 只用于提示改进。\n"
            "9. 再调用 validate_slidev_deck(markdown=...) 做语法审查，例如 {'markdown': '---\\n...'}。\n"
            "10. 最后只能通过 save_slidev_artifact(title, markdown) 结束。不要直接在文本里返回整份 deck。\n\n"
            "额外约束：\n"
            "- 不要直接调用 run_skill 来做 review_outline.py / review_deck.py / validate_deck.py。\n"
            "- subagent 的文本意见不能替代正式审查结果。\n"
            "- 只在 review_slidev_outline / review_slidev_deck / validate_slidev_deck 都完成且通过后，才允许 save_slidev_artifact。\n\n"
            "第一页语法约束：\n"
            "- 如果第一页就是 cover / center，请把 `layout`、`class` 直接写进开头的全局 frontmatter，不要先输出一个空 `---` 再开封面页。\n"
            "- 如果后续页面要使用 `layout:` / `class:` frontmatter，必须写成完整 fenced block：`---` / `layout: ...` / `class: ...` / `---`；不要输出裸 `layout:` 行。\n"
            "- 推荐第一张 slide 的开头示例：\n"
            "  ---\n"
            "  theme: default\n"
            "  title: Deck Title\n"
            "  layout: cover\n"
            "  class: deck-cover\n"
            "  ---\n"
            "  # 标题\n"
            "  一句副标题\n\n"
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
                runtime.deck_review = result
                runtime.deck_review_hash = _text_hash(str(parameters.get("markdown") or ""))
                state.document_metadata["slidev_deck_review"] = result
            if skill_name == "slidev-syntax" and script_name == "validate_deck.py":
                if not isinstance(result, dict):
                    raise SlidevMvpValidationError("slidev-syntax validation must return a JSON object.")
                runtime.validation = result
                runtime.validation_hash = _text_hash(str(parameters.get("markdown") or ""))
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
        normalized_markdown, normalization = _normalize_slidev_composition(markdown)
        runtime.artifact_dir.mkdir(parents=True, exist_ok=True)
        runtime.slides_path.write_text(normalized_markdown.rstrip() + "\n", encoding="utf-8")
        self._ensure_runtime_link(runtime.artifact_dir)

        slide_count = _count_slidev_slides(normalized_markdown)
        outline_items = state.outline.get("items", []) if isinstance(state.outline, dict) else []
        pattern_hints = _extract_pattern_hints(outline_items)
        visual_hints = _extract_visual_hints(outline_items)
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
        state.document_metadata.update(
            {
                "slidev_slide_count": slide_count,
                "slidev_validation": runtime.validation or {},
                "slidev_outline_review": runtime.outline_review or {},
                "slidev_deck_review": runtime.deck_review or {},
                "slidev_structure_warnings": structure_warnings,
                "slidev_pattern_hints": pattern_hints,
                "slidev_visual_hints": visual_hints,
                "slidev_native_usage": (runtime.validation or {}).get("native_usage_summary", {}),
                "slidev_mapping_summary": _build_mapping_summary(pattern_hints, runtime.validation or {}),
                "slidev_visual_recipe_summary": _build_visual_recipe_summary(
                    visual_hints,
                    runtime.deck_review or {},
                    runtime.validation or {},
                ),
                "slidev_composition_normalization": {
                    "blank_first_slide_detected": bool(normalization.get("blank_first_slide_detected")),
                    "double_separator_frontmatter_detected": bool(
                        normalization.get("double_separator_frontmatter_detected")
                    ),
                    "normalized_double_separator_frontmatter_count": int(
                        normalization.get("normalized_double_separator_frontmatter_count") or 0
                    ),
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
                "mapping_summary": _build_mapping_summary(pattern_hints, runtime.validation or {}),
                "visual_recipe_summary": _build_visual_recipe_summary(
                    visual_hints,
                    runtime.deck_review or {},
                    runtime.validation or {},
                ),
                "blank_first_slide_detected": bool(normalization.get("blank_first_slide_detected")),
                "composition_normalization": {
                    "blank_first_slide_detected": bool(normalization.get("blank_first_slide_detected")),
                    "double_separator_frontmatter_detected": bool(
                        normalization.get("double_separator_frontmatter_detected")
                    ),
                    "normalized_double_separator_frontmatter_count": int(
                        normalization.get("normalized_double_separator_frontmatter_count") or 0
                    ),
                },
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


def _normalize_slidev_composition(markdown: str) -> tuple[str, dict[str, Any]]:
    normalized, metadata = _normalize_leading_first_slide_frontmatter(markdown)
    normalized, separator_metadata = _normalize_double_separator_slide_frontmatter(normalized)
    metadata.update(separator_metadata)
    return normalized, metadata


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

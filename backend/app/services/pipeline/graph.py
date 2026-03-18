"""Pipeline stages for generation v2.

Flow:
  parse -> outline -> layout -> slides -> assets -> verify -> fix(optional)
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.models.slide import Slide
from app.services.fallback_semantics import (
    CONTENT_GENERATING,
    FALLBACK_GENERATED,
    get_bullet_fallback_status,
    is_placeholder_text,
)
from app.services.image_semantics import normalize_image_content_data
from app.services.pipeline.content_type_signals import infer_content_signals

logger = logging.getLogger(__name__)

TOTAL_STEPS = 6
_SLIDE_CONTEXT_MAX_CHARS = 2000
_ADJACENT_LAYOUT_DIVERSITY_EXEMPT_GROUPS = {
    "cover",
    "agenda",
    "section-divider",
    "closing",
}
_VISUAL_EXPLAINER_KEYWORDS = (
    "图片",
    "配图",
    "图文",
    "案例",
    "场景",
    "示例",
    "展示",
    "演示",
    "说明",
    "解析",
    "界面",
    "截图",
    "视觉",
    "照片",
    "hero",
    "image",
    "photo",
    "visual",
    "screenshot",
    "case study",
    "showcase",
)
_VISUAL_EXPLAINER_STRONG_KEYWORDS = (
    "图片",
    "配图",
    "图文",
    "案例",
    "界面",
    "截图",
    "视觉",
    "照片",
    "hero",
    "image",
    "photo",
    "visual",
    "screenshot",
    "case study",
    "showcase",
)
_CAPABILITY_GRID_KEYWORDS = (
    "模块",
    "矩阵",
    "清单",
    "一览",
    "分类",
    "维度",
    "体系",
    "grid",
    "matrix",
    "capability map",
    "feature set",
    "stack",
)
_EVIDENCE_VISUAL_KEYWORDS = (
    "图片",
    "配图",
    "界面",
    "截图",
    "场景",
    "照片",
    "视觉",
    "hero",
    "image",
    "photo",
    "visual",
    "screenshot",
    "showcase",
)
_CHART_ANALYSIS_KEYWORDS = (
    "图表",
    "曲线",
    "柱状",
    "折线",
    "趋势",
    "走势",
    "同比",
    "环比",
    "图",
    "chart",
    "graph",
    "trend",
    "analysis",
    "takeaway",
    "benchmark",
)
_TABLE_MATRIX_KEYWORDS = (
    "表格",
    "矩阵",
    "参数",
    "行列",
    "清单",
    "规格",
    "table",
    "matrix",
    "tabular",
    "spec",
    "parameter",
)
_TIMELINE_KEYWORDS = (
    "时间线",
    "里程碑",
    "阶段",
    "日期",
    "排期",
    "roadmap",
    "timeline",
    "milestone",
    "quarter",
    "month",
    "week",
)
_RESPONSE_MAPPING_KEYWORDS = (
    "挑战",
    "痛点",
    "问题",
    "方案",
    "回应",
    "结果",
    "改进",
    "challenge",
    "pain point",
    "response",
    "solution",
    "outcome",
)

# content_hints are produced by the outline stage as optional "structure intent" tags.
# Treat them as high-signal hints to reduce mis-matching (e.g., a chart page ending up as bullets).
_CONTENT_HINT_CHART_TOKENS = (
    "chart",
    "graph",
    "plot",
    "trend",
    "图表",
    "曲线",
    "柱状",
    "折线",
    "趋势",
    "走势",
)
_CONTENT_HINT_TABLE_TOKENS = ("table", "tabular", "matrix", "表格", "矩阵", "行列")
_CONTENT_HINT_TIMELINE_TOKENS = (
    "timeline",
    "roadmap",
    "milestone",
    "时间线",
    "里程碑",
    "排期",
    "日期",
)
_CONTENT_HINT_IMAGE_TOKENS = (
    "image",
    "visual",
    "photo",
    "screenshot",
    "图片",
    "配图",
    "照片",
    "截图",
    "界面",
)


def _normalize_content_hints(item: dict[str, Any]) -> list[str]:
    """Return canonicalized content hints (order-preserving, de-duplicated).

    Canonical hints: chart/table/timeline/image
    """

    raw = item.get("content_hints", [])
    if not isinstance(raw, list):
        return []

    canonical: list[str] = []
    for hint in raw:
        if not isinstance(hint, str):
            continue
        text = hint.strip().lower()
        if not text:
            continue

        tag = ""
        if any(token in text for token in _CONTENT_HINT_TIMELINE_TOKENS):
            tag = "timeline"
        elif any(token in text for token in _CONTENT_HINT_TABLE_TOKENS):
            tag = "table"
        elif any(token in text for token in _CONTENT_HINT_CHART_TOKENS):
            tag = "chart"
        elif any(token in text for token in _CONTENT_HINT_IMAGE_TOKENS):
            tag = "image"

        if tag and tag not in canonical:
            canonical.append(tag)

    return canonical


def _hinted_sub_group(item: dict[str, Any], role: str) -> str:
    """Map content_hints to a concrete sub_group for a given role.

    Note: group(role) is fixed by suggested_slide_role; hints only steer sub_group/variant.
    """

    hints = _normalize_content_hints(item)
    if not hints:
        return ""

    for hint in hints:
        if role == "evidence":
            if hint == "chart":
                return "chart-analysis"
            if hint == "table":
                return "table-matrix"
            if hint == "image":
                return "visual-evidence"
        if role == "process" and hint == "timeline":
            return "timeline-milestone"
        if role == "narrative" and hint == "image":
            return "visual-explainer"

    return ""


def _hinted_variant(item: dict[str, Any], role: str, sub_group: str) -> str:
    """Map content_hints to a preferred variant on a resolved track."""

    hints = _normalize_content_hints(item)
    if not hints:
        return ""

    # Only map when the role+sub_group track is explicit; otherwise let existing heuristics decide.
    if role == "evidence":
        if sub_group == "chart-analysis":
            return "chart-takeaways"
        if sub_group == "table-matrix":
            return "data-matrix"
        if sub_group == "visual-evidence":
            return "context-metrics"
    if role == "process" and sub_group == "timeline-milestone":
        return "timeline-band"
    if role == "narrative" and sub_group == "visual-explainer":
        return "media-feature"

    return ""

ProgressHook = Callable[[str, int, int, str], Awaitable[None]]
SlideHook = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class PipelineState:
    """Pipeline shared state."""

    raw_content: str = ""
    source_ids: list[str] = field(default_factory=list)
    topic: str = ""
    template_id: str | None = None
    num_pages: int = 5
    job_id: str | None = None

    document_metadata: dict[str, Any] = field(default_factory=dict)
    outline: dict[str, Any] = field(default_factory=dict)
    layout_selections: list[dict[str, Any]] = field(default_factory=list)
    slide_contents: list[dict[str, Any]] = field(default_factory=list)

    slides: list[Slide] = field(default_factory=list)
    verification_issues: list[dict[str, Any]] = field(default_factory=list)
    failed_slide_indices: list[int] = field(default_factory=list)


async def stage_parse_document(state: PipelineState, progress: ProgressHook | None = None) -> None:
    from app.services.document.parser import estimate_tokens, extract_structure_signals

    if progress:
        await progress("parse", 1, TOTAL_STEPS, "解析文档...")

    content = state.raw_content or ""
    token_count = estimate_tokens(content)
    heading_count = sum(1 for line in content.split("\n") if line.startswith("#"))
    structure_signals = extract_structure_signals(content)

    # Preserve upstream metadata (e.g., computed source_hints) while refreshing parse stats.
    state.document_metadata.update(
        {
            "char_count": len(content),
            "estimated_tokens": token_count,
            "heading_count": heading_count,
            "structure_signals": structure_signals,
        }
    )

    logger.info(
        "ParseDocument: %d chars, ~%d tokens, %d headings",
        len(content),
        token_count,
        heading_count,
        extra={
            "job_id": state.job_id,
            "stage": "parse",
            "structure_signals": {
                "image_count": structure_signals.get("image_count", 0),
                "table_count": structure_signals.get("table_count", 0),
                "chart_keywords": structure_signals.get("chart_keyword_hits", []),
                "timeline_dates": structure_signals.get("timeline_date_hits", []),
                "timeline_quarters": structure_signals.get("timeline_quarter_hits", []),
            },
        },
    )


def _format_source_hints_for_prompt(source_hints: Any) -> str:
    if not isinstance(source_hints, dict):
        return ""
    total = source_hints.get("total_sources")
    try:
        total_int = int(total)
    except Exception:
        total_int = 0
    if total_int <= 0:
        return ""

    def get_int(key: str) -> int:
        try:
            return int(source_hints.get(key) or 0)
        except Exception:
            return 0

    images = get_int("images")
    data = get_int("data")
    documents = get_int("documents")
    slides = get_int("slides")
    unknown = get_int("unknown")
    return (
        "素材提示(source_hints): "
        f"总计 {total_int}，图片 {images}，数据/文本 {data}，文档 {documents}，PPT {slides}，未知 {unknown}"
    )


def _format_structure_signals_for_prompt(structure_signals: Any) -> str:
    if not isinstance(structure_signals, dict):
        return ""

    def to_int(value: Any) -> int:
        try:
            return int(value)
        except Exception:
            return 0

    image_count = to_int(structure_signals.get("image_count"))
    table_count = to_int(structure_signals.get("table_count"))
    image_samples = structure_signals.get("image_src_samples") or []
    table_samples = structure_signals.get("table_header_samples") or []
    chart_keywords = structure_signals.get("chart_keyword_hits") or []
    table_keywords = structure_signals.get("table_keyword_hits") or []
    timeline_keywords = structure_signals.get("timeline_keyword_hits") or []
    timeline_dates = structure_signals.get("timeline_date_hits") or []
    timeline_quarters = structure_signals.get("timeline_quarter_hits") or []

    has_any = any(
        [
            image_count > 0,
            table_count > 0,
            bool(chart_keywords),
            bool(timeline_keywords),
            bool(timeline_dates),
            bool(timeline_quarters),
        ]
    )
    if not has_any:
        return ""

    def fmt_samples(values: Any, limit: int = 3) -> str:
        if not isinstance(values, list):
            return ""
        cleaned = [str(v).strip() for v in values if str(v).strip()]
        return "、".join(cleaned[:limit])

    lines: list[str] = [
        "结构信号摘要（来自解析阶段，仅供你生成 content_hints 时参考）：",
        f"- 图片: {image_count}" + (f"（示例: {fmt_samples(image_samples)}）" if image_count else ""),
        f"- 表格: {table_count}" + (f"（示例表头: {fmt_samples(table_samples)}）" if table_count else ""),
    ]
    if chart_keywords:
        lines.append(f"- 图表关键词: {fmt_samples(chart_keywords, limit=6)}")
    if table_keywords and not table_count:
        lines.append(f"- 表格关键词: {fmt_samples(table_keywords, limit=6)}")
    if timeline_keywords:
        lines.append(f"- 时间线关键词: {fmt_samples(timeline_keywords, limit=6)}")
    if timeline_dates:
        lines.append(f"- 日期命中: {fmt_samples(timeline_dates, limit=6)}")
    if timeline_quarters:
        lines.append(f"- 季度命中: {fmt_samples(timeline_quarters, limit=6)}")

    return "\n".join(lines)


async def stage_generate_outline(state: PipelineState, progress: ProgressHook | None = None) -> None:
    from app.core.config import settings
    from app.services.document.parser import estimate_tokens
    from app.services.agents.outline_synthesizer import outline_synthesizer_agent
    from app.services.pipeline.layout_roles import normalize_outline_items_roles

    if progress:
        await progress("outline", 2, TOTAL_STEPS, "生成大纲...")

    t0 = time.monotonic()
    content = state.raw_content
    token_count = estimate_tokens(content)

    if token_count <= 8000:
        content_section = f"内容:\n{content}"
    else:
        content_section = f"内容（前 12000 字符）:\n{content[:12000]}"

    source_hints_section = _format_source_hints_for_prompt(
        state.document_metadata.get("source_hints")
    )
    source_hints_text = f"{source_hints_section}\n\n" if source_hints_section else ""

    structure_section = _format_structure_signals_for_prompt(
        state.document_metadata.get("structure_signals")
    )
    structure_section_text = f"{structure_section}\n\n" if structure_section else ""

    prompt = (
        f"演示文稿主题：{state.topic or '综合演示'}\n"
        f"目标页数：{state.num_pages} 页\n\n"
        f"{source_hints_text}"
        f"{structure_section_text}"
        f"{content_section}\n\n"
        f"请生成一个 {state.num_pages} 页的演示文稿大纲。"
    )

    model = settings.strong_model
    provider = model.split(":", 1)[0] if ":" in model else None
    logger.info(
        "Outline call start",
        extra={
            "job_id": state.job_id,
            "stage": "outline",
            "model": model,
            "provider": provider,
            "estimated_tokens": token_count,
            "timeout_seconds": settings.outline_timeout_seconds,
        },
    )

    try:
        result = await outline_synthesizer_agent.run(prompt)
        usage = result.usage()
        outline = result.output.model_dump()
        raw_outline_items = list(outline.get("items", []))
        outline["items"] = normalize_outline_items_roles(
            raw_outline_items,
            num_pages=state.num_pages,
        )
        state.outline = outline
        _log_outline_role_diagnostics(
            job_id=state.job_id,
            raw_items=raw_outline_items,
            normalized_items=outline["items"],
        )
        logger.info(
            "Outline call done",
            extra={
                "job_id": state.job_id,
                "stage": "outline",
                "model": settings.strong_model,
                "provider": settings.strong_model.split(":", 1)[0],
                "attempt": usage.requests,
                "token_usage": str(usage),
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            },
        )
    except Exception as e:
        logger.warning(
            "Outline generation failed: %s",
            e,
            extra={"job_id": state.job_id, "stage": "outline", "error_type": type(e).__name__},
        )
        raise

    outline_items = state.outline.get("items", [])
    logger.info(
        "GenerateOutline: %d items",
        len(outline_items),
        extra={"job_id": state.job_id, "stage": "outline"},
    )


async def stage_select_layouts(state: PipelineState, progress: ProgressHook | None = None) -> None:
    if progress:
        await progress("layout", 3, TOTAL_STEPS, "选择布局...")

    t0 = time.monotonic()

    from app.models.layout_registry import (
        get_all_layouts,
        get_layout,
        get_layout_taxonomy_catalog,
    )
    from app.core.config import settings
    from app.services.pipeline.layout_roles import (
        get_outline_item_role,
        normalize_outline_items_roles,
    )
    from app.services.pipeline.layout_usage import (
        format_usage_tags,
        infer_document_and_slide_usage,
        rank_layouts_by_usage,
    )

    outline_items = normalize_outline_items_roles(
        state.outline.get("items", []),
        num_pages=state.num_pages,
    )
    state.outline["items"] = outline_items
    layout_entries = get_all_layouts()
    document_usage_tags, slide_usage_tags = infer_document_and_slide_usage(
        state.topic,
        state.raw_content,
        outline_items,
    )
    state.document_metadata["layout_usage"] = {
        "document_tags": list(document_usage_tags),
        "slide_tags": {str(k): list(v) for k, v in slide_usage_tags.items()},
    }
    source_hints = state.document_metadata.get("source_hints")
    structure_signals = state.document_metadata.get("structure_signals")
    content_signals_by_slide: dict[int, dict[str, Any]] = {}
    for item in outline_items:
        slide_number = int(item.get("slide_number") or 0)
        if slide_number <= 0:
            continue
        role = get_outline_item_role(item)
        content_signals_by_slide[slide_number] = infer_content_signals(
            item,
            role=role,
            primary_strategy=settings.content_type_primary_strategy,
            shadow_enabled=settings.content_type_shadow_enabled,
            confidence_threshold=settings.content_type_confidence_threshold,
            source_hints=source_hints if isinstance(source_hints, Mapping) else None,
            structure_signals=structure_signals if isinstance(structure_signals, Mapping) else None,
        )

    items_text = "\n".join(
        _format_outline_item_for_layout_prompt(
            item,
            document_usage_tags=document_usage_tags,
            slide_usage_tags=slide_usage_tags,
            layout_entries=layout_entries,
            format_usage_tags_fn=format_usage_tags,
            rank_layouts_by_usage_fn=rank_layouts_by_usage,
        )
        for item in outline_items
    )
    document_usage_text = format_usage_tags(document_usage_tags)
    source_hints_section = _format_source_hints_for_prompt(
        state.document_metadata.get("source_hints")
    )
    source_hints_line = f"{source_hints_section}\n" if source_hints_section else ""
    prompt = (
        f"可用布局列表:\n{get_layout_taxonomy_catalog()}\n\n"
        f"文档级 Usage 推断: {document_usage_text}\n"
        f"{source_hints_line}"
        "选择规则:\n"
        "- 必须先满足每页的 suggested_slide_role 页面角色，并把它作为 group 输出\n"
        "- 先确定 group，再确定 sub_group，再输出 variant_id\n"
        "- 对存在正式结构层的 group，必须显式选择对应的 sub_group\n"
        "- 若某页包含 `结构提示(content_hints)`，把它当作强信号来选 sub_group/variant（优先级高于关键词猜测）\n"
        "- content_hints 映射: chart->evidence/chart-analysis, table->evidence/table-matrix, timeline->process/timeline-milestone, image->narrative/visual-explainer 或 evidence/visual-evidence（取决于该页 group）\n"
        "- narrative 候选为 icon-points / visual-explainer / capability-grid\n"
        "- evidence 候选为 stat-summary / visual-evidence / chart-analysis / table-matrix\n"
        "- comparison 候选为 side-by-side / response-mapping\n"
        "- process 候选为 step-flow / timeline-milestone\n"
        "- 其余 group 统一使用 sub_group=default\n"
        "- 优先选择 usage 匹配且结构匹配的 variant_id\n"
        "- 若 usage 匹配不足但结构明显更合适，可越过 usage\n"
        "- 系统会在你选中的 variant_id 下再解析具体 layout_id\n"
        "- 当 usage 未命中时，按内容结构与叙事节奏选择\n\n"
        f"大纲:\n{items_text}\n\n"
        "请为每页输出 group、sub_group、variant_id 和 reason。不要输出 layout_id。"
    )

    try:
        from app.services.agents.layout_selector import layout_selector_agent

        result = await layout_selector_agent.run(prompt)
        usage = result.usage()
        selections = result.output.model_dump()["slides"]
        decision_traces: dict[int, dict[str, Any]] = {}

        for sel in selections:
            item = next((it for it in outline_items if it["slide_number"] == sel["slide_number"]), None)
            role = get_outline_item_role(item or {})
            slide_number = int(sel.get("slide_number") or 0)
            effective_usage = slide_usage_tags.get(slide_number, ()) or document_usage_tags
            signal_bundle = content_signals_by_slide.get(slide_number, {})
            primary_signal = signal_bundle.get("primary")
            shadow_signal = signal_bundle.get("shadow")
            if not isinstance(primary_signal, Mapping):
                primary_signal = {}
            if not isinstance(shadow_signal, Mapping):
                shadow_signal = None
            requested_group = str(sel.get("group") or "")
            requested_sub_group = str(sel.get("sub_group") or "default")
            resolved_sub_group = _resolve_layout_sub_group(
                item or {},
                role=role,
                requested_sub_group=requested_sub_group,
                content_signal_primary=primary_signal,
            )
            requested_layout_id = str(sel.get("layout_id") or "")
            requested_layout = get_layout(requested_layout_id) if requested_layout_id else None
            requested_variant_id = str(sel.get("variant_id") or getattr(requested_layout, "variant_id", ""))
            resolved_variant_id = _resolve_layout_variant(
                item or {},
                role=role,
                sub_group=resolved_sub_group,
                requested_variant_id=requested_variant_id,
                usage_tags=effective_usage,
            )
            candidate_entries = _rank_group_sub_group_variant_layouts(
                layout_entries,
                group=role,
                sub_group=resolved_sub_group,
                variant_id=resolved_variant_id,
                usage_tags=effective_usage,
                rank_layouts_by_usage_fn=rank_layouts_by_usage,
            )
            final_layout_id = (
                candidate_entries[0].id
                if candidate_entries
                else _group_sub_group_variant_to_default_layout(
                    role,
                    resolved_sub_group,
                    resolved_variant_id,
                )
            )

            final_entry = get_layout(final_layout_id)
            used_safety_default = False
            if final_entry is None:
                final_layout_id = _group_sub_group_variant_to_default_layout(
                    role,
                    resolved_sub_group,
                    resolved_variant_id,
                )
                final_entry = get_layout(final_layout_id)
            if final_entry is None:
                logger.error(
                    "Layout selection fallback resolved to unknown layout, using safety default",
                    extra={
                        "job_id": state.job_id,
                        "stage": "layout",
                        "group": role,
                        "sub_group": resolved_sub_group,
                        "requested_variant_id": str(sel.get("variant_id") or ""),
                        "resolved_variant_id": resolved_variant_id,
                        "fallback_layout_id": final_layout_id,
                        "safety_layout_id": "bullet-with-icons",
                    },
                )
                used_safety_default = True
                final_layout_id = "bullet-with-icons"
                final_entry = get_layout(final_layout_id)
                if final_entry is None:
                    raise KeyError("Safety default layout 'bullet-with-icons' is unavailable")

            sel["layout_id"] = final_layout_id
            sel["group"] = role
            sel["sub_group"] = resolved_sub_group
            sel["variant_id"] = final_entry.variant_id
            sel["design_traits"] = _serialize_design_traits_from_entry(final_entry)
            if slide_number:
                decision_traces[slide_number] = {
                    "selection_source": "model",
                    "requested_group": requested_group,
                    "resolved_group": role,
                    "requested_sub_group": requested_sub_group,
                    "resolved_sub_group": resolved_sub_group,
                    "requested_variant_id": requested_variant_id,
                    "resolved_variant_id": resolved_variant_id,
                    "pre_diversity_layout_id": final_layout_id,
                    "effective_usage_tags": list(effective_usage),
                    "content_signal_primary": dict(primary_signal),
                    "content_signal_shadow": dict(shadow_signal) if shadow_signal else None,
                    "confidence": float(primary_signal.get("confidence") or 0.0),
                    "signal_source": str(primary_signal.get("signal_source") or "fallback"),
                    "used_safety_default": used_safety_default,
                }

        state.layout_selections = selections
        logger.info(
            "Layout selection call done",
            extra={
                "job_id": state.job_id,
                "stage": "layout",
                "model": settings.fast_model or settings.default_model,
                "provider": (settings.fast_model or settings.default_model).split(":", 1)[0],
                "attempt": usage.requests,
                "token_usage": str(usage),
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            },
        )
    except Exception as e:
        logger.warning(
            "Layout selection failed: %s, using role mapping",
            e,
            extra={"job_id": state.job_id, "stage": "layout", "error_type": type(e).__name__},
        )
        decision_traces = {}
        state.layout_selections = []
        for item in outline_items:
            role = get_outline_item_role(item)
            slide_number = int(item.get("slide_number") or 0)
            signal_bundle = content_signals_by_slide.get(slide_number, {})
            primary_signal = signal_bundle.get("primary")
            shadow_signal = signal_bundle.get("shadow")
            if not isinstance(primary_signal, Mapping):
                primary_signal = {}
            if not isinstance(shadow_signal, Mapping):
                shadow_signal = None
            resolved_sub_group = _resolve_layout_sub_group(
                item,
                role=role,
                requested_sub_group="default",
                content_signal_primary=primary_signal,
            )
            variant_id = _group_sub_group_to_default_variant(
                role,
                resolved_sub_group,
            )
            layout_id = _group_sub_group_variant_to_default_layout(
                role,
                resolved_sub_group,
                variant_id,
            )
            state.layout_selections.append(
                {
                    "slide_number": item["slide_number"],
                    "group": role,
                    "sub_group": resolved_sub_group,
                    "variant_id": variant_id,
                    "layout_id": layout_id,
                    "design_traits": _serialize_design_traits_from_entry(get_layout(layout_id)),
                    "reason": "fallback",
                }
            )
            if slide_number:
                decision_traces[slide_number] = {
                    "selection_source": "fallback",
                    "requested_group": "",
                    "resolved_group": role,
                    "requested_sub_group": "default",
                    "resolved_sub_group": resolved_sub_group,
                    "requested_variant_id": "",
                    "resolved_variant_id": variant_id,
                    "pre_diversity_layout_id": layout_id,
                    "effective_usage_tags": list(
                        slide_usage_tags.get(slide_number, ()) or document_usage_tags
                    ),
                    "content_signal_primary": dict(primary_signal),
                    "content_signal_shadow": dict(shadow_signal) if shadow_signal else None,
                    "confidence": float(primary_signal.get("confidence") or 0.0),
                    "signal_source": str(primary_signal.get("signal_source") or "fallback"),
                    "used_safety_default": False,
                }
    state.layout_selections = _finalize_layout_selections(
        selections=state.layout_selections,
        job_id=state.job_id,
        outline_items=outline_items,
        decision_traces=decision_traces,
        document_usage_tags=document_usage_tags,
        slide_usage_tags=slide_usage_tags,
        layout_entries=layout_entries,
        rank_layouts_by_usage_fn=rank_layouts_by_usage,
    )


def _group_sub_group_to_default_variant(group: str, sub_group: str) -> str:
    defaults: dict[tuple[str, str], str] = {
        ("cover", "default"): "title-centered",
        ("agenda", "default"): "section-cards",
        ("section-divider", "default"): "centered-divider",
        ("narrative", "icon-points"): "icon-pillars",
        ("narrative", "visual-explainer"): "media-feature",
        ("narrative", "capability-grid"): "icon-matrix",
        ("evidence", "stat-summary"): "kpi-grid",
        ("evidence", "visual-evidence"): "context-metrics",
        ("evidence", "chart-analysis"): "chart-takeaways",
        ("evidence", "table-matrix"): "data-matrix",
        ("comparison", "side-by-side"): "balanced-columns",
        ("comparison", "response-mapping"): "challenge-response",
        ("process", "step-flow"): "numbered-steps",
        ("process", "timeline-milestone"): "timeline-band",
        ("highlight", "default"): "quote-focus",
        ("closing", "default"): "closing-center",
    }
    return defaults.get((group, sub_group), "icon-pillars")


def _group_sub_group_variant_to_default_layout(group: str, sub_group: str, variant_id: str) -> str:
    defaults: dict[tuple[str, str, str], str] = {
        ("cover", "default", "title-centered"): "intro-slide",
        ("cover", "default", "title-left"): "intro-slide-left",
        ("agenda", "default", "section-cards"): "outline-slide",
        ("agenda", "default", "chapter-rail"): "outline-slide-rail",
        ("section-divider", "default", "centered-divider"): "section-header",
        ("section-divider", "default", "side-label"): "section-header-side",
        ("narrative", "icon-points", "icon-pillars"): "bullet-with-icons",
        ("narrative", "icon-points", "feature-cards"): "bullet-with-icons-cards",
        ("narrative", "visual-explainer", "media-feature"): "image-and-description",
        ("narrative", "capability-grid", "icon-matrix"): "bullet-icons-only",
        ("evidence", "stat-summary", "kpi-grid"): "metrics-slide",
        ("evidence", "stat-summary", "summary-band"): "metrics-slide-band",
        ("evidence", "visual-evidence", "context-metrics"): "metrics-with-image",
        ("evidence", "chart-analysis", "chart-takeaways"): "chart-with-bullets",
        ("evidence", "table-matrix", "data-matrix"): "table-info",
        ("comparison", "side-by-side", "balanced-columns"): "two-column-compare",
        ("comparison", "response-mapping", "challenge-response"): "challenge-outcome",
        ("process", "step-flow", "numbered-steps"): "numbered-bullets",
        ("process", "step-flow", "progress-track"): "numbered-bullets-track",
        ("process", "timeline-milestone", "timeline-band"): "timeline",
        ("highlight", "default", "quote-focus"): "quote-slide",
        ("highlight", "default", "banner-highlight"): "quote-banner",
        ("closing", "default", "closing-center"): "thank-you",
        ("closing", "default", "contact-card"): "thank-you-contact",
    }
    return defaults.get(
        (group, sub_group, variant_id),
        defaults.get(
            (group, sub_group, _group_sub_group_to_default_variant(group, sub_group)),
            _role_to_default_layout(group),
        ),
    )


def _format_outline_item_for_layout_prompt(
    item: dict[str, Any],
    *,
    document_usage_tags: tuple[str, ...],
    slide_usage_tags: dict[int, tuple[str, ...]],
    layout_entries: list[Any],
    format_usage_tags_fn,
    rank_layouts_by_usage_fn,
) -> str:
    from app.services.pipeline.layout_roles import get_default_layout_for_role, get_outline_item_role
    from app.services.pipeline.layout_taxonomy import (
        get_layout_variant_definition,
        get_sub_group_description,
        get_sub_group_label,
        get_sub_groups_for_group,
        get_variant_ids_for_sub_group,
    )

    slide_number = int(item.get("slide_number", 0))
    key_points = item.get("key_points", [])
    preview_points = ", ".join(str(point) for point in key_points[:3])
    content_hints = item.get("content_hints", [])
    hints_text = ""
    if isinstance(content_hints, list):
        cleaned = [str(hint).strip() for hint in content_hints if str(hint).strip()]
        if cleaned:
            hints_text = f", 结构提示(content_hints): {', '.join(cleaned[:6])}"
    role = get_outline_item_role(item)
    current_usage = slide_usage_tags.get(slide_number, ())
    effective_usage = current_usage or document_usage_tags
    usage_text = format_usage_tags_fn(current_usage)
    if not current_usage and document_usage_tags:
        usage_text = f"继承文档级({format_usage_tags_fn(document_usage_tags)})"

    role_matched = [entry for entry in layout_entries if str(entry.group) == role]
    if not role_matched:
        fallback_layout = get_default_layout_for_role(role)
        role_matched = [entry for entry in layout_entries if entry.id == fallback_layout]
    sub_group_candidates = []
    for sub_group in get_sub_groups_for_group(role):
        sub_group_entries = [
            entry for entry in role_matched if str(entry.sub_group) == sub_group
        ]
        variant_candidates = []
        for variant_id in get_variant_ids_for_sub_group(role, sub_group):
            definition = get_layout_variant_definition(role, sub_group, variant_id)
            variant_layouts = [
                entry.id for entry in sub_group_entries if str(entry.variant_id) == variant_id
            ]
            variant_candidates.append(
                f"`{variant_id}`({definition.label if definition else variant_id}: "
                f"{definition.description if definition else ''} 可用布局 {', '.join(f'`{layout_id}`' for layout_id in variant_layouts) or '无'})"
            )
        layouts_text = " / ".join(variant_candidates) or "无"
        sub_group_candidates.append(
            f"`{sub_group}`({get_sub_group_label(role, sub_group)}: "
            f"{get_sub_group_description(role, sub_group)} 可用布局 {layouts_text})"
        )
    role_matched_text = ", ".join(f"`{entry.id}`" for entry in role_matched) or "无角色匹配布局"
    sub_group_text = " / ".join(sub_group_candidates) if sub_group_candidates else "`default`"
    preferred_variants = (
        _rank_group_sub_group_variants(
            role_matched,
            group=role,
            usage_tags=effective_usage,
            rank_layouts_by_usage_fn=rank_layouts_by_usage_fn,
        )
        if effective_usage
        else []
    )
    if preferred_variants:
        preferred_text = ", ".join(
            f"`{variant_id}`({label})"
            for variant_id, label in preferred_variants
        )
    else:
        preferred_text = "无明确 usage 候选，按结构和设计方向选择"

    return (
        f"- 第{slide_number}页: {item['title']} "
        f"(角色: {role}, "
        f"候选子组: {sub_group_text}, "
        f"要点: {preview_points}{hints_text}, "
        f"页内 Usage: {usage_text}, "
        f"角色匹配布局: {role_matched_text}, "
        f"优先候选变体: {preferred_text})"
    )


async def stage_generate_slides(
    state: PipelineState,
    per_slide_timeout: float,
    progress: ProgressHook | None = None,
    on_slide: SlideHook | None = None,
) -> None:
    if progress:
        await progress("slides", 4, TOTAL_STEPS, "生成幻灯片...")

    from app.services.agents.slide_generator import generate_slide_content

    outline_items = state.outline.get("items", [])
    layout_map = {sel["slide_number"]: sel["layout_id"] for sel in state.layout_selections}

    semaphore = asyncio.Semaphore(5)
    results: list[dict[str, Any]] = [{}] * len(outline_items)
    failed: list[int] = []

    async def generate_one(idx: int, item: dict[str, Any]) -> None:
        async with semaphore:
            slide_num = item["slide_number"]
            layout_id = layout_map.get(slide_num, "bullet-with-icons")

            source_content = _extract_slide_context(
                raw_content=state.raw_content,
                title=item.get("title", ""),
                content_brief=item.get("content_brief", ""),
                key_points=item.get("key_points", []),
                slide_index=idx,
                total_slides=max(1, len(outline_items)),
            )

            try:
                coro = generate_slide_content(
                    layout_id=layout_id,
                    slide_number=slide_num,
                    title=item["title"],
                    content_brief=item.get("content_brief", ""),
                    key_points=item.get("key_points", []),
                    source_content=source_content,
                    job_id=state.job_id,
                    stage="slides",
                )
                content_data = await asyncio.wait_for(coro, timeout=per_slide_timeout)
                results[idx] = {
                    "slide_number": slide_num,
                    "layout_id": layout_id,
                    "content_data": content_data,
                }
            except asyncio.TimeoutError:
                failed.append(idx)
                logger.warning(
                    "Slide %d timed out, using fallback",
                    slide_num,
                    extra={
                        "job_id": state.job_id,
                        "stage": "slides",
                        "slide_index": idx,
                        "layout_id": layout_id,
                        "fallback": True,
                        "fallback_reason": "slide_timeout",
                        "error_type": "timeout",
                    },
                )
                results[idx] = {
                    "slide_number": slide_num,
                    "layout_id": layout_id,
                    "content_data": _fallback_content(item, layout_id),
                }
            except Exception as e:
                failed.append(idx)
                logger.warning(
                    "Slide %d generation failed: %s",
                    slide_num,
                    e,
                    extra={
                        "job_id": state.job_id,
                        "stage": "slides",
                        "slide_index": idx,
                        "layout_id": layout_id,
                        "fallback": True,
                        "fallback_reason": "slide_exception",
                        "error_type": type(e).__name__,
                    },
                )
                results[idx] = {
                    "slide_number": slide_num,
                    "layout_id": layout_id,
                    "content_data": _fallback_content(item, layout_id),
                }

            slide = Slide(
                slideId=f"slide-{slide_num}",
                layoutType=results[idx].get("layout_id", "bullet-with-icons"),
                layoutId=results[idx].get("layout_id", "bullet-with-icons"),
                contentData=results[idx].get("content_data", {}),
                components=[],
            )

            if on_slide:
                await on_slide(
                    {
                        "slide_index": idx,
                        "slide": slide.model_dump(mode="json", by_alias=True),
                    }
                )

            if progress:
                await progress("slides", 4, TOTAL_STEPS, f"生成第 {idx + 1}/{len(outline_items)} 页...")

    await asyncio.gather(*(generate_one(i, item) for i, item in enumerate(outline_items)))

    state.slide_contents = results
    state.failed_slide_indices = sorted(set(failed))


async def stage_resolve_assets(state: PipelineState, progress: ProgressHook | None = None) -> None:
    if progress:
        await progress("assets", 5, TOTAL_STEPS, "\u5904\u7406\u8d44\u6e90...")

    slides: list[Slide] = []
    for sc in state.slide_contents:
        layout_id = sc.get("layout_id", "bullet-with-icons")
        content_data = sc.get("content_data", {})
        if isinstance(content_data, dict):
            content_data = normalize_image_content_data(layout_id, content_data)

        slide = Slide(
            slideId=f"slide-{sc['slide_number']}",
            layoutType=layout_id,
            layoutId=layout_id,
            contentData=content_data,
            components=[],
        )
        slides.append(slide)
    state.slides = slides

async def stage_verify_slides(
    state: PipelineState,
    progress: ProgressHook | None = None,
    enable_vision: bool = True,
    vision_timeout_seconds: float | None = None,
    aesthetic_timeout_seconds: float | None = None,
) -> None:
    if progress:
        await progress("verify", 6, TOTAL_STEPS, "验证布局质量...")

    from app.services.agents.layout_verifier import run_aesthetic_verification, verify_programmatic

    issues = []
    for issue in verify_programmatic(state.slides):
        issue_dict = issue.model_dump(mode="json")
        issue_dict["source"] = issue_dict.get("source") or "programmatic"
        severity = str(issue_dict.get("severity") or "warning").lower()
        issue_dict["tier"] = "hard" if severity == "error" else "advisory"
        issues.append(issue_dict)

    if enable_vision and state.slides:
        if vision_timeout_seconds is None or aesthetic_timeout_seconds is None:
            from app.core.config import settings

            verify_timeout = float(settings.verify_timeout_seconds)
            if vision_timeout_seconds is None:
                vision_timeout_seconds = min(
                    max(5.0, verify_timeout * 0.6),
                    max(1.0, verify_timeout - 1.0),
                )
            if aesthetic_timeout_seconds is None:
                aesthetic_timeout_seconds = min(
                    max(5.0, vision_timeout_seconds * 1.25),
                    max(1.0, verify_timeout - 1.0),
                )
        presentation_dict = {
            "presentationId": "verification-temp",
            "title": state.topic or "演示文稿",
            "slides": [s.model_dump(mode="json", by_alias=True) for s in state.slides],
        }
        try:
            if aesthetic_timeout_seconds and aesthetic_timeout_seconds > 0:
                aesthetic = await asyncio.wait_for(
                    run_aesthetic_verification(
                        state.slides,
                        presentation_dict=presentation_dict,
                        vision_timeout_seconds=vision_timeout_seconds,
                    ),
                    timeout=aesthetic_timeout_seconds,
                )
            else:
                aesthetic = await run_aesthetic_verification(
                    state.slides,
                    presentation_dict=presentation_dict,
                    vision_timeout_seconds=vision_timeout_seconds,
                )
        except asyncio.TimeoutError:
            logger.warning(
                "Aesthetic verification exceeded %.1fs and was skipped to keep verify stage healthy",
                aesthetic_timeout_seconds or 0.0,
            )
            issues.append(
                {
                    "slide_id": state.slides[0].slide_id,
                    "severity": "warning",
                    "category": "aesthetic",
                    "message": "审美校验耗时过长，已跳过以避免 verify 阶段整体超时",
                    "suggestion": "减少页数、降低视觉评估复杂度，或延长 verify 超时预算",
                    "source": "aesthetic_timeout_fallback",
                    "tier": "advisory",
                }
            )
            aesthetic = None
        if aesthetic:
            for issue in aesthetic.issues:
                issue_dict = issue.model_dump(mode="json")
                severity = str(issue_dict.get("severity") or "warning").lower()
                # 视觉问题统一降级为 advisory，避免误触发自动修复链路
                if severity == "error":
                    issue_dict["severity"] = "warning"
                issue_dict["source"] = issue_dict.get("source") or "vision"
                issue_dict["tier"] = "advisory"
                issues.append(issue_dict)

    state.verification_issues = issues


async def stage_fix_slides_once(
    state: PipelineState,
    per_slide_timeout: float,
    progress: ProgressHook | None = None,
    on_slide: SlideHook | None = None,
    target_slide_ids: set[str] | None = None,
) -> None:
    if progress:
        await progress("fix", 6, TOTAL_STEPS, "修复存在问题的页面...")

    from app.services.agents.slide_generator import generate_slide_content

    if target_slide_ids is not None:
        error_slide_ids = {sid for sid in target_slide_ids if sid}
    else:
        error_slide_ids = {
            issue.get("slide_id")
            for issue in state.verification_issues
            if issue.get("severity") == "error" and issue.get("slide_id")
        }
    if not error_slide_ids:
        return

    layout_map = {sel["slide_number"]: sel["layout_id"] for sel in state.layout_selections}
    outline_items = state.outline.get("items", [])

    for idx, slide in enumerate(state.slides):
        if slide.slide_id not in error_slide_ids:
            continue

        slide_num = idx + 1
        item = next((it for it in outline_items if it["slide_number"] == slide_num), None)
        if item is None:
            continue

        layout_id = layout_map.get(slide_num, slide.layout_id or "bullet-with-icons")
        source_content = _extract_slide_context(
            raw_content=state.raw_content,
            title=item.get("title", ""),
            content_brief=item.get("content_brief", ""),
            key_points=item.get("key_points", []),
            slide_index=idx,
            total_slides=max(1, len(state.slides)),
        )

        try:
            coro = generate_slide_content(
                layout_id=layout_id,
                slide_number=slide_num,
                title=item["title"],
                content_brief=item.get("content_brief", ""),
                key_points=item.get("key_points", []),
                source_content=source_content,
                job_id=state.job_id,
                stage="fix",
            )
            content_data = await asyncio.wait_for(coro, timeout=per_slide_timeout)
        except Exception as e:
            logger.warning(
                "Slide %d fix generation failed, using fallback",
                slide_num,
                extra={
                    "job_id": state.job_id,
                    "stage": "fix",
                    "slide_index": idx,
                    "layout_id": layout_id,
                    "fallback": True,
                    "fallback_reason": "fix_exception",
                    "error_type": type(e).__name__,
                },
            )
            content_data = _fallback_content(item, layout_id)

        if idx < len(state.slide_contents):
            state.slide_contents[idx] = {
                "slide_number": slide_num,
                "layout_id": layout_id,
                "content_data": content_data,
            }

        patched = Slide(
            slideId=f"slide-{slide_num}",
            layoutType=layout_id,
            layoutId=layout_id,
            contentData=content_data,
            components=[],
        )
        state.slides[idx] = patched

        if on_slide:
            await on_slide(
                {
                    "slide_index": idx,
                    "slide": patched.model_dump(mode="json", by_alias=True),
                }
            )

def _rank_group_sub_group_variants(
    layout_entries: list[Any],
    *,
    group: str,
    usage_tags: tuple[str, ...],
    rank_layouts_by_usage_fn,
) -> list[tuple[str, str]]:
    matched = [entry for entry in layout_entries if str(entry.group) == group]
    ranked_layouts = (
        rank_layouts_by_usage_fn(matched, usage_tags, limit=len(matched)) if usage_tags else matched
    )
    seen: set[str] = set()
    ranked_variants: list[tuple[str, str]] = []
    for entry in ranked_layouts:
        if entry.variant_id in seen:
            continue
        seen.add(entry.variant_id)
        ranked_variants.append((entry.variant_id, entry.variant_label))
    return ranked_variants


def _log_outline_role_diagnostics(
    *,
    job_id: str,
    raw_items: list[dict[str, Any]],
    normalized_items: list[dict[str, Any]],
) -> None:
    for idx, item in enumerate(normalized_items):
        raw_item = raw_items[idx] if idx < len(raw_items) and isinstance(raw_items[idx], dict) else {}
        raw_role = str(
            raw_item.get("suggested_slide_role") or raw_item.get("suggested_layout_category") or ""
        )
        normalized_role = str(item.get("suggested_slide_role") or "")
        logger.info(
            "Outline role resolved",
            extra={
                "job_id": job_id,
                "stage": "outline",
                "slide_number": item.get("slide_number"),
                "title": str(item.get("title") or ""),
                "raw_role": raw_role,
                "normalized_role": normalized_role,
                "role_changed": raw_role != normalized_role,
                "key_point_count": len(item.get("key_points") or []),
                "source_reference_count": len(item.get("source_references") or []),
            },
        )


def _log_layout_selection_diagnostics(
    *,
    job_id: str,
    outline_items: list[dict[str, Any]],
    selections: list[dict[str, Any]],
    decision_traces: dict[int, dict[str, Any]],
    document_usage_tags: tuple[str, ...],
    slide_usage_tags: dict[int, tuple[str, ...]],
) -> None:
    item_by_slide = {
        int(item.get("slide_number")): item
        for item in outline_items
        if isinstance(item.get("slide_number"), int)
    }
    for selection in selections:
        slide_number = selection.get("slide_number")
        if not isinstance(slide_number, int):
            continue
        item = item_by_slide.get(slide_number, {})
        trace = decision_traces.get(slide_number, {})
        effective_usage = tuple(trace.get("effective_usage_tags") or []) or (
            slide_usage_tags.get(slide_number, ()) or document_usage_tags
        )
        pre_diversity_layout_id = str(trace.get("pre_diversity_layout_id") or selection.get("layout_id") or "")
        final_layout_id = str(selection.get("layout_id") or "")
        logger.info(
            "Layout decision resolved",
            extra={
                "job_id": job_id,
                "stage": "layout",
                "slide_number": slide_number,
                "title": str(item.get("title") or ""),
                "outline_role": str(item.get("suggested_slide_role") or selection.get("group") or ""),
                "selection_source": str(trace.get("selection_source") or "unknown"),
                "requested_group": str(trace.get("requested_group") or ""),
                "resolved_group": str(trace.get("resolved_group") or selection.get("group") or ""),
                "requested_sub_group": str(trace.get("requested_sub_group") or ""),
                "resolved_sub_group": str(trace.get("resolved_sub_group") or selection.get("sub_group") or ""),
                "requested_variant_id": str(trace.get("requested_variant_id") or ""),
                "resolved_variant_id": str(trace.get("resolved_variant_id") or selection.get("variant_id") or ""),
                "pre_diversity_layout_id": pre_diversity_layout_id,
                "final_layout_id": final_layout_id,
                "diversity_adjusted": pre_diversity_layout_id != final_layout_id,
                "effective_usage_tags": list(effective_usage),
                "reason": str(selection.get("reason") or ""),
                "content_signal_primary": trace.get("content_signal_primary") or {},
                "content_signal_shadow": trace.get("content_signal_shadow"),
                "confidence": float(trace.get("confidence") or 0.0),
                "signal_source": str(trace.get("signal_source") or "fallback"),
                "used_safety_default": bool(trace.get("used_safety_default") or False),
            },
        )


def _finalize_layout_selections(
    *,
    selections: list[dict[str, Any]],
    job_id: str,
    outline_items: list[dict[str, Any]],
    decision_traces: dict[int, dict[str, Any]],
    document_usage_tags: tuple[str, ...],
    slide_usage_tags: dict[int, tuple[str, ...]],
    layout_entries: list[Any],
    rank_layouts_by_usage_fn,
) -> list[dict[str, Any]]:
    finalized = _enforce_adjacent_layout_diversity(
        selections,
        document_usage_tags=document_usage_tags,
        slide_usage_tags=slide_usage_tags,
        layout_entries=layout_entries,
        rank_layouts_by_usage_fn=rank_layouts_by_usage_fn,
    )
    _log_layout_selection_diagnostics(
        job_id=job_id,
        outline_items=outline_items,
        selections=finalized,
        decision_traces=decision_traces,
        document_usage_tags=document_usage_tags,
        slide_usage_tags=slide_usage_tags,
    )
    return finalized


def _rank_group_sub_group_variant_layouts(
    layout_entries: list[Any],
    *,
    group: str,
    sub_group: str,
    variant_id: str,
    usage_tags: tuple[str, ...],
    rank_layouts_by_usage_fn,
) -> list[Any]:
    from app.services.pipeline.layout_roles import get_default_layout_for_role

    variant_matched = [
        entry
        for entry in layout_entries
        if str(entry.group) == group
        and str(entry.sub_group) == sub_group
        and str(entry.variant_id) == variant_id
    ]
    if not variant_matched:
        variant_matched = [
            entry
            for entry in layout_entries
            if str(entry.group) == group and str(entry.sub_group) == sub_group
        ]
    if not variant_matched:
        variant_matched = [entry for entry in layout_entries if str(entry.group) == group]
    if not variant_matched:
        fallback_layout = get_default_layout_for_role(group)
        variant_matched = [entry for entry in layout_entries if entry.id == fallback_layout]

    if usage_tags:
        ranked = rank_layouts_by_usage_fn(
            variant_matched,
            usage_tags,
            limit=len(variant_matched),
        )
        if ranked:
            return ranked
    return variant_matched


def _rank_sibling_layouts_for_repeat_guard(
    layout_entries: list[Any],
    *,
    group: str,
    sub_group: str,
    usage_tags: tuple[str, ...],
    rank_layouts_by_usage_fn,
) -> list[Any]:
    matched = [
        entry
        for entry in layout_entries
        if str(entry.group) == group and str(entry.sub_group) == sub_group
    ]
    if not matched:
        return []

    if usage_tags:
        ranked = rank_layouts_by_usage_fn(
            matched,
            usage_tags,
            limit=len(matched),
        )
        if ranked:
            ranked_ids = {entry.id for entry in ranked}
            return ranked + [entry for entry in matched if entry.id not in ranked_ids]

    return matched


def _enforce_adjacent_layout_diversity(
    selections: list[dict[str, Any]],
    *,
    document_usage_tags: tuple[str, ...],
    slide_usage_tags: dict[int, tuple[str, ...]],
    layout_entries: list[Any],
    rank_layouts_by_usage_fn,
) -> list[dict[str, Any]]:
    if len(selections) < 2:
        return selections

    adjusted = [dict(selection) for selection in selections]
    ordered_indexes = sorted(
        range(len(adjusted)),
        key=lambda idx: (
            adjusted[idx]["slide_number"]
            if isinstance(adjusted[idx].get("slide_number"), int)
            else idx + 1,
            idx,
        ),
    )
    previous_selection: dict[str, Any] | None = None

    for idx in ordered_indexes:
        selection = adjusted[idx]
        current_layout_id = str(selection.get("layout_id") or "")
        current_group = str(selection.get("group") or "")
        current_sub_group = str(selection.get("sub_group") or "default")

        if previous_selection is None:
            previous_selection = selection
            continue

        previous_layout_id = str(previous_selection.get("layout_id") or "")
        if (
            not current_layout_id
            or current_layout_id != previous_layout_id
            or current_group in _ADJACENT_LAYOUT_DIVERSITY_EXEMPT_GROUPS
        ):
            previous_selection = selection
            continue

        slide_number = selection.get("slide_number")
        effective_usage = (
            slide_usage_tags.get(slide_number, ())
            if isinstance(slide_number, int)
            else ()
        ) or document_usage_tags
        sibling_entries = _rank_sibling_layouts_for_repeat_guard(
            layout_entries,
            group=current_group,
            sub_group=current_sub_group,
            usage_tags=effective_usage,
            rank_layouts_by_usage_fn=rank_layouts_by_usage_fn,
        )
        replacement = next(
            (
                entry
                for entry in sibling_entries
                if entry.id not in {current_layout_id, previous_layout_id}
            ),
            None,
        )
        if replacement is None:
            previous_selection = selection
            continue

        selection["layout_id"] = replacement.id
        selection["variant_id"] = replacement.variant_id
        selection["design_traits"] = _serialize_design_traits_from_entry(replacement)
        reason = str(selection.get("reason") or "").strip()
        diversity_reason = f"adjusted to avoid adjacent layout repeat from {current_layout_id}"
        selection["reason"] = f"{reason}; {diversity_reason}" if reason else diversity_reason
        previous_selection = selection

    return adjusted


def _resolve_layout_sub_group(
    item: dict[str, Any],
    *,
    role: str,
    requested_sub_group: str,
    content_signal_primary: Mapping[str, Any] | None = None,
) -> str:
    from app.services.pipeline.layout_roles import is_variant_pilot_role
    from app.services.pipeline.layout_taxonomy import get_sub_groups_for_group

    allowed_sub_groups = set(get_sub_groups_for_group(role))
    if not is_variant_pilot_role(role) or not allowed_sub_groups:
        return "default"

    hinted = _hinted_sub_group(item, role)
    if hinted and hinted in allowed_sub_groups:
        return hinted
    if requested_sub_group in allowed_sub_groups:
        return requested_sub_group
    if isinstance(content_signal_primary, Mapping):
        signal_sub_group = str(content_signal_primary.get("suggested_sub_group") or "")
        if signal_sub_group in allowed_sub_groups:
            return signal_sub_group

    return _suggest_sub_group_for_outline_item(item, role)


def _resolve_layout_variant(
    item: dict[str, Any],
    *,
    role: str,
    sub_group: str,
    requested_variant_id: str,
    usage_tags: tuple[str, ...],
) -> str:
    from app.services.pipeline.layout_taxonomy import get_variant_ids_for_sub_group

    allowed_variants = tuple(get_variant_ids_for_sub_group(role, sub_group))
    if not allowed_variants:
        return _group_sub_group_to_default_variant(role, sub_group)
    hinted = _hinted_variant(item, role, sub_group)
    if hinted and hinted in allowed_variants:
        return hinted
    if requested_variant_id in allowed_variants:
        return requested_variant_id
    return _suggest_variant_for_outline_item(item, role, sub_group, usage_tags, allowed_variants)


def _suggest_sub_group_for_outline_item(item: dict[str, Any], role: str) -> str:
    title = str(item.get("title") or "").lower()
    content_brief = str(item.get("content_brief") or "").lower()
    key_points = [
        str(point).strip().lower()
        for point in item.get("key_points", [])
        if isinstance(point, str) and point.strip()
    ]
    key_point_text = "\n".join(key_points)
    combined = "\n".join([title, content_brief, key_point_text])

    if role == "narrative":
        has_visual_signal = any(token in combined for token in _VISUAL_EXPLAINER_KEYWORDS)
        has_strong_visual_signal = any(
            token in combined for token in _VISUAL_EXPLAINER_STRONG_KEYWORDS
        )
        has_capability_signal = len(key_points) >= 4 or any(
            token in combined for token in _CAPABILITY_GRID_KEYWORDS
        )

        if has_capability_signal and (not has_visual_signal or not has_strong_visual_signal):
            return "capability-grid"

        if has_visual_signal:
            return "visual-explainer"

        return "icon-points"

    if role == "evidence":
        if any(token in combined for token in _TABLE_MATRIX_KEYWORDS):
            return "table-matrix"
        if any(token in combined for token in _CHART_ANALYSIS_KEYWORDS):
            return "chart-analysis"
        if any(token in combined for token in _EVIDENCE_VISUAL_KEYWORDS):
            return "visual-evidence"
        return "stat-summary"

    if role == "comparison":
        if any(token in combined for token in _RESPONSE_MAPPING_KEYWORDS):
            return "response-mapping"
        return "side-by-side"

    if role == "process":
        if any(token in combined for token in _TIMELINE_KEYWORDS):
            return "timeline-milestone"
        return "step-flow"

    return "default"


def _suggest_variant_for_outline_item(
    item: dict[str, Any],
    role: str,
    sub_group: str,
    usage_tags: tuple[str, ...],
    allowed_variants: tuple[str, ...],
) -> str:
    title = str(item.get("title") or "").lower()
    content_brief = str(item.get("content_brief") or "").lower()
    key_points = [
        str(point).strip().lower()
        for point in item.get("key_points", [])
        if isinstance(point, str) and point.strip()
    ]
    combined = "\n".join([title, content_brief, "\n".join(key_points)])

    def choose(default_variant: str, alternative_variant: str, condition: bool) -> str:
        if alternative_variant in allowed_variants and condition:
            return alternative_variant
        if default_variant in allowed_variants:
            return default_variant
        return allowed_variants[0]

    if role == "cover" and sub_group == "default":
        return choose(
            "title-centered",
            "title-left",
            bool(content_brief.strip()) or len(title) >= 18 or len(key_points) >= 3,
        )

    if role == "agenda" and sub_group == "default":
        return choose(
            "section-cards",
            "chapter-rail",
            len(key_points) >= 5 or "阶段" in combined or "路径" in combined,
        )

    if role == "section-divider" and sub_group == "default":
        return choose(
            "centered-divider",
            "side-label",
            bool(content_brief.strip()) or "part" in combined or "阶段" in combined,
        )

    if role == "narrative" and sub_group == "icon-points":
        return choose(
            "icon-pillars",
            "feature-cards",
            "功能" in combined
            or "模块" in combined
            or "能力" in combined
            or "product-demo" in usage_tags
            or "sales-pitch" in usage_tags,
        )

    if role == "evidence" and sub_group == "stat-summary":
        summary_band_tokens = (
            "摘要",
            "总览",
            "总述",
            "executive summary",
            "one-line summary",
            "一句话",
        )
        return choose(
            "kpi-grid",
            "summary-band",
            "investor-pitch" in usage_tags
            or "sales-pitch" in usage_tags
            or any(token in combined for token in summary_band_tokens),
        )

    if role == "process" and sub_group == "step-flow":
        return choose(
            "numbered-steps",
            "progress-track",
            "阶段" in combined
            or "推进" in combined
            or "rollout" in combined
            or "project-status" in usage_tags,
        )

    if role == "highlight" and sub_group == "default":
        return choose(
            "quote-focus",
            "banner-highlight",
            not ("引用" in combined or "作者" in combined or "quote" in combined),
        )

    if role == "closing" and sub_group == "default":
        return choose(
            "closing-center",
            "contact-card",
            "contact" in combined or "联系" in combined or "邮箱" in combined or "sales-pitch" in usage_tags,
        )

    return _group_sub_group_to_default_variant(role, sub_group)


def _serialize_design_traits_from_entry(entry: Any) -> dict[str, str]:
    if entry is None:
        return {"tone": "", "style": "", "density": ""}
    return {
        "tone": str(entry.design_traits.tone),
        "style": str(entry.design_traits.style),
        "density": str(entry.design_traits.density),
    }


def _role_to_default_layout(role: str) -> str:
    from app.services.pipeline.layout_roles import get_default_layout_for_role

    return get_default_layout_for_role(role)


def _extract_slide_context(
    raw_content: str,
    title: str,
    content_brief: str,
    key_points: list[str],
    slide_index: int,
    total_slides: int,
    max_chars: int = _SLIDE_CONTEXT_MAX_CHARS,
) -> str:
    content = (raw_content or "").strip()
    if not content:
        return ""

    paragraphs = [segment.strip() for segment in re.split(r"\n\s*\n+", content) if segment.strip()]
    if len(paragraphs) <= 1:
        return content[:max_chars]

    title_text = str(title or "")
    brief_text = str(content_brief or "")
    query_terms = _collect_query_terms(title_text, brief_text, key_points)
    scored: list[tuple[int, int, str]] = []

    for idx, paragraph in enumerate(paragraphs):
        score = _score_paragraph(paragraph, title_text, brief_text, key_points, query_terms)
        scored.append((score, idx, paragraph))

    matched = [entry for entry in scored if entry[0] > 0]
    if not matched:
        return _slice_content_by_position(content, slide_index, total_slides, max_chars)

    matched.sort(key=lambda item: (-item[0], item[1]))
    top_entries = matched[:6]
    top_entries.sort(key=lambda item: item[1])

    selected: list[str] = []
    size = 0
    for _, _, paragraph in top_entries:
        delta = len(paragraph) + (2 if selected else 0)
        if size + delta > max_chars:
            continue
        selected.append(paragraph)
        size += delta
        if size >= max_chars * 0.85:
            break

    if not selected:
        return _slice_content_by_position(content, slide_index, total_slides, max_chars)
    return "\n\n".join(selected)


def _slice_content_by_position(content: str, slide_index: int, total_slides: int, max_chars: int) -> str:
    if len(content) <= max_chars:
        return content
    denominator = max(1, total_slides - 1)
    ratio = min(max(slide_index, 0), denominator) / denominator
    anchor = int((len(content) - max_chars) * ratio)
    start = max(0, min(anchor, len(content) - max_chars))
    end = start + max_chars
    return content[start:end]


def _collect_query_terms(title: str, content_brief: str, key_points: list[str]) -> list[str]:
    terms: list[str] = []
    candidates = [title, content_brief, *key_points]
    for text in candidates:
        if not text:
            continue
        trimmed = text.strip()
        if len(trimmed) >= 2:
            terms.append(trimmed.lower())
        pieces = re.split(r"[\s,，。;；:：/|()（）【】\\-]+", trimmed)
        for piece in pieces:
            token = piece.strip().lower()
            if len(token) >= 2:
                terms.append(token)
    deduped: list[str] = []
    for term in terms:
        if term and term not in deduped:
            deduped.append(term)
    return deduped


def _score_paragraph(
    paragraph: str,
    title: str,
    content_brief: str,
    key_points: list[str],
    query_terms: list[str],
) -> int:
    haystack = paragraph.lower()
    score = 0

    title_text = title.strip().lower()
    if title_text and title_text in haystack:
        score += 8

    brief_text = content_brief.strip().lower()
    if brief_text and brief_text in haystack:
        score += 4

    for point in key_points:
        point_text = point.strip().lower()
        if point_text and point_text in haystack:
            score += 3

    for term in query_terms:
        if term in haystack:
            score += 1
    return score


def _normalize_fallback_points(raw_points: Any) -> list[str]:
    if not isinstance(raw_points, list):
        return []
    points: list[str] = []
    for value in raw_points:
        text = str(value).strip() if value is not None else ""
        if text:
            points.append(text)
    return points


def _is_placeholder_point(text: str) -> bool:
    return is_placeholder_text(text)


def _bullet_with_icons_fallback(item_title: str, points: list[str]) -> dict[str, Any]:
    meaningful_points = [point for point in points if not _is_placeholder_point(point)]
    if not meaningful_points:
        return {
            "title": item_title,
            "items": [],
            "status": get_bullet_fallback_status(),
        }

    items = meaningful_points[:4]
    return {
        "title": item_title,
        "items": [
            {
                "icon": {"query": "star"},
                "title": point[:25],
                "description": point,
            }
            for point in items
        ],
    }



def _fallback_content(item: dict[str, Any], layout_id: str) -> dict[str, Any]:
    title = item.get("title", "幻灯片")
    points = _normalize_fallback_points(item.get("key_points"))

    if layout_id in {"intro-slide", "intro-slide-left"}:
        return {"title": title, "subtitle": "由知演 AI 智能生成"}
    if layout_id in {"thank-you", "thank-you-contact", "thankyou"}:
        return {"title": "谢谢", "subtitle": "感谢您的关注"}
    if layout_id in {"section-header", "section-header-side"}:
        return {"title": title}
    if layout_id in {"outline-slide", "outline-slide-rail"}:
        sections = points[:10] if points else ["议题概览", "核心内容", "后续安排"]
        while len(sections) < 3:
            sections.append(f"章节 {len(sections) + 1}")
        return {
            "title": title,
            "sections": [
                {"title": section[:24], "description": "自动回退生成"}
                for section in sections
            ],
        }
    if layout_id in {"bullet-with-icons", "bullet-with-icons-cards"}:
        return _bullet_with_icons_fallback(title, points)
    if layout_id in {"numbered-bullets", "numbered-bullets-track"}:
        items = points[:5] if points else [CONTENT_GENERATING]
        while len(items) < 3:
            items.append(CONTENT_GENERATING)
        return {
            "title": title,
            "items": [{"title": f"要点 {i + 1}", "description": p} for i, p in enumerate(items)],
        }
    if layout_id in {"metrics-slide", "metrics-slide-band"}:
        metrics = points[:3] if points else [CONTENT_GENERATING, CONTENT_GENERATING]
        if len(metrics) < 2:
            metrics.append(CONTENT_GENERATING)
        conclusion = points[0] if points else f"{title}的核心指标整体可读。"
        conclusion_brief = (
            points[1]
            if len(points) > 1
            else "详细指标如下，可作为结论的量化支撑。"
        )
        return {
            "title": title,
            "conclusion": conclusion,
            "conclusionBrief": conclusion_brief,
            "metrics": [
                {"value": f"{(i + 1) * 10}%", "label": f"指标 {i + 1}", "description": p}
                for i, p in enumerate(metrics)
            ],
        }
    if layout_id == "metrics-with-image":
        metrics = points[:3] if points else [CONTENT_GENERATING, CONTENT_GENERATING]
        if len(metrics) < 2:
            metrics.append(CONTENT_GENERATING)
        return {
            "title": title,
            "metrics": [
                {"value": f"{(i + 1) * 10}%", "label": f"指标 {i + 1}", "description": p}
                for i, p in enumerate(metrics)
            ],
            "image": {
                "source": "ai",
                "prompt": "modern office presentation setting",
            },
        }
    if layout_id == "chart-with-bullets":
        bullets = points[:4] if points else [CONTENT_GENERATING, CONTENT_GENERATING]
        while len(bullets) < 2:
            bullets.append(CONTENT_GENERATING)
        return {
            "title": title,
            "chart": {
                "chart_type": "bar",
                "labels": ["A", "B", "C"],
                "datasets": [{"label": "指标", "data": [60, 75, 90], "color": "#3b82f6"}],
            },
            "bullets": [{"text": text} for text in bullets],
        }
    if layout_id == "table-info":
        rows = [[f"项{i + 1}", points[i] if i < len(points) else CONTENT_GENERATING] for i in range(3)]
        return {
            "title": title,
            "headers": ["主题", "说明"],
            "rows": rows,
            "caption": f"{FALLBACK_GENERATED}内容",
        }
    if layout_id == "two-column-compare":
        candidates = points[:6] if points else [CONTENT_GENERATING, CONTENT_GENERATING]
        if len(candidates) < 2:
            candidates.append(CONTENT_GENERATING)
        mid = max(1, (len(candidates) + 1) // 2)
        left_items = candidates[:mid] or [CONTENT_GENERATING]
        right_items = candidates[mid:] or [CONTENT_GENERATING]
        return {
            "title": title,
            "left": {"heading": "要点 A", "items": left_items, "icon": {"query": "layers"}},
            "right": {"heading": "要点 B", "items": right_items, "icon": {"query": "target"}},
        }
    if layout_id == "image-and-description":
        return {
            "title": title,
            "image": {
                "source": "ai",
                "prompt": "business presentation illustration",
            },
            "description": points[0] if points else CONTENT_GENERATING,
            "bullets": points[:3],
        }
    if layout_id == "timeline":
        events = points[:4] if points else [CONTENT_GENERATING, CONTENT_GENERATING, CONTENT_GENERATING]
        while len(events) < 3:
            events.append(CONTENT_GENERATING)
        return {
            "title": title,
            "events": [
                {"date": f"阶段 {i + 1}", "title": event, "description": FALLBACK_GENERATED}
                for i, event in enumerate(events)
            ],
        }
    if layout_id in {"quote-slide", "quote-banner"}:
        return {"quote": points[0] if points else title}
    if layout_id == "bullet-icons-only":
        labels = points[:6] if points else ["能力 1", "能力 2", "能力 3", "能力 4"]
        while len(labels) < 4:
            labels.append(f"能力 {len(labels) + 1}")
        return {
            "title": title,
            "items": [{"icon": {"query": "sparkles"}, "label": label[:20]} for label in labels],
        }
    if layout_id == "challenge-outcome":
        pairs = points[:4] if points else [CONTENT_GENERATING, CONTENT_GENERATING]
        while len(pairs) < 2:
            pairs.append(CONTENT_GENERATING)
        return {
            "title": title,
            "items": [{"challenge": text, "outcome": "建议下一步行动"} for text in pairs],
        }

    # Unknown layout falls back to a known-safe bullet schema.
    fallback_items = points[:4] if points else [CONTENT_GENERATING, CONTENT_GENERATING, CONTENT_GENERATING]
    while len(fallback_items) < 3:
        fallback_items.append(CONTENT_GENERATING)
    return {
        "title": title,
        "items": [
            {"icon": {"query": "star"}, "title": p[:25], "description": p}
            for p in fallback_items
        ],
    }

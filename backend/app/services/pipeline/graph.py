"""Pipeline stages for generation v2.

Flow:
  parse -> outline -> layout -> slides -> assets -> verify -> fix(optional)
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.models.slide import Slide

logger = logging.getLogger(__name__)

TOTAL_STEPS = 6
_SLIDE_CONTEXT_MAX_CHARS = 2000
_VISUAL_EXPLAINER_KEYWORDS = (
    "图片",
    "配图",
    "图文",
    "案例",
    "场景",
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
    "grid",
    "matrix",
    "capability map",
    "feature set",
    "stack",
)

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
    from app.services.document.parser import estimate_tokens

    if progress:
        await progress("parse", 1, TOTAL_STEPS, "解析文档...")

    content = state.raw_content or ""
    token_count = estimate_tokens(content)
    heading_count = sum(1 for line in content.split("\n") if line.startswith("#"))

    state.document_metadata = {
        "char_count": len(content),
        "estimated_tokens": token_count,
        "heading_count": heading_count,
    }

    logger.info(
        "ParseDocument: %d chars, ~%d tokens, %d headings",
        len(content),
        token_count,
        heading_count,
        extra={"job_id": state.job_id, "stage": "parse"},
    )


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

    prompt = (
        f"演示文稿主题：{state.topic or '综合演示'}\n"
        f"目标页数：{state.num_pages} 页\n\n"
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
        outline["items"] = normalize_outline_items_roles(
            outline.get("items", []),
            num_pages=state.num_pages,
        )
        state.outline = outline
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
        get_layout_catalog,
        get_layout_ids,
        get_layout_variant_catalog,
    )
    from app.services.pipeline.layout_roles import (
        get_layout_role,
        get_outline_item_role,
        normalize_outline_items_roles,
    )
    from app.services.pipeline.layout_variants import (
        get_layout_variant,
        normalize_layout_variant,
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
    valid_ids = set(get_layout_ids())
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
    prompt = (
        f"可用布局列表:\n{get_layout_catalog()}\n\n"
        f"变体轨道:\n{get_layout_variant_catalog()}\n\n"
        f"文档级 Usage 推断: {document_usage_text}\n"
        "选择规则:\n"
        "- 必须先满足每页的 suggested_slide_role 页面角色，并把它作为 group 输出\n"
        "- 先确定 group，再确定 variant，最后再输出 layout_id\n"
        "- narrative 必须显式选择 icon-points / visual-explainer / capability-grid 之一\n"
        "- 非 narrative group 统一使用 variant=default\n"
        "- 优先选择 usage 匹配且结构匹配的 layout_id\n"
        "- 若 usage 匹配不足但结构明显更合适，可越过 usage\n"
        "- 当 usage 未命中时，按内容结构与叙事节奏选择\n\n"
        f"大纲:\n{items_text}\n\n"
        "请为每页输出 group、variant、layout_id 和 reason。"
    )

    try:
        from app.core.config import settings
        from app.services.agents.layout_selector import layout_selector_agent

        result = await layout_selector_agent.run(prompt)
        usage = result.usage()
        selections = result.output.model_dump()["slides"]

        for sel in selections:
            item = next((it for it in outline_items if it["slide_number"] == sel["slide_number"]), None)
            role = get_outline_item_role(item or {})
            effective_usage = slide_usage_tags.get(sel["slide_number"], ()) or document_usage_tags
            requested_variant = normalize_layout_variant(str(sel.get("variant") or "default"))
            resolved_variant = _resolve_layout_variant(
                item or {},
                role=role,
                requested_variant=requested_variant,
                requested_layout_id=str(sel.get("layout_id") or ""),
            )
            candidate_entries = _rank_role_variant_layouts(
                layout_entries,
                role=role,
                variant=resolved_variant,
                usage_tags=effective_usage,
                rank_layouts_by_usage_fn=rank_layouts_by_usage,
            )
            candidate_ids = {entry.id for entry in candidate_entries}
            requested_layout_id = str(sel.get("layout_id") or "")
            if (
                requested_layout_id not in valid_ids
                or requested_layout_id not in candidate_ids
                or get_layout_role(requested_layout_id) != role
                or get_layout_variant(requested_layout_id) != resolved_variant
            ):
                sel["layout_id"] = (
                    candidate_entries[0].id
                    if candidate_entries
                    else _role_variant_to_default_layout(role, resolved_variant)
                )
            else:
                sel["layout_id"] = requested_layout_id

            sel["group"] = role
            sel["variant"] = resolved_variant

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
        state.layout_selections = [
            {
                "slide_number": item["slide_number"],
                "group": get_outline_item_role(item),
                "variant": (
                    resolved_variant := _resolve_layout_variant(
                        item,
                        role=get_outline_item_role(item),
                        requested_variant="default",
                        requested_layout_id="",
                    )
                ),
                "layout_id": _role_variant_to_default_layout(
                    get_outline_item_role(item),
                    resolved_variant,
                ),
                "reason": "fallback",
            }
            for item in outline_items
        ]


def _role_variant_to_default_layout(role: str, variant: str) -> str:
    if role == "narrative":
        if variant == "visual-explainer":
            return "image-and-description"
        if variant == "capability-grid":
            return "bullet-icons-only"
        return "bullet-with-icons"

    return _role_to_default_layout(role)


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
    from app.services.pipeline.layout_variants import (
        get_layout_variant,
        get_layout_variant_description,
        get_layout_variant_label,
        get_variants_for_role,
    )

    slide_number = int(item.get("slide_number", 0))
    key_points = item.get("key_points", [])
    preview_points = ", ".join(str(point) for point in key_points[:3])
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
    preferred = (
        rank_layouts_by_usage_fn(role_matched, effective_usage, limit=4) if effective_usage else []
    )
    variant_candidates = []
    for variant in get_variants_for_role(role):
        variant_entries = [
            entry for entry in role_matched if get_layout_variant(entry.id) == variant
        ]
        layouts_text = ", ".join(f"`{entry.id}`" for entry in variant_entries) or "无"
        variant_candidates.append(
            f"`{variant}`({get_layout_variant_label(role, variant)}: "
            f"{get_layout_variant_description(role, variant)} 可用布局 {layouts_text})"
        )
    role_matched_text = ", ".join(f"`{entry.id}`" for entry in role_matched) or "无角色匹配布局"
    variant_text = " / ".join(variant_candidates) if variant_candidates else "`default`"
    if preferred:
        preferred_text = ", ".join(f"`{entry.id}`({entry.name})" for entry in preferred)
    else:
        preferred_text = "无明确 usage 候选，按结构选择"

    return (
        f"- 第{slide_number}页: {item['title']} "
        f"(角色: {role}, "
        f"候选变体: {variant_text}, "
        f"要点: {preview_points}, "
        f"页内 Usage: {usage_text}, "
        f"角色匹配布局: {role_matched_text}, "
        f"优先候选布局: {preferred_text})"
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
        await progress("assets", 5, TOTAL_STEPS, "处理资源...")

    slides: list[Slide] = []
    for sc in state.slide_contents:
        slide = Slide(
            slideId=f"slide-{sc['slide_number']}",
            layoutType=sc.get("layout_id", "bullet-with-icons"),
            layoutId=sc.get("layout_id", "bullet-with-icons"),
            contentData=sc.get("content_data", {}),
            components=[],
        )
        slides.append(slide)
    state.slides = slides


async def stage_verify_slides(
    state: PipelineState,
    progress: ProgressHook | None = None,
    enable_vision: bool = True,
    vision_timeout_seconds: float | None = None,
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
        if vision_timeout_seconds is None:
            from app.core.config import settings

            verify_timeout = float(settings.verify_timeout_seconds)
            vision_timeout_seconds = min(
                max(5.0, verify_timeout * 0.6),
                max(1.0, verify_timeout - 1.0),
            )
        presentation_dict = {
            "presentationId": "verification-temp",
            "title": state.topic or "演示文稿",
            "slides": [s.model_dump(mode="json", by_alias=True) for s in state.slides],
        }
        aesthetic = await run_aesthetic_verification(
            state.slides,
            presentation_dict=presentation_dict,
            vision_timeout_seconds=vision_timeout_seconds,
        )
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

def _rank_role_variant_layouts(
    layout_entries: list[Any],
    *,
    role: str,
    variant: str,
    usage_tags: tuple[str, ...],
    rank_layouts_by_usage_fn,
) -> list[Any]:
    from app.services.pipeline.layout_roles import get_default_layout_for_role
    from app.services.pipeline.layout_variants import get_layout_variant

    variant_matched = [
        entry
        for entry in layout_entries
        if str(entry.group) == role and get_layout_variant(entry.id) == variant
    ]
    if not variant_matched:
        variant_matched = [entry for entry in layout_entries if str(entry.group) == role]
    if not variant_matched:
        fallback_layout = get_default_layout_for_role(role)
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


def _resolve_layout_variant(
    item: dict[str, Any],
    *,
    role: str,
    requested_variant: str,
    requested_layout_id: str,
) -> str:
    from app.services.pipeline.layout_roles import is_variant_pilot_role
    from app.services.pipeline.layout_variants import get_layout_variant, get_variants_for_role

    if not is_variant_pilot_role(role):
        return "default"

    allowed_variants = set(get_variants_for_role(role))
    if requested_variant in allowed_variants:
        return requested_variant

    if requested_layout_id:
        inferred_variant = get_layout_variant(requested_layout_id)
        if inferred_variant in allowed_variants:
            return inferred_variant

    return _suggest_variant_for_outline_item(item, role)


def _suggest_variant_for_outline_item(item: dict[str, Any], role: str) -> str:
    if role != "narrative":
        return "default"

    title = str(item.get("title") or "").lower()
    content_brief = str(item.get("content_brief") or "").lower()
    key_points = [
        str(point).strip().lower()
        for point in item.get("key_points", [])
        if isinstance(point, str) and point.strip()
    ]
    key_point_text = "\n".join(key_points)
    combined = "\n".join([title, content_brief, key_point_text])

    if any(token in combined for token in _VISUAL_EXPLAINER_KEYWORDS):
        return "visual-explainer"

    if len(key_points) >= 5 or any(token in combined for token in _CAPABILITY_GRID_KEYWORDS):
        return "capability-grid"

    return "icon-points"


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
    return text.strip() in {"内容生成中", "待补充", "自动回退生成"}


def _bullet_with_icons_fallback(item_title: str, points: list[str]) -> dict[str, Any]:
    meaningful_points = [point for point in points if not _is_placeholder_point(point)]
    if not meaningful_points:
        return {
            "title": item_title,
            "items": [],
            "status": {
                "title": "内容暂未就绪",
                "message": "该页正在生成或已回退，可稍后重试。",
            },
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

    if layout_id == "intro-slide":
        return {"title": title, "subtitle": "由知演 AI 智能生成"}
    if layout_id in {"thank-you", "thankyou"}:
        return {"title": "谢谢", "subtitle": "感谢您的关注"}
    if layout_id == "section-header":
        return {"title": title}
    if layout_id == "bullet-with-icons":
        return _bullet_with_icons_fallback(title, points)
    if layout_id == "numbered-bullets":
        items = points[:5] if points else ["内容生成中"]
        while len(items) < 3:
            items.append("内容生成中")
        return {
            "title": title,
            "items": [{"title": f"要点 {i + 1}", "description": p} for i, p in enumerate(items)],
        }
    if layout_id == "metrics-slide":
        metrics = points[:3] if points else ["?????", "?????"]
        if len(metrics) < 2:
            metrics.append("?????")
        conclusion = points[0] if points else f"{title}??????????"
        conclusion_brief = (
            points[1]
            if len(points) > 1
            else "??????????????????"
        )
        return {
            "title": title,
            "conclusion": conclusion,
            "conclusionBrief": conclusion_brief,
            "metrics": [
                {"value": f"{(i + 1) * 10}%", "label": f"?? {i + 1}", "description": p}
                for i, p in enumerate(metrics)
            ],
        }
    if layout_id == "metrics-with-image":
        metrics = points[:3] if points else ["内容生成中", "内容生成中"]
        if len(metrics) < 2:
            metrics.append("内容生成中")
        return {
            "title": title,
            "metrics": [
                {"value": f"{(i + 1) * 10}%", "label": f"指标 {i + 1}", "description": p}
                for i, p in enumerate(metrics)
            ],
            "image": {"prompt": "modern office presentation setting"},
        }
    if layout_id == "chart-with-bullets":
        bullets = points[:4] if points else ["内容生成中", "内容生成中"]
        while len(bullets) < 2:
            bullets.append("内容生成中")
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
        rows = [[f"项{i + 1}", points[i] if i < len(points) else "内容生成中"] for i in range(3)]
        return {
            "title": title,
            "headers": ["主题", "说明"],
            "rows": rows,
            "caption": "自动回退生成内容",
        }
    if layout_id == "two-column-compare":
        candidates = points[:6] if points else ["内容生成中", "内容生成中"]
        if len(candidates) < 2:
            candidates.append("内容生成中")
        mid = max(1, (len(candidates) + 1) // 2)
        left_items = candidates[:mid] or ["内容生成中"]
        right_items = candidates[mid:] or ["内容生成中"]
        return {
            "title": title,
            "left": {"heading": "要点 A", "items": left_items, "icon": {"query": "layers"}},
            "right": {"heading": "要点 B", "items": right_items, "icon": {"query": "target"}},
        }
    if layout_id == "image-and-description":
        return {
            "title": title,
            "image": {"prompt": "business presentation illustration"},
            "description": points[0] if points else "内容生成中",
            "bullets": points[:3],
        }
    if layout_id == "timeline":
        events = points[:4] if points else ["内容生成中", "内容生成中", "内容生成中"]
        while len(events) < 3:
            events.append("内容生成中")
        return {
            "title": title,
            "events": [
                {"date": f"阶段 {i + 1}", "title": event, "description": "自动回退生成"}
                for i, event in enumerate(events)
            ],
        }
    if layout_id == "quote-slide":
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
        pairs = points[:4] if points else ["内容生成中", "内容生成中"]
        while len(pairs) < 2:
            pairs.append("内容生成中")
        return {
            "title": title,
            "items": [{"challenge": text, "outcome": "建议下一步行动"} for text in pairs],
        }

    # Unknown layout falls back to a known-safe bullet schema.
    fallback_items = points[:4] if points else ["内容生成中", "内容生成中", "内容生成中"]
    while len(fallback_items) < 3:
        fallback_items.append("内容生成中")
    return {
        "title": title,
        "items": [
            {"icon": {"query": "star"}, "title": p[:25], "description": p}
            for p in fallback_items
        ],
    }

"""Pipeline stages for generation v2.

Flow:
  parse -> outline -> layout -> slides -> assets -> verify -> fix(optional)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.models.slide import Slide

logger = logging.getLogger(__name__)

TOTAL_STEPS = 6

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
        state.outline = result.output.model_dump()
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

    from app.models.layout_registry import get_layout_catalog, get_layout_ids

    outline_items = state.outline.get("items", [])
    valid_ids = set(get_layout_ids())

    items_text = "\n".join(
        f"- 第{item['slide_number']}页: {item['title']} "
        f"(类别: {item.get('suggested_layout_category', 'bullets')}, "
        f"要点: {', '.join(item.get('key_points', [])[:3])})"
        for item in outline_items
    )
    prompt = (
        f"可用布局列表:\n{get_layout_catalog()}\n\n"
        f"大纲:\n{items_text}\n\n"
        f"请为每页选择最合适的 layout_id。"
    )

    try:
        from app.core.config import settings
        from app.services.agents.layout_selector import layout_selector_agent

        result = await layout_selector_agent.run(prompt)
        usage = result.usage()
        selections = result.output.model_dump()["slides"]

        for sel in selections:
            if sel["layout_id"] not in valid_ids:
                item = next((it for it in outline_items if it["slide_number"] == sel["slide_number"]), None)
                sel["layout_id"] = _category_to_layout(
                    item.get("suggested_layout_category", "bullets") if item else "bullets"
                )

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
            "Layout selection failed: %s, using category mapping",
            e,
            extra={"job_id": state.job_id, "stage": "layout", "error_type": type(e).__name__},
        )
        state.layout_selections = [
            {
                "slide_number": item["slide_number"],
                "layout_id": _category_to_layout(item.get("suggested_layout_category", "bullets")),
                "reason": "fallback",
            }
            for item in outline_items
        ]


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

            source_content = state.raw_content[:2000]

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
) -> None:
    if progress:
        await progress("verify", 6, TOTAL_STEPS, "验证布局质量...")

    from app.services.agents.layout_verifier import run_aesthetic_verification, verify_programmatic

    issues = [issue.model_dump(mode="json") for issue in verify_programmatic(state.slides)]

    if enable_vision and state.slides:
        presentation_dict = {
            "presentationId": "verification-temp",
            "title": state.topic or "演示文稿",
            "slides": [s.model_dump(mode="json", by_alias=True) for s in state.slides],
        }
        aesthetic = await run_aesthetic_verification(state.slides, presentation_dict=presentation_dict)
        if aesthetic:
            for issue in aesthetic.issues:
                issues.append(issue.model_dump(mode="json"))

    state.verification_issues = issues


async def stage_fix_slides_once(
    state: PipelineState,
    per_slide_timeout: float,
    progress: ProgressHook | None = None,
    on_slide: SlideHook | None = None,
) -> None:
    if progress:
        await progress("fix", 6, TOTAL_STEPS, "修复存在问题的页面...")

    from app.services.agents.slide_generator import generate_slide_content

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
        source_content = state.raw_content[:2000]

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



def _fallback_outline(state: PipelineState) -> dict[str, Any]:
    items: list[dict[str, Any]] = [
        {
            "slide_number": 1,
            "title": state.topic or "演示文稿",
            "content_brief": "演示文稿标题页",
            "key_points": [],
            "source_references": [],
            "suggested_layout_category": "intro",
        }
    ]
    for i in range(2, state.num_pages):
        items.append(
            {
                "slide_number": i,
                "title": f"第 {i} 节",
                "content_brief": "内容页",
                "key_points": ["要点"],
                "source_references": [],
                "suggested_layout_category": "bullets",
            }
        )
    items.append(
        {
            "slide_number": state.num_pages,
            "title": "谢谢",
            "content_brief": "致谢结束页",
            "key_points": [],
            "source_references": [],
            "suggested_layout_category": "thankyou",
        }
    )
    return {"narrative_arc": "自动生成的演示大纲", "items": items}



def _category_to_layout(category: str) -> str:
    mapping = {
        "intro": "intro-slide",
        "section": "section-header",
        "bullets": "bullet-with-icons",
        "metrics": "metrics-slide",
        "comparison": "two-column-compare",
        "chart": "chart-with-bullets",
        "table": "table-info",
        "timeline": "timeline",
        "quote": "quote-slide",
        "image": "image-and-description",
        "challenge": "challenge-outcome",
        "thankyou": "thank-you",
    }
    return mapping.get(category, "bullet-with-icons")



def _fallback_content(item: dict[str, Any], layout_id: str) -> dict[str, Any]:
    title = item.get("title", "幻灯片")
    points = item.get("key_points", ["内容生成中"])

    if layout_id == "intro-slide":
        return {"title": title, "subtitle": "由知演 AI 智能生成"}
    if layout_id in {"thank-you", "thankyou"}:
        return {"title": "谢谢", "subtitle": "感谢您的关注"}
    if layout_id == "section-header":
        return {"title": title}
    if layout_id == "bullet-with-icons":
        items = points[:4] if points else ["内容生成中"]
        while len(items) < 3:
            items.append("内容生成中")
        return {
            "title": title,
            "items": [
                {"icon": {"query": "star"}, "title": p[:25], "description": p}
                for p in items
            ],
        }
    if layout_id == "numbered-bullets":
        items = points[:5] if points else ["内容生成中"]
        while len(items) < 3:
            items.append("内容生成中")
        return {
            "title": title,
            "items": [{"title": f"要点 {i + 1}", "description": p} for i, p in enumerate(items)],
        }
    if layout_id == "metrics-slide":
        metrics = points[:3] if points else ["内容生成中", "内容生成中"]
        if len(metrics) < 2:
            metrics.append("内容生成中")
        return {
            "title": title,
            "metrics": [
                {"value": f"{(i + 1) * 10}%", "label": f"指标 {i + 1}", "description": p}
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
                "chartType": "bar",
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

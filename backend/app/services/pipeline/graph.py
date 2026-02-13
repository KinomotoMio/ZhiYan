"""pydantic-graph 编排 — 文档→大纲→布局选择→并行生成→验证

6-step Pipeline:
  ParseDocument → GenerateOutline → SelectLayouts
  → GenerateSlides(并行) → ResolveAssets → VerifySlides(End)

文档清洗已替换为解析时的轻量正则规范化（normalize_markdown）。
GenerateSpeakerNotes 已移至用户手动触发（按钮 / API），类定义保留供调用。
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from app.models.slide import Slide

logger = logging.getLogger(__name__)

TOTAL_STEPS = 6


@dataclass
class PipelineState:
    """Pipeline 共享状态"""

    # 输入
    raw_content: str = ""
    source_ids: list[str] = field(default_factory=list)
    topic: str = ""
    template_id: str | None = None
    num_pages: int = 5

    # 中间结果
    document_metadata: dict = field(default_factory=dict)
    outline: dict = field(default_factory=dict)
    layout_selections: list[dict] = field(default_factory=list)
    slide_contents: list[dict] = field(default_factory=list)

    # 输出
    slides: list[Slide] = field(default_factory=list)
    verification_issues: list[dict] = field(default_factory=list)

    # 进度回调（可选）
    progress_callback: Callable[..., Any] | None = None
    # 单页完成回调（渐进式 UX）
    slide_callback: Callable[[dict], None] | None = None

    def report_progress(self, stage: str, step: int, total_steps: int, message: str) -> None:
        if self.progress_callback:
            self.progress_callback(stage, step, total_steps, message)


# ---------- Step 1: ParseDocument ----------

@dataclass
class ParseDocumentNode(BaseNode[PipelineState]):
    """解析文档，提取元数据和结构"""

    async def run(
        self, ctx: GraphRunContext[PipelineState, None]
    ) -> "GenerateOutlineNode":
        ctx.state.report_progress("parse", 1, TOTAL_STEPS, "解析文档...")
        from app.services.document.parser import estimate_tokens

        content = ctx.state.raw_content
        token_count = estimate_tokens(content)
        heading_count = sum(
            1 for line in content.split("\n") if line.startswith("#")
        )

        ctx.state.document_metadata = {
            "char_count": len(content),
            "estimated_tokens": token_count,
            "heading_count": heading_count,
        }

        if ctx.state.source_ids:
            from app.services.document.source_store import get_combined_content

            combined = get_combined_content(ctx.state.source_ids)
            if combined:
                ctx.state.raw_content = combined

        logger.info(
            "ParseDocument: %d chars, ~%d tokens, %d headings",
            len(ctx.state.raw_content), token_count, heading_count,
        )
        return GenerateOutlineNode()


# ---------- Step 2: GenerateOutline ----------

@dataclass
class GenerateOutlineNode(BaseNode[PipelineState]):
    """生成演示文稿大纲 — 直接从文档内容生成，不再逐块分析"""

    async def run(
        self, ctx: GraphRunContext[PipelineState, None]
    ) -> "SelectLayoutsNode":
        ctx.state.report_progress("outline", 2, TOTAL_STEPS, "生成大纲...")
        t0 = time.monotonic()
        logger.info("GenerateOutline: starting")

        from app.services.document.parser import estimate_tokens

        content = ctx.state.raw_content
        token_count = estimate_tokens(content)

        # 构建 prompt
        if ctx.state.source_ids:
            from app.services.document.source_store import get_layer12_summaries

            summaries = get_layer12_summaries(ctx.state.source_ids)
            if summaries:
                content_section = f"文档摘要:\n{summaries}\n\n"
            else:
                content_section = ""

            if token_count <= 8000:
                content_section += f"文档全文:\n{content}"
            else:
                content_section += f"文档内容（前 8000 字符）:\n{content[:12000]}"
        else:
            content_section = f"内容:\n{content[:12000]}"

        prompt = (
            f"演示文稿主题：{ctx.state.topic or '综合演示'}\n"
            f"目标页数：{ctx.state.num_pages} 页\n\n"
            f"{content_section}\n\n"
            f"请生成一个 {ctx.state.num_pages} 页的演示文稿大纲。"
        )

        try:
            from app.services.agents.outline_synthesizer import outline_synthesizer_agent

            result = await outline_synthesizer_agent.run(prompt)
            usage = result.usage()
            if usage.requests > 1:
                logger.warning(
                    "GenerateOutline required %d LLM requests",
                    usage.requests,
                )
            ctx.state.outline = result.output.model_dump()
        except Exception as e:
            logger.warning("Outline generation failed: %s, using fallback", e)
            ctx.state.outline = self._fallback_outline(ctx.state)

        elapsed = time.monotonic() - t0
        outline_items = ctx.state.outline.get("items", [])
        logger.info(
            "GenerateOutline: %d items in %.1fs",
            len(outline_items), elapsed,
        )

        # 发送 outline_ready 事件（渐进式 UX）
        ctx.state.report_progress(
            "outline", 2, TOTAL_STEPS,
            json.dumps({
                "type": "outline_ready",
                "topic": ctx.state.topic,
                "items": [
                    {
                        "slide_number": item["slide_number"],
                        "title": item["title"],
                        "suggested_layout_category": item.get("suggested_layout_category", "bullets"),
                    }
                    for item in outline_items
                ],
            }),
        )

        return SelectLayoutsNode()

    @staticmethod
    def _fallback_outline(state: "PipelineState") -> dict:
        items = [
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
            items.append({
                "slide_number": i,
                "title": f"第 {i} 节",
                "content_brief": "内容页",
                "key_points": ["要点"],
                "source_references": [],
                "suggested_layout_category": "bullets",
            })
        items.append({
            "slide_number": state.num_pages,
            "title": "谢谢",
            "content_brief": "致谢结束页",
            "key_points": [],
            "source_references": [],
            "suggested_layout_category": "thankyou",
        })
        return {"narrative_arc": "自动生成的演示大纲", "items": items}


# ---------- Step 3: SelectLayouts ----------

@dataclass
class SelectLayoutsNode(BaseNode[PipelineState]):
    """为每页选择具体的 layout_id"""

    async def run(
        self, ctx: GraphRunContext[PipelineState, None]
    ) -> "GenerateSlidesNode":
        ctx.state.report_progress("layout", 3, TOTAL_STEPS, "选择布局...")
        t0 = time.monotonic()
        logger.info("SelectLayouts: starting")

        from app.models.layout_registry import get_layout_catalog, get_layout_ids

        outline_items = ctx.state.outline.get("items", [])
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
            from app.services.agents.layout_selector import layout_selector_agent

            result = await layout_selector_agent.run(prompt)
            selections = result.output.model_dump()["slides"]

            for sel in selections:
                if sel["layout_id"] not in valid_ids:
                    item = next(
                        (it for it in outline_items if it["slide_number"] == sel["slide_number"]),
                        None,
                    )
                    sel["layout_id"] = self._category_to_layout(
                        item.get("suggested_layout_category", "bullets") if item else "bullets"
                    )

            ctx.state.layout_selections = selections
        except Exception as e:
            logger.warning("Layout selection failed: %s, using category mapping", e)
            ctx.state.layout_selections = [
                {
                    "slide_number": item["slide_number"],
                    "layout_id": self._category_to_layout(
                        item.get("suggested_layout_category", "bullets")
                    ),
                    "reason": "fallback",
                }
                for item in outline_items
            ]

        elapsed = time.monotonic() - t0
        logger.info("SelectLayouts: %d layouts selected in %.1fs", len(ctx.state.layout_selections), elapsed)
        return GenerateSlidesNode()

    @staticmethod
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


# ---------- Step 4: GenerateSlides (并行) ----------

@dataclass
class GenerateSlidesNode(BaseNode[PipelineState]):
    """按 layout schema 并行生成每页结构化内容"""

    async def run(
        self, ctx: GraphRunContext[PipelineState, None]
    ) -> "ResolveAssetsNode":
        ctx.state.report_progress("generate", 4, TOTAL_STEPS, "生成幻灯片...")
        t0 = time.monotonic()
        logger.info("GenerateSlides: starting parallel generation")

        from app.services.agents.slide_generator import generate_slide_content

        outline_items = ctx.state.outline.get("items", [])
        layout_map = {
            sel["slide_number"]: sel["layout_id"]
            for sel in ctx.state.layout_selections
        }

        semaphore = asyncio.Semaphore(5)
        results: list[dict] = [{}] * len(outline_items)

        async def generate_one(idx: int, item: dict) -> None:
            async with semaphore:
                slide_num = item["slide_number"]
                layout_id = layout_map.get(slide_num, "bullet-with-icons")

                source_content = ""
                if item.get("source_references"):
                    from app.services.document.source_store import get_combined_content

                    source_content = get_combined_content(
                        item["source_references"]
                    )
                if not source_content:
                    source_content = ctx.state.raw_content[:2000]

                try:
                    content_data = await generate_slide_content(
                        layout_id=layout_id,
                        slide_number=slide_num,
                        title=item["title"],
                        content_brief=item.get("content_brief", ""),
                        key_points=item.get("key_points", []),
                        source_content=source_content,
                    )
                    results[idx] = {
                        "slide_number": slide_num,
                        "layout_id": layout_id,
                        "content_data": content_data,
                    }
                except Exception as e:
                    logger.warning("Slide %d generation failed: %s", slide_num, e)
                    results[idx] = {
                        "slide_number": slide_num,
                        "layout_id": layout_id,
                        "content_data": self._fallback_content(item, layout_id),
                    }

                # 构建 Slide 对象并通过 slide_callback 推送
                slide = Slide(
                    slideId=f"slide-{slide_num}",
                    layoutType=results[idx].get("layout_id", "bullet-with-icons"),
                    layoutId=results[idx].get("layout_id", "bullet-with-icons"),
                    contentData=results[idx].get("content_data", {}),
                    components=[],
                )
                if ctx.state.slide_callback:
                    ctx.state.slide_callback({
                        "type": "slide_ready",
                        "slide_index": idx,
                        "slide": json.loads(slide.model_dump_json(by_alias=True)),
                    })

                ctx.state.report_progress(
                    "generate", 4, TOTAL_STEPS,
                    f"生成第 {idx + 1}/{len(outline_items)} 页...",
                )

        await asyncio.gather(
            *(generate_one(i, item) for i, item in enumerate(outline_items))
        )

        ctx.state.slide_contents = results
        elapsed = time.monotonic() - t0
        logger.info("GenerateSlides: %d slides in %.1fs", len(results), elapsed)
        return ResolveAssetsNode()

    @staticmethod
    def _fallback_content(item: dict, layout_id: str) -> dict:
        title = item.get("title", "幻灯片")
        points = item.get("key_points", ["内容生成中"])

        if layout_id == "intro-slide":
            return {"title": title, "subtitle": "由知演 AI 智能生成"}
        if layout_id == "thank-you":
            return {"title": "谢谢", "subtitle": "感谢您的关注"}
        if layout_id == "section-header":
            return {"title": title}
        if layout_id == "quote-slide":
            return {"quote": points[0] if points else title}

        return {
            "title": title,
            "items": [
                {"icon": {"query": "star"}, "title": p[:25], "description": p}
                for p in points[:4]
            ],
        }


# ---------- Step 5: ResolveAssets ----------

@dataclass
class ResolveAssetsNode(BaseNode[PipelineState]):
    """解析图片/图标资源（MVP 阶段保持占位）"""

    async def run(
        self, ctx: GraphRunContext[PipelineState, None]
    ) -> "VerifySlidesNode":
        ctx.state.report_progress("assets", 5, TOTAL_STEPS, "处理资源...")
        logger.info("ResolveAssets: MVP pass-through (%d slides)", len(ctx.state.slide_contents))

        slides: list[Slide] = []
        for sc in ctx.state.slide_contents:
            slide = Slide(
                slideId=f"slide-{sc['slide_number']}",
                layoutType=sc.get("layout_id", "bullet-with-icons"),
                layoutId=sc.get("layout_id", "bullet-with-icons"),
                contentData=sc.get("content_data", {}),
                components=[],
            )
            slides.append(slide)

        ctx.state.slides = slides
        return VerifySlidesNode()


# ---------- Step 6: VerifySlides (终止节点) ----------

@dataclass
class VerifySlidesNode(BaseNode[PipelineState, None, list[Slide]]):
    """验证布局质量 — 基于结构化数据的检查"""

    async def run(
        self, ctx: GraphRunContext[PipelineState, None]
    ) -> End[list[Slide]]:
        ctx.state.report_progress("verify", 6, TOTAL_STEPS, "验证布局质量...")
        t0 = time.monotonic()
        logger.info("VerifySlides: starting verification")

        issues = []
        for slide in ctx.state.slides:
            content = slide.content_data or {}
            if not content:
                issues.append({
                    "slide_id": slide.slide_id,
                    "severity": "error",
                    "category": "content",
                    "message": f"幻灯片 {slide.slide_id} 缺少内容数据",
                    "suggestion": "重新生成该页内容",
                })

        ctx.state.verification_issues = issues
        elapsed = time.monotonic() - t0
        logger.info(
            "VerifySlides: %d issues found in %.1fs",
            len(issues), elapsed,
        )
        return End(ctx.state.slides)


# ========== 以下节点已从 Pipeline 移除，保留类定义供 API 独立调用 ==========


@dataclass
class GenerateSpeakerNotesNode(BaseNode[PipelineState]):
    """批量生成演讲者注释 — 已从 pipeline 移除，改为用户手动触发"""

    async def run(
        self, ctx: GraphRunContext[PipelineState, None]
    ) -> End[list[Slide]]:
        t0 = time.monotonic()
        logger.info("GenerateSpeakerNotes: starting")

        slides = ctx.state.slides
        if not slides:
            return End(slides)

        slides_summary = "\n".join(
            f"- 第{i+1}页 [{s.layout_id}]: "
            f"{(s.content_data or {}).get('title', '无标题')}"
            for i, s in enumerate(slides)
        )
        prompt = (
            f"演示文稿主题: {ctx.state.topic}\n\n"
            f"幻灯片列表:\n{slides_summary}\n\n"
            f"请为每页生成演讲者注释。"
        )

        try:
            from app.services.agents.speaker_notes_generator import speaker_notes_generator_agent

            result = await speaker_notes_generator_agent.run(prompt)
            notes_map = {
                n.slide_number: n.notes
                for n in result.output.notes
            }
            for i, slide in enumerate(slides):
                slide.speaker_notes = notes_map.get(i + 1, "")
        except Exception as e:
            logger.warning("Speaker notes generation failed: %s", e)

        elapsed = time.monotonic() - t0
        logger.info("GenerateSpeakerNotes: done in %.1fs", elapsed)
        return End(slides)


# 注册活跃节点（GenerateSpeakerNotesNode 已移除）
slide_pipeline = Graph(
    nodes=[
        ParseDocumentNode,
        GenerateOutlineNode,
        SelectLayoutsNode,
        GenerateSlidesNode,
        ResolveAssetsNode,
        VerifySlidesNode,
    ],
    name="slide_pipeline",
)

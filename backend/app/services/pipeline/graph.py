"""pydantic-graph 编排 — 文档→分析→大纲→生成→验证

使用 pydantic-graph Original API (BaseNode)。
状态通过 PipelineState 在节点间共享。
"""

import asyncio
import logging
from dataclasses import dataclass, field

from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from app.models.slide import Slide

logger = logging.getLogger(__name__)


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
    chunks: list[dict] = field(default_factory=list)
    chunk_analyses: list[dict] = field(default_factory=list)
    outline: dict = field(default_factory=dict)

    # 输出
    slides: list[Slide] = field(default_factory=list)
    verification_issues: list[dict] = field(default_factory=list)


@dataclass
class ParseDocumentNode(BaseNode[PipelineState]):
    """解析文档，提取元数据和结构"""

    async def run(
        self, ctx: GraphRunContext[PipelineState, None]
    ) -> "PlanChunksNode":
        from app.services.document.parser import estimate_tokens

        content = ctx.state.raw_content
        token_count = estimate_tokens(content)
        # 统计标题数量
        heading_count = sum(
            1 for line in content.split("\n") if line.startswith("#")
        )
        paragraph_count = len(
            [p for p in content.split("\n\n") if p.strip()]
        )

        ctx.state.document_metadata = {
            "char_count": len(content),
            "estimated_tokens": token_count,
            "heading_count": heading_count,
            "paragraph_count": paragraph_count,
        }
        logger.info(
            "ParseDocument: %d chars, ~%d tokens, %d headings",
            len(content), token_count, heading_count,
        )
        return PlanChunksNode()


@dataclass
class PlanChunksNode(BaseNode[PipelineState]):
    """规划分块策略 — 优先使用标题分块，回退到段落分块"""

    async def run(
        self, ctx: GraphRunContext[PipelineState, None]
    ) -> "AnalyzeChunksNode":
        from app.services.document.parser import split_by_headings

        content = ctx.state.raw_content
        metadata = ctx.state.document_metadata

        # 有标题结构 → 按标题分块
        if metadata.get("heading_count", 0) > 0:
            chunks = split_by_headings(content)
        else:
            # 无标题 → 按双换行分段
            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
            if not paragraphs:
                paragraphs = [content]
            chunks = [
                {
                    "chunk_id": f"chunk-{i}",
                    "heading": "",
                    "content": p,
                    "estimated_tokens": len(p) // 2,
                }
                for i, p in enumerate(paragraphs)
            ]

        # 如果块太少（短文本），确保至少有一个
        if not chunks:
            chunks = [{
                "chunk_id": "chunk-0",
                "heading": ctx.state.topic or "内容",
                "content": content,
                "estimated_tokens": metadata.get("estimated_tokens", 0),
            }]

        ctx.state.chunks = chunks
        logger.info("PlanChunks: %d chunks generated", len(chunks))
        return AnalyzeChunksNode()


@dataclass
class AnalyzeChunksNode(BaseNode[PipelineState]):
    """分析各块内容 — 并行调用 chunk_analyzer_agent"""

    async def run(
        self, ctx: GraphRunContext[PipelineState, None]
    ) -> "SynthesizeOutlineNode":
        topic = ctx.state.topic

        async def analyze_one(chunk: dict) -> dict:
            prompt = (
                f"演示文稿主题：{topic}\n\n"
                f"请分析以下文档片段（ID: {chunk['chunk_id']}）：\n\n"
                f"{chunk['content'][:3000]}"
            )
            try:
                from app.services.agents.chunk_analyzer import chunk_analyzer_agent

                result = await chunk_analyzer_agent.run(prompt)
                analysis = result.output.model_dump()
                analysis["chunk_id"] = chunk["chunk_id"]
                return analysis
            except Exception as e:
                logger.warning("Chunk %s analysis failed: %s", chunk["chunk_id"], e)
                # 回退：从原文提取简单要点
                content = chunk.get("content", "")
                lines = [l.strip() for l in content.split("\n") if l.strip() and not l.startswith("#")]
                key_points = lines[:3] if lines else [chunk.get("heading", "内容要点")]
                return {
                    "chunk_id": chunk["chunk_id"],
                    "key_points": key_points,
                    "suggested_slide_count": 1,
                    "data_elements": [],
                    "importance": 0.5,
                }

        # 并行分析所有块，捕获整体错误
        try:
            ctx.state.chunk_analyses = list(await asyncio.gather(
                *(analyze_one(chunk) for chunk in ctx.state.chunks)
            ))
        except Exception as e:
            logger.warning("AnalyzeChunks gather failed: %s, using fallback", e)
            ctx.state.chunk_analyses = [
                {
                    "chunk_id": chunk["chunk_id"],
                    "key_points": [chunk.get("heading", "") or chunk["content"][:50]],
                    "suggested_slide_count": 1,
                    "data_elements": [],
                    "importance": 0.5,
                }
                for chunk in ctx.state.chunks
            ]
        logger.info("AnalyzeChunks: %d chunks analyzed", len(ctx.state.chunk_analyses))
        return SynthesizeOutlineNode()


@dataclass
class SynthesizeOutlineNode(BaseNode[PipelineState]):
    """综合生成大纲 — 调用 outline_synthesizer_agent"""

    async def run(
        self, ctx: GraphRunContext[PipelineState, None]
    ) -> "GenerateSlidesNode":
        # 构建分析摘要
        analyses_text = "\n".join(
            f"- [{a['chunk_id']}] 要点: {', '.join(a.get('key_points', [])[:3])}; "
            f"重要度: {a.get('importance', 0.5):.1f}; "
            f"建议页数: {a.get('suggested_slide_count', 1)}"
            for a in ctx.state.chunk_analyses
        )

        prompt = (
            f"演示文稿主题：{ctx.state.topic or '综合演示'}\n"
            f"目标页数：{ctx.state.num_pages} 页\n\n"
            f"文档分析摘要：\n{analyses_text}\n\n"
            f"请据此生成一个 {ctx.state.num_pages} 页的演示文稿大纲。"
            f"第 1 页必须是 title-slide，最后一页是 section-header（致谢页）。"
        )

        try:
            from app.services.agents.outline_synthesizer import outline_synthesizer_agent

            result = await outline_synthesizer_agent.run(prompt)
            ctx.state.outline = result.output.model_dump()
        except Exception as e:
            logger.warning("Outline synthesis failed: %s, using fallback", e)
            ctx.state.outline = self._fallback_outline(ctx.state)

        logger.info(
            "SynthesizeOutline: %d items",
            len(ctx.state.outline.get("items", [])),
        )
        return GenerateSlidesNode()

    @staticmethod
    def _fallback_outline(state: "PipelineState") -> dict:
        """Agent 调用失败时的回退大纲"""
        items = [
            {
                "slide_number": 1,
                "title": state.topic or "演示文稿",
                "layout_type": "title-slide",
                "key_points": [],
                "source_chunk_ids": [],
            }
        ]
        # 内容页
        for i in range(2, state.num_pages):
            chunk_idx = min(i - 2, len(state.chunk_analyses) - 1)
            analysis = (
                state.chunk_analyses[chunk_idx]
                if state.chunk_analyses
                else {"key_points": ["要点"], "chunk_id": "chunk-0"}
            )
            items.append({
                "slide_number": i,
                "title": f"第 {i} 节",
                "layout_type": "title-content",
                "key_points": analysis.get("key_points", [])[:3],
                "source_chunk_ids": [analysis.get("chunk_id", "chunk-0")],
            })
        # 结尾页
        items.append({
            "slide_number": state.num_pages,
            "title": "谢谢",
            "layout_type": "section-header",
            "key_points": [],
            "source_chunk_ids": [],
        })
        return {"narrative_arc": "自动生成的演示大纲", "items": items}


@dataclass
class GenerateSlidesNode(BaseNode[PipelineState]):
    """按大纲逐页生成 Slide — 调用 slide_generator_agent + layout 映射"""

    async def run(
        self, ctx: GraphRunContext[PipelineState, None]
    ) -> "VerifySlidesNode":
        from app.services.pipeline.layout import build_slide_from_content

        outline_items = ctx.state.outline.get("items", [])
        # 构建 chunk_id → content 映射
        chunk_map = {c["chunk_id"]: c["content"] for c in ctx.state.chunks}

        slides: list[Slide] = []
        for item in outline_items:
            slide_num = item["slide_number"]
            layout = item.get("layout_type", "title-content")

            # 收集关联源内容
            source_chunks = [
                chunk_map.get(cid, "")
                for cid in item.get("source_chunk_ids", [])
            ]
            source_content = "\n".join(source_chunks)[:2000]

            prompt = (
                f"幻灯片 #{slide_num}，布局: {layout}\n"
                f"标题方向: {item['title']}\n"
                f"核心要点: {', '.join(item.get('key_points', []))}\n\n"
                f"关联源文档片段:\n{source_content[:1500]}\n\n"
                f"请生成这一页幻灯片的内容。"
            )

            try:
                from app.services.agents.slide_generator import slide_generator_agent

                result = await slide_generator_agent.run(prompt)
                content = result.output
                slide = build_slide_from_content(
                    slide_number=slide_num,
                    title=content.title,
                    layout_type=content.layout_type.value,
                    body_text=content.body_text,
                    speaker_notes=content.speaker_notes,
                    needs_image=content.needs_image,
                    image_description=content.image_description,
                )
            except Exception as e:
                logger.warning("Slide %d generation failed: %s", slide_num, e)
                slide = build_slide_from_content(
                    slide_number=slide_num,
                    title=item["title"],
                    layout_type=layout,
                    body_text="\n".join(
                        f"• {p}" for p in item.get("key_points", ["内容生成中"])
                    ),
                    speaker_notes="",
                )
            slides.append(slide)

        ctx.state.slides = slides
        logger.info("GenerateSlides: %d slides created", len(slides))
        return VerifySlidesNode()


@dataclass
class VerifySlidesNode(BaseNode[PipelineState, None, list[Slide]]):
    """验证布局质量 — 程序化检查"""

    async def run(
        self, ctx: GraphRunContext[PipelineState, None]
    ) -> End[list[Slide]]:
        from app.services.agents.layout_verifier import verify_programmatic, run_aesthetic_verification

        issues = verify_programmatic(ctx.state.slides)

        # 可选：LLM 审美评估
        aesthetic_result = await run_aesthetic_verification(ctx.state.slides)
        if aesthetic_result and aesthetic_result.issues:
            issues.extend(aesthetic_result.issues)

        ctx.state.verification_issues = [i.model_dump() for i in issues]

        if issues:
            logger.info(
                "VerifySlides: %d issues found (%d errors)",
                len(issues),
                sum(1 for i in issues if i.severity == "error"),
            )
        else:
            logger.info("VerifySlides: all checks passed")

        return End(ctx.state.slides)


# 注册所有节点
slide_pipeline = Graph(
    nodes=[
        ParseDocumentNode,
        PlanChunksNode,
        AnalyzeChunksNode,
        SynthesizeOutlineNode,
        GenerateSlidesNode,
        VerifySlidesNode,
    ],
    name="slide_pipeline",
)

"""Outline Synthesizer Agent — 块摘要 → 叙事大纲

只看各块的摘要，不看原文，保持 context 精简。
"""

from pydantic import BaseModel, Field


class OutlineItem(BaseModel):
    """大纲中的一项"""

    slide_number: int
    title: str = Field(description="幻灯片标题")
    layout_type: str = Field(description="建议的布局类型")
    key_points: list[str] = Field(description="该页的核心要点")
    source_chunk_ids: list[str] = Field(description="关联的源文档块 ID")


class PresentationOutline(BaseModel):
    """演示文稿大纲"""

    narrative_arc: str = Field(description="叙事主线描述")
    items: list[OutlineItem]


_agent = None


def get_outline_synthesizer_agent():
    """延迟创建 Agent"""
    global _agent
    if _agent is None:
        from pydantic_ai import Agent
        from app.core.config import settings
        from app.core.model_resolver import resolve_model

        _agent = Agent(
            model=resolve_model(settings.strong_model),
            output_type=PresentationOutline,
            instructions=(
                "你是一个演示文稿策划专家。根据各文档块的分析摘要，构建一个连贯的叙事大纲。\n\n"
                "## 叙事结构指南\n"
                "采用「问题→分析→方案→结论」四段式叙事弧：\n"
                "1. **开篇引入**（1-2页）：title-slide 亮出主题 + 背景/问题引出\n"
                "2. **现状分析**（占总页数 30%）：数据、案例、痛点\n"
                "3. **解决方案**（占总页数 40%）：核心方法、技术细节、优势\n"
                "4. **总结展望**（1-2页）：核心结论 + 致谢页\n\n"
                "## 布局选择规则\n"
                "- 第 1 页必须是 title-slide\n"
                "- 最后一页必须是 section-header（致谢页）\n"
                "- 章节过渡用 section-header\n"
                "- 数据密集内容用 two-column\n"
                "- 需要配图的内容用 title-content-image\n"
                "- 其余内容页用 title-content\n\n"
                "## 质量要求\n"
                "- 每页只承载一个核心观点\n"
                "- 相关内容按逻辑顺序排列\n"
                "- 避免信息重复\n"
                "- narrative_arc 一句话概括叙事主线（如「从行业痛点出发，分析AI解决方案，展示落地成果」）"
            ),
        )
    return _agent


def __getattr__(name):
    if name == "outline_synthesizer_agent":
        return get_outline_synthesizer_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

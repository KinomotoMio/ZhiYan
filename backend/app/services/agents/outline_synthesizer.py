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

        _agent = Agent(
            model="openai:gpt-4o",
            output_type=PresentationOutline,
            instructions=(
                "你是一个演示文稿策划专家。根据各文档块的分析摘要，构建一个连贯的叙事大纲。\n"
                "规则：\n"
                "- 开头用 title-slide，结尾用 section-header（致谢页）\n"
                "- 章节过渡用 section-header\n"
                "- 内容页选择 title-content 或 title-content-image\n"
                "- 数据密集的内容用 two-column\n"
                "- 每页只承载一个核心观点\n"
                "- 叙事主线应该有清晰的起承转合"
            ),
        )
    return _agent


def __getattr__(name):
    if name == "outline_synthesizer_agent":
        return get_outline_synthesizer_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""Slide Generator Agent — 大纲 + 关联块 → Slide JSON

按需加载：只加载当前页关联的源文档片段。
LLM 只负责内容决策，不指定精确坐标。
"""

from pydantic import BaseModel, Field

from app.models.slide import LayoutType


class SlideGenerationInput(BaseModel):
    """单页幻灯片生成的输入"""

    slide_number: int
    title: str
    layout_type: str
    key_points: list[str]
    source_content: str = Field(description="关联的源文档内容片段")


class SlideContent(BaseModel):
    """LLM 生成的内容决策（不含坐标）"""

    title: str = Field(description="幻灯片标题")
    layout_type: LayoutType
    body_text: str | None = Field(None, description="正文内容（Markdown 格式）")
    speaker_notes: str = Field(description="演讲者注释")
    needs_image: bool = Field(default=False, description="是否需要配图")
    image_description: str | None = Field(None, description="配图描述（用于后续生成）")


_agent = None


def get_slide_generator_agent():
    """延迟创建 Agent"""
    global _agent
    if _agent is None:
        from pydantic_ai import Agent

        _agent = Agent(
            model="openai:gpt-4o",
            output_type=SlideContent,
            instructions=(
                "你是一个幻灯片内容撰写专家。根据大纲和源文档内容，生成单页幻灯片的内容。\n"
                "规则：\n"
                "- 标题简洁有力，不超过 15 个字\n"
                "- 要点使用列表格式，每条不超过 20 个字\n"
                "- 每页最多 5 个要点\n"
                "- 演讲者注释应包含展开说明，帮助演讲者讲解\n"
                "- 不要生成坐标或样式数值，只负责内容\n"
                "- 中文为主，专业术语保留英文原文"
            ),
        )
    return _agent


def __getattr__(name):
    if name == "slide_generator_agent":
        return get_slide_generator_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

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
        from app.core.config import settings

        _agent = Agent(
            model=settings.strong_model,
            output_type=SlideContent,
            instructions=(
                "你是一个幻灯片内容撰写专家。根据大纲和源文档内容，生成单页幻灯片的内容。\n\n"
                "## 规则\n"
                "- 标题简洁有力，不超过 15 个字\n"
                "- 要点使用列表格式，每条不超过 20 个字\n"
                "- 每页最多 5 个要点\n"
                "- 演讲者注释应包含展开说明，帮助演讲者讲解（50-100字）\n"
                "- 不要生成坐标或样式数值，只负责内容\n"
                "- 中文为主，专业术语保留英文原文\n\n"
                "## 示例\n\n"
                "### 输入\n"
                "幻灯片 #3，布局: title-content\n"
                "标题方向: AI 技术的三大突破\n"
                "核心要点: 自然语言处理, 计算机视觉, 强化学习\n"
                "关联源文档：2024年，大语言模型在代码生成、翻译、摘要等任务上接近人类水平...\n\n"
                "### 期望输出\n"
                "- title: 'AI 技术三大突破领域'\n"
                "- layout_type: 'title-content'\n"
                "- body_text: '• 自然语言处理：LLM 接近人类水平\\n"
                "• 计算机视觉：多模态理解与生成\\n"
                "• 强化学习：从游戏到机器人控制'\n"
                "- speaker_notes: '这三个领域代表了当前 AI 最活跃的研究方向。"
                "NLP 方面，大语言模型已经能够完成代码生成、多语言翻译等复杂任务...'\n"
                "- needs_image: false\n\n"
                "## 布局选择指南\n"
                "- title-slide: 仅标题+副标题，用于首页\n"
                "- title-content: 标题+正文要点，最常用\n"
                "- title-content-image: 有配图需求时使用\n"
                "- two-column: 对比或并列内容\n"
                "- section-header: 章节过渡页\n"
            ),
        )
    return _agent


def __getattr__(name):
    if name == "slide_generator_agent":
        return get_slide_generator_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

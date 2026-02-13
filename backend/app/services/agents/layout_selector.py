"""Layout Selector Agent — 为每页幻灯片选择最佳布局

输入：大纲 items + 可用布局清单
输出：每页的 layout_id

使用 fast_model，不需要 strong_model。
"""

from pydantic import BaseModel, Field

_agent = None


class SlideLayoutChoice(BaseModel):
    slide_number: int
    layout_id: str = Field(description="从可用布局中选择的 layout_id")
    reason: str = Field(description="选择理由（一句话）")


class LayoutSelectionResult(BaseModel):
    slides: list[SlideLayoutChoice]


def get_layout_selector_agent():
    """延迟创建 Agent"""
    global _agent
    if _agent is None:
        from pydantic_ai import Agent

        from app.core.config import settings
        from app.core.model_resolver import resolve_model

        _agent = Agent(
            model=resolve_model(settings.fast_model or settings.default_model),
            output_type=LayoutSelectionResult,
            retries=1,
            instructions=(
                "你是演示文稿布局选择专家。根据大纲中每页的内容特征，"
                "从可用布局列表中选择最合适的布局。\n\n"
                "## 选择原则\n"
                "- 第一页必须使用 `intro-slide`\n"
                "- 最后一页必须使用 `thank-you`\n"
                "- 章节过渡页使用 `section-header`\n"
                "- 包含数字/KPI 的内容使用 `metrics-slide` 或 `metrics-with-image`\n"
                "- 包含步骤/流程的内容使用 `numbered-bullets`\n"
                "- 包含对比的内容使用 `two-column-compare` 或 `challenge-outcome`\n"
                "- 包含数据表格的内容使用 `table-info`\n"
                "- 包含时间线/里程碑的内容使用 `timeline`\n"
                "- 重要引述/结论使用 `quote-slide`\n"
                "- 需要配图的使用 `image-and-description` 或 `metrics-with-image`\n"
                "- 一般要点列举使用 `bullet-with-icons`\n"
                "- 技术栈/特性列表使用 `bullet-icons-only`\n\n"
                "## 多样性原则\n"
                "- 避免连续使用相同布局（除非内容确实需要）\n"
                "- 整体布局应有视觉变化和节奏感\n"
            ),
        )
    return _agent


def __getattr__(name):
    if name == "layout_selector_agent":
        return get_layout_selector_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

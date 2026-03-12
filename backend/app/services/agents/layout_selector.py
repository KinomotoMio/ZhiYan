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
                "- 先满足每页的 `suggested_slide_role` 页面角色，再决定具体 layout_id\n"
                "- `cover` 必须选择 `intro-slide`\n"
                "- `agenda` 必须选择 `outline-slide`\n"
                "- `section-divider` 必须选择 `section-header`\n"
                "- `closing` 必须选择 `thank-you`\n"
                "- `narrative` 在 `bullet-with-icons` / `bullet-icons-only` / `image-and-description` 中选择\n"
                "- `evidence` 在 `metrics-slide` / `metrics-with-image` / `chart-with-bullets` / `table-info` 中选择\n"
                "- `comparison` 在 `two-column-compare` / `challenge-outcome` 中选择\n"
                "- `process` 在 `numbered-bullets` / `timeline` 中选择\n"
                "- `highlight` 选择 `quote-slide`\n"
                "- 优先选择 usage 匹配且结构匹配的 layout\n"
                "- 若 usage 不匹配但结构明显更合适，可越过 usage\n"
                "- 学术类优先信息密度高、逻辑清晰的 layout\n"
                "- 商业/销售/路演类优先强调价值、对比、指标、配图的 layout\n"
                "- 培训/会议类优先步骤、时间线、章节切换清晰的 layout\n\n"
                "## 多样性原则\n"
                "- 避免连续使用相同布局（除非内容确实需要）\n"
                "- 整体布局应有视觉变化和节奏感\n"
            ),
        )
    return _agent


class _LazyLayoutSelectorAgent:
    """Proxy that keeps runtime lazy-loading without breaking test monkeypatching."""

    def __getattr__(self, name):
        return getattr(get_layout_selector_agent(), name)


layout_selector_agent = _LazyLayoutSelectorAgent()

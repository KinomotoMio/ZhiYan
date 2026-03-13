"""Layout Selector Agent — 为每页幻灯片选择最佳布局

输入：大纲 items + 可用布局清单
输出：每页的 group + sub_group + layout_id

使用 fast_model，不需要 strong_model。
"""

from pydantic import BaseModel, Field

_agent = None


class SlideLayoutChoice(BaseModel):
    slide_number: int
    group: str = Field(description="必须与该页的 suggested_slide_role 一致")
    sub_group: str = Field(
        default="default",
        description="该 group 下的信息结构层；非 narrative 组统一填 default",
    )
    layout_id: str = Field(description="从可用布局中选择的 layout_id")
    reason: str = Field(description="选择理由（一句话）")


class LayoutSelectionResult(BaseModel):
    slides: list[SlideLayoutChoice]


class _LazyLayoutSelectorAgent:
    async def run(self, *args, **kwargs):
        return await get_layout_selector_agent().run(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(get_layout_selector_agent(), name)


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
                "- 必须先锁定每页的 `group`，且它必须与 `suggested_slide_role` 一致\n"
                "- 然后选择该 `group` 下的 `sub_group`，最后再落到具体 `layout_id`\n"
                "- 对 narrative，必须先判断是 `icon-points` / `visual-explainer` / `capability-grid` 哪一种结构，再选择 layout\n"
                "- 对非 narrative group，`sub_group` 一律填 `default`\n"
                "- `cover` 必须选择 `intro-slide`\n"
                "- `agenda` 必须选择 `outline-slide`\n"
                "- `section-divider` 必须选择 `section-header`\n"
                "- `closing` 必须选择 `thank-you`\n"
                "- `evidence` / `comparison` / `process` 仍按各自 group 内布局选择，但 sub_group 保持 `default`\n"
                "- 优先选择 usage 匹配且结构匹配的 layout\n"
                "- 若 usage 不匹配但结构明显更合适，可越过 usage\n"
                "- 尽量避免连续页面选择完全相同的 `layout_id`，除非角色固定页或没有更合适候选\n"
                "- 学术类优先信息密度高、逻辑清晰的 layout\n"
                "- 商业/销售/路演类优先强调价值、对比、指标、配图的 layout\n"
                "- 培训/会议类优先步骤、时间线、章节切换清晰的 layout\n\n"
                "## 输出要求\n"
                "- 每页必须同时输出 `group`、`sub_group`、`layout_id`、`reason`\n"
                "- `variant` 由系统在选定最终 layout 后自动回填，你不需要输出它\n"
                "- 若 `layout_id` 与你选定的 `group` / `sub_group` 不匹配，优先保证 `group` / `sub_group` 正确\n"
            ),
        )
    return _agent


layout_selector_agent = _LazyLayoutSelectorAgent()

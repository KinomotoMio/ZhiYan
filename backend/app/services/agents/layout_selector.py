"""Layout Selector Agent — 为每页幻灯片选择最佳布局

输入：大纲 items + 可用布局清单
输出：每页的 group + sub_group + variant_id

使用 fast_model，不需要 strong_model。
"""

from pydantic import BaseModel, Field

_agent = None


class SlideLayoutChoice(BaseModel):
    slide_number: int
    group: str = Field(description="必须与该页的 suggested_slide_role 一致")
    sub_group: str = Field(
        default="default",
        description="该 group 下的信息结构层；必须从该 group 的正式 sub_group 集合中选择",
    )
    variant_id: str = Field(
        description="该 group + sub_group 下的正式设计变体标识；必须从该结构的 variant 集合中选择",
    )
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
                "- 然后选择该 `group` 下的 `sub_group`，再选择该结构下的 `variant_id`\n"
                "- 对存在正式结构层的 group，必须先判断应落在哪个 `sub_group`\n"
                "- `narrative` 候选为 `icon-points` / `visual-explainer` / `capability-grid`\n"
                "- `evidence` 候选为 `stat-summary` / `visual-evidence` / `chart-analysis` / `table-matrix`\n"
                "- `comparison` 候选为 `side-by-side` / `response-mapping`\n"
                "- `process` 候选为 `step-flow` / `timeline-milestone`\n"
                "- 若某页条目包含 `content_hints`（结构提示），优先按其指示选择 sub_group/variant：chart->evidence/chart-analysis，table->evidence/table-matrix，timeline->process/timeline-milestone，image->narrative/visual-explainer 或 evidence/visual-evidence（取决于该页 group）\n"
                "- 其余 group 保持 `sub_group=default`\n"
                "- 优先选择 usage 匹配且结构匹配的 variant\n"
                "- 若 usage 不匹配但结构明显更合适，可越过 usage\n"
                "- 不需要直接输出 `layout_id`，系统会在你选中的 `variant_id` 下再解析具体模板\n"
                "- 学术类优先信息密度高、逻辑清晰的 layout\n"
                "- 商业/销售/路演类优先强调价值、对比、指标、配图的 layout\n"
                "- 培训/会议类优先步骤、时间线、章节切换清晰的 layout\n\n"
                "## 输出要求\n"
                "- 每页必须同时输出 `group`、`sub_group`、`variant_id`、`reason`\n"
                "- 不要输出 `layout_id`\n"
                "- 若 `variant_id` 与你选定的 `group` / `sub_group` 不匹配，优先保证 `group` / `sub_group` 正确\n"
            ),
        )
    return _agent


layout_selector_agent = _LazyLayoutSelectorAgent()

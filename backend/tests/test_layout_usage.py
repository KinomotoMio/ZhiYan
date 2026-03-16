import asyncio
import logging
from types import SimpleNamespace

from app.models.layout_registry import (
    get_all_layouts,
    get_layout,
    get_layout_catalog,
    get_layout_variant_catalog,
)
from app.services.pipeline.layout_roles import (
    format_role_contract_for_prompt,
    get_layout_role,
    get_layout_role_description,
    is_variant_pilot_role,
    normalize_outline_items_roles,
)
from app.services.pipeline.layout_variants import (
    get_layout_variant,
    get_layout_variant_description,
    get_layout_variant_label,
    get_variants_for_role,
)
from app.services.pipeline.graph import (
    PipelineState,
    _enforce_adjacent_layout_diversity,
    stage_select_layouts,
)
from app.services.pipeline.layout_usage import (
    infer_document_and_slide_usage,
    infer_usage_tags,
    rank_layouts_by_usage,
)


class _FakeResult:
    def __init__(self, selections):
        self.output = SimpleNamespace(model_dump=lambda: {"slides": selections})

    def usage(self):
        return SimpleNamespace(requests=1, __str__=lambda self: "requests=1")


class _FakeLayoutSelectorAgent:
    def __init__(self, selections):
        self.selections = selections
        self.prompts: list[str] = []

    async def run(self, prompt: str):
        self.prompts.append(prompt)
        return _FakeResult(self.selections)


def test_infer_usage_tags_hits_common_generation_scenarios():
    assert infer_usage_tags(("研究生论文答辩：多模态检索实验结果",)) == ("academic-report",)
    assert infer_usage_tags(("Q2 商业复盘与经营分析",)) == ("business-report",)
    assert infer_usage_tags(("客户销售提案与招投标方案",)) == ("sales-pitch",)
    assert infer_usage_tags(("SaaS 产品融资路演 deck",)) == ("investor-pitch",)
    assert infer_usage_tags(("新员工入职培训课件",)) == ("training-workshop",)
    assert infer_usage_tags(("本周项目进展与里程碑状态更新",)) == ("project-status",)
    assert infer_usage_tags(("AI 产品功能演示 walkthrough",)) == ("product-demo",)


def test_infer_document_and_slide_usage_uses_outline_context():
    document_tags, slide_tags = infer_document_and_slide_usage(
        "研究生论文答辩",
        "本次研究包含实验设计、结果分析与模型评估。",
        [
            {
                "slide_number": 2,
                "title": "实验结果",
                "content_brief": "展示实验数据、指标和评估结论",
                "key_points": ["实验结果", "评估指标"],
            }
        ],
    )

    assert document_tags == ("academic-report",)
    assert slide_tags[2] == ("academic-report",)


def test_infer_document_and_slide_usage_keeps_slide_tags_local_to_the_slide():
    document_tags, slide_tags = infer_document_and_slide_usage(
        "Q2 商业复盘",
        "整份文档主要讲商业复盘、经营分析和增长策略。",
        [
            {
                "slide_number": 2,
                "title": "实验结果",
                "content_brief": "展示实验数据、模型评估与论文结论",
                "key_points": ["实验结果", "模型评估"],
            }
        ],
    )

    assert document_tags == ("business-report",)
    assert slide_tags[2][0] == "academic-report"
    assert "business-report" in slide_tags[2]


def test_get_layout_catalog_includes_usage_metadata():
    catalog = get_layout_catalog()
    assert "角色:" in catalog
    assert "适用领域" in catalog
    assert "职责:" in catalog
    assert "结构:" in catalog
    assert "变体:" in catalog
    assert "设计:" in catalog
    assert "适用时机:" in catalog
    assert "避免时机:" in catalog
    assert "usage 偏向:" in catalog
    assert "学术汇报" in catalog
    assert "商业汇报" in catalog
    assert "图标立柱要点 (icon-pillars)" in catalog
    assert "用于正文中分点说明 3-4 个能力、优势或结论" in catalog


def test_get_layout_variant_catalog_describes_role_to_variant_tracks():
    catalog = get_layout_variant_catalog()
    assert "角色 `narrative` / 子组 `icon-points` / 变体 `icon-pillars`" in catalog
    assert "`bullet-with-icons`(图标要点)" in catalog
    assert "角色 `evidence` / 子组 `stat-summary` / 变体 `kpi-grid`" in catalog


def test_layout_registry_exposes_variant_metadata_for_trial_and_default_groups():
    bullet_layout = get_layout("bullet-with-icons")
    assert bullet_layout is not None
    assert bullet_layout.group == "narrative"
    assert bullet_layout.sub_group == "icon-points"
    assert bullet_layout.variant_id == "icon-pillars"
    assert bullet_layout.variant_label == "图标立柱要点"
    assert bullet_layout.design_traits.tone == "assertive"
    assert bullet_layout.design_traits.style == "icon-led"
    assert bullet_layout.design_traits.density == "medium"
    assert bullet_layout.notes.purpose.startswith("用于正文中分点说明")
    assert "图标分点结构" in bullet_layout.notes.structure_signal

    outline_layout = get_layout("outline-slide")
    assert outline_layout is not None
    assert outline_layout.group == "agenda"
    assert outline_layout.sub_group == "default"
    assert outline_layout.variant_id == "section-cards"
    assert outline_layout.variant_label == "章节卡片目录"
    assert outline_layout.design_traits.tone == "formal"
    assert outline_layout.design_traits.style == "card-based"
    assert outline_layout.design_traits.density == "medium"
    assert outline_layout.description.startswith("用于交代整份演示的章节骨架")
    assert outline_layout.notes.use_when.startswith("当目录需要让 4-10 个章节被并列扫读")


def test_sibling_layout_notes_stay_distinct_after_runtime_sync():
    bullet_layout = get_layout("bullet-with-icons")
    bullet_cards_layout = get_layout("bullet-with-icons-cards")
    metrics_layout = get_layout("metrics-slide")
    metrics_band_layout = get_layout("metrics-slide-band")
    steps_layout = get_layout("numbered-bullets")
    track_layout = get_layout("numbered-bullets-track")
    thank_you_layout = get_layout("thank-you")
    thank_you_contact_layout = get_layout("thank-you-contact")

    assert bullet_layout is not None
    assert bullet_cards_layout is not None
    assert "一句结论配一个图标锚点" in bullet_layout.notes.use_when
    assert "独立卡片边界" in bullet_cards_layout.notes.use_when
    assert "较完整的标题或说明卡片" in bullet_layout.notes.avoid_when
    assert "轻量并列结论" in bullet_cards_layout.notes.avoid_when

    assert metrics_layout is not None
    assert metrics_band_layout is not None
    assert "同一视觉层级上并列展示 2-4 个核心数字" in metrics_layout.notes.use_when
    assert "executive summary 先抢占注意力" in metrics_band_layout.notes.use_when
    assert "横向结论带先抢占注意力" in metrics_layout.notes.avoid_when
    assert "同一视觉层级并列出现" in metrics_band_layout.notes.avoid_when

    assert steps_layout is not None
    assert track_layout is not None
    assert "彼此相对独立但有顺序的执行动作" in steps_layout.notes.use_when
    assert "阶段递进或 rollout 轨道感" in track_layout.notes.use_when
    assert "连续推进轨道" in steps_layout.notes.avoid_when
    assert "彼此独立的步骤要点、方法清单" in track_layout.notes.avoid_when

    assert thank_you_layout is not None
    assert thank_you_contact_layout is not None
    assert "而不需要额外行动信息" in thank_you_layout.notes.use_when
    assert "继续联系、预约、跟进，或采取下一步行动" in thank_you_contact_layout.notes.use_when
    assert "明确联系方式和下一步行动" in thank_you_layout.notes.avoid_when
    assert "联系方式抢走收尾留白" in thank_you_contact_layout.notes.avoid_when


def test_layout_role_mapping_matches_expected_layout_roles():
    assert get_layout_role("intro-slide") == "cover"
    assert get_layout_role("outline-slide") == "agenda"
    assert get_layout_role("section-header") == "section-divider"
    assert get_layout_role("metrics-slide") == "evidence"
    assert get_layout_role("two-column-compare") == "comparison"
    assert get_layout_role("timeline") == "process"
    assert get_layout_role("quote-slide") == "highlight"
    assert get_layout_role("thank-you") == "closing"


def test_layout_variant_mapping_matches_expected_layout_variants():
    assert get_layout_variant("bullet-with-icons") == "icon-pillars"
    assert get_layout_variant("image-and-description") == "media-feature"
    assert get_layout_variant("bullet-icons-only") == "icon-matrix"
    assert get_layout_variant("metrics-slide") == "kpi-grid"
    assert get_layout_variant("timeline") == "timeline-band"

    assert get_layout_variant_label("narrative", "icon-pillars") == "图标立柱要点"
    assert get_layout_variant_description("narrative", "media-feature").startswith("以一张主视觉")
    assert get_variants_for_role("narrative") == (
        "icon-pillars",
        "feature-cards",
        "media-feature",
        "icon-matrix",
    )
    assert get_variants_for_role("evidence") == (
        "kpi-grid",
        "summary-band",
        "context-metrics",
        "chart-takeaways",
        "data-matrix",
    )
    assert get_variants_for_role("cover") == ("title-centered", "title-left")


def test_layout_role_contract_describes_page_function_and_formal_sub_groups():
    assert get_layout_role_description("cover").startswith("定义演示开场身份")
    assert get_layout_role_description("narrative").startswith("承接常规正文叙述")
    assert is_variant_pilot_role("narrative") is True
    assert is_variant_pilot_role("evidence") is True
    assert is_variant_pilot_role("comparison") is True

    contract = format_role_contract_for_prompt()
    assert "`cover`" in contract
    assert "`agenda`" in contract
    assert "存在正式 sub-group" in contract


def test_normalize_outline_items_roles_handles_legacy_categories_and_structure_rules():
    items = normalize_outline_items_roles(
        [
            {
                "slide_number": 1,
                "title": "封面",
                "suggested_layout_category": "bullets",
            },
            {
                "slide_number": 2,
                "title": "背景",
                "suggested_layout_category": "metrics",
            },
            {
                "slide_number": 3,
                "title": "章节页 A",
                "suggested_layout_category": "section",
            },
            {
                "slide_number": 4,
                "title": "章节页 B",
                "suggested_slide_role": "section-divider",
            },
            {
                "slide_number": 5,
                "title": "收尾",
                "suggested_layout_category": "bullets",
            },
        ],
        num_pages=5,
    )

    assert [item["suggested_slide_role"] for item in items] == [
        "cover",
        "agenda",
        "narrative",
        "narrative",
        "closing",
    ]
    assert all("suggested_layout_category" not in item for item in items)


def test_normalize_outline_items_roles_for_three_page_deck_keeps_cover_body_closing():
    items = normalize_outline_items_roles(
        [
            {"slide_number": 1, "title": "封面", "suggested_slide_role": "highlight"},
            {"slide_number": 2, "title": "正文", "suggested_slide_role": "comparison"},
            {"slide_number": 3, "title": "结尾", "suggested_slide_role": "process"},
        ],
        num_pages=3,
    )

    assert [item["suggested_slide_role"] for item in items] == [
        "cover",
        "comparison",
        "closing",
    ]


def test_normalize_outline_items_roles_preserves_valid_section_dividers_for_longer_decks():
    items = normalize_outline_items_roles(
        [
            {"slide_number": 1, "title": "封面", "suggested_slide_role": "cover"},
            {"slide_number": 2, "title": "目录", "suggested_slide_role": "agenda"},
            {"slide_number": 3, "title": "背景", "suggested_slide_role": "narrative"},
            {"slide_number": 4, "title": "第一部分", "suggested_slide_role": "section-divider"},
            {"slide_number": 5, "title": "结果", "suggested_slide_role": "evidence"},
            {"slide_number": 6, "title": "第二部分", "suggested_slide_role": "section-divider"},
            {"slide_number": 7, "title": "流程", "suggested_slide_role": "process"},
            {"slide_number": 8, "title": "致谢", "suggested_slide_role": "closing"},
        ],
        num_pages=8,
    )

    assert [item["suggested_slide_role"] for item in items] == [
        "cover",
        "agenda",
        "narrative",
        "section-divider",
        "evidence",
        "section-divider",
        "process",
        "closing",
    ]


def test_normalize_outline_items_roles_infers_content_roles_when_missing():
    items = normalize_outline_items_roles(
        [
            {"slide_number": 1, "title": "AI 时代的人才策略"},
            {
                "slide_number": 2,
                "title": "市场规模与增长数据",
                "content_brief": "展示 adoption、ROI 与增长趋势。",
                "key_points": ["渗透率 63%", "ROI 提升 28%"],
            },
            {
                "slide_number": 3,
                "title": "手工流程 vs AI 流程",
                "content_brief": "对照传统方式与自动化方式的差异。",
                "key_points": ["现状", "目标"],
            },
            {
                "slide_number": 4,
                "title": "落地实施路径",
                "content_brief": "分阶段说明 rollout 计划。",
                "key_points": ["试点", "推广", "复盘"],
            },
            {
                "slide_number": 5,
                "title": "核心结论",
                "content_brief": "一句话总结最关键判断。",
                "key_points": ["AI 将重塑岗位分工"],
            },
            {"slide_number": 6, "title": "谢谢"},
        ],
        num_pages=6,
    )

    assert [item["suggested_slide_role"] for item in items] == [
        "cover",
        "agenda",
        "comparison",
        "process",
        "highlight",
        "closing",
    ]


def test_stage_select_layouts_prompt_contains_usage_guidance(monkeypatch):
    async def _case():
        from app.services.agents import layout_selector as layout_selector_mod

        agent = _FakeLayoutSelectorAgent(
            [
                {
                    "slide_number": 1,
                    "group": "cover",
                    "sub_group": "default",
                    "layout_id": "intro-slide",
                    "reason": "标题页",
                },
                {
                    "slide_number": 2,
                    "group": "evidence",
                    "sub_group": "default",
                    "layout_id": "chart-with-bullets",
                    "reason": "实验结果更适合图表",
                },
            ]
        )
        monkeypatch.setattr(layout_selector_mod, "layout_selector_agent", agent, raising=False)

        state = PipelineState(
            raw_content="研究生论文答辩，包含实验设计与结果分析。",
            topic="研究生论文答辩：多模态检索实验结果",
            num_pages=3,
            outline={
                "items": [
                    {
                        "slide_number": 1,
                        "title": "封面",
                        "suggested_slide_role": "cover",
                        "key_points": ["研究背景"],
                    },
                    {
                        "slide_number": 2,
                        "title": "实验结果",
                        "content_brief": "展示实验结果、对比图表与评估结论",
                        "suggested_slide_role": "evidence",
                        "key_points": ["实验结果", "模型评估", "图表对比"],
                    },
                    {
                        "slide_number": 3,
                        "title": "致谢",
                        "suggested_slide_role": "closing",
                        "key_points": ["感谢聆听"],
                    },
                ]
            },
        )

        await stage_select_layouts(state)

        assert len(agent.prompts) == 1
        prompt = agent.prompts[0]
        assert "可用布局列表:" in prompt
        assert "文档级 Usage 推断: 学术汇报" in prompt
        assert "页内 Usage:" in prompt
        assert "角色: evidence" in prompt
        assert "角色匹配布局: `metrics-slide`, `metrics-slide-band`, `metrics-with-image`, `chart-with-bullets`, `table-info`" in prompt
        assert "候选子组:" in prompt
        assert "`stat-summary`(指标概览:" in prompt
        assert "`visual-evidence`(图像佐证:" in prompt
        assert "`chart-analysis`(图表解读:" in prompt
        assert "`table-matrix`(表格矩阵:" in prompt
        assert "优先候选变体:" in prompt
        assert "`chart-takeaways`" in prompt
        assert "系统会在你选中的 variant_id 下再解析具体 layout_id" in prompt
        assert "请为每页输出 group、sub_group、variant_id 和 reason。不要输出 layout_id。" in prompt

    asyncio.run(_case())


def test_stage_select_layouts_prompt_falls_back_when_usage_missing(monkeypatch):
    async def _case():
        from app.services.agents import layout_selector as layout_selector_mod

        agent = _FakeLayoutSelectorAgent(
            [
                {
                    "slide_number": 1,
                    "group": "narrative",
                    "sub_group": "icon-points",
                    "layout_id": "bullet-with-icons",
                    "reason": "默认要点布局",
                }
            ]
        )
        monkeypatch.setattr(layout_selector_mod, "layout_selector_agent", agent, raising=False)

        state = PipelineState(
            raw_content="这里是一段中性说明，没有明显场景词。",
            topic="通用说明",
            num_pages=1,
            outline={
                "items": [
                    {
                        "slide_number": 1,
                        "title": "概览",
                        "content_brief": "介绍主要内容",
                        "suggested_slide_role": "narrative",
                        "key_points": ["概览", "背景"],
                    }
                ]
            },
        )

        await stage_select_layouts(state)

        prompt = agent.prompts[0]
        assert "文档级 Usage 推断: 未命中" in prompt
        assert "无明确 usage 候选，按结构和设计方向选择" in prompt

    asyncio.run(_case())


def test_adjacent_layout_diversity_skips_exempt_fixed_roles():
    adjusted = _enforce_adjacent_layout_diversity(
        [
            {
                "slide_number": 1,
                "group": "cover",
                "sub_group": "default",
                "variant_id": "title-centered",
                "layout_id": "intro-slide",
                "design_traits": {"tone": "bold", "style": "editorial", "density": "low"},
                "reason": "cover",
            },
            {
                "slide_number": 2,
                "group": "cover",
                "sub_group": "default",
                "variant_id": "title-centered",
                "layout_id": "intro-slide",
                "design_traits": {"tone": "bold", "style": "editorial", "density": "low"},
                "reason": "cover-repeat",
            },
        ],
        document_usage_tags=(),
        slide_usage_tags={},
        layout_entries=get_all_layouts(),
        rank_layouts_by_usage_fn=rank_layouts_by_usage,
    )

    assert adjusted[1]["layout_id"] == "intro-slide"
    assert adjusted[1]["variant_id"] == "title-centered"
    assert adjusted[1]["reason"] == "cover-repeat"


def test_adjacent_layout_diversity_keeps_repeat_when_no_safe_sibling_exists():
    adjusted = _enforce_adjacent_layout_diversity(
        [
            {
                "slide_number": 1,
                "group": "narrative",
                "sub_group": "visual-explainer",
                "variant_id": "media-feature",
                "layout_id": "image-and-description",
                "design_traits": {"tone": "editorial", "style": "editorial", "density": "medium"},
                "reason": "visual-a",
            },
            {
                "slide_number": 2,
                "group": "narrative",
                "sub_group": "visual-explainer",
                "variant_id": "media-feature",
                "layout_id": "image-and-description",
                "design_traits": {"tone": "editorial", "style": "editorial", "density": "medium"},
                "reason": "visual-b",
            },
        ],
        document_usage_tags=("product-demo",),
        slide_usage_tags={},
        layout_entries=get_all_layouts(),
        rank_layouts_by_usage_fn=rank_layouts_by_usage,
    )

    assert adjusted[1]["layout_id"] == "image-and-description"
    assert adjusted[1]["variant_id"] == "media-feature"
    assert adjusted[1]["reason"] == "visual-b"


def test_stage_select_layouts_rebalances_adjacent_duplicate_layouts(monkeypatch):
    async def _case():
        from app.services.agents import layout_selector as layout_selector_mod

        agent = _FakeLayoutSelectorAgent(
            [
                {
                    "slide_number": 1,
                    "group": "cover",
                    "sub_group": "default",
                    "layout_id": "intro-slide",
                    "reason": "cover",
                },
                {
                    "slide_number": 2,
                    "group": "agenda",
                    "sub_group": "default",
                    "layout_id": "outline-slide",
                    "reason": "agenda",
                },
                {
                    "slide_number": 3,
                    "group": "process",
                    "sub_group": "step-flow",
                    "layout_id": "numbered-bullets",
                    "reason": "step-a",
                },
                {
                    "slide_number": 4,
                    "group": "process",
                    "sub_group": "step-flow",
                    "layout_id": "numbered-bullets",
                    "reason": "step-b",
                },
                {
                    "slide_number": 5,
                    "group": "closing",
                    "sub_group": "default",
                    "layout_id": "thank-you",
                    "reason": "closing",
                },
            ]
        )
        monkeypatch.setattr(layout_selector_mod, "layout_selector_agent", agent, raising=False)

        state = PipelineState(
            raw_content="The deck includes two consecutive process slides that should not repeat the same layout.",
            topic="Delivery plan",
            num_pages=5,
            outline={
                "items": [
                    {"slide_number": 1, "title": "Cover", "suggested_slide_role": "cover"},
                    {"slide_number": 2, "title": "Agenda", "suggested_slide_role": "agenda"},
                    {
                        "slide_number": 3,
                        "title": "Execution Step A",
                        "content_brief": "Describe the first execution step and expected output.",
                        "suggested_slide_role": "process",
                        "key_points": ["step one", "step two"],
                    },
                    {
                        "slide_number": 4,
                        "title": "Execution Step B",
                        "content_brief": "Describe the second execution step and expected output.",
                        "suggested_slide_role": "process",
                        "key_points": ["step three", "step four"],
                    },
                    {"slide_number": 5, "title": "Closing", "suggested_slide_role": "closing"},
                ]
            },
        )

        await stage_select_layouts(state)

        assert state.layout_selections[2]["layout_id"] == "numbered-bullets"
        assert state.layout_selections[3]["layout_id"] == "numbered-bullets-track"
        assert state.layout_selections[3]["variant_id"] == "progress-track"
        assert "adjusted to avoid adjacent layout repeat" in state.layout_selections[3]["reason"]

    asyncio.run(_case())


def test_stage_select_layouts_enforces_diversity_in_fallback_path(monkeypatch):
    async def _case():
        from app.services.agents import layout_selector as layout_selector_mod

        class _ExplodingLayoutSelectorAgent:
            async def run(self, prompt: str):
                raise RuntimeError("boom")

        monkeypatch.setattr(
            layout_selector_mod,
            "layout_selector_agent",
            _ExplodingLayoutSelectorAgent(),
            raising=False,
        )

        state = PipelineState(
            raw_content="This deck needs two consecutive narrative slides after the agenda.",
            topic="Product overview",
            num_pages=5,
            outline={
                "items": [
                    {"slide_number": 1, "title": "Cover", "suggested_slide_role": "cover"},
                    {"slide_number": 2, "title": "Agenda", "suggested_slide_role": "agenda"},
                    {
                        "slide_number": 3,
                        "title": "Capability A",
                        "content_brief": "Explain the first capability.",
                        "suggested_slide_role": "narrative",
                        "key_points": ["point a1", "point a2"],
                    },
                    {
                        "slide_number": 4,
                        "title": "Capability B",
                        "content_brief": "Explain the second capability.",
                        "suggested_slide_role": "narrative",
                        "key_points": ["point b1", "point b2"],
                    },
                    {"slide_number": 5, "title": "Closing", "suggested_slide_role": "closing"},
                ]
            },
        )

        await stage_select_layouts(state)

        assert state.layout_selections[2]["layout_id"] == "bullet-with-icons"
        assert state.layout_selections[3]["layout_id"] == "bullet-with-icons-cards"
        assert state.layout_selections[3]["variant_id"] == "feature-cards"
        assert "adjusted to avoid adjacent layout repeat" in state.layout_selections[3]["reason"]

    asyncio.run(_case())


def test_stage_select_layouts_rejects_layouts_from_the_wrong_role(monkeypatch):
    async def _case():
        from app.services.agents import layout_selector as layout_selector_mod

        agent = _FakeLayoutSelectorAgent(
            [
                {
                    "slide_number": 1,
                    "group": "cover",
                    "sub_group": "default",
                    "layout_id": "intro-slide",
                    "reason": "封面",
                },
                {
                    "slide_number": 2,
                    "group": "evidence",
                    "sub_group": "default",
                    "layout_id": "metrics-slide",
                    "reason": "模型误选了数据布局",
                },
                {
                    "slide_number": 3,
                    "group": "closing",
                    "sub_group": "default",
                    "layout_id": "thank-you",
                    "reason": "结束页",
                },
            ]
        )
        monkeypatch.setattr(layout_selector_mod, "layout_selector_agent", agent, raising=False)

        state = PipelineState(
            raw_content="这里是常规叙述内容。",
            topic="普通介绍",
            num_pages=3,
            outline={
                "items": [
                    {
                        "slide_number": 1,
                        "title": "封面",
                        "suggested_slide_role": "cover",
                        "key_points": ["欢迎页"],
                    },
                    {
                        "slide_number": 2,
                        "title": "概览",
                        "content_brief": "介绍主要能力与背景",
                        "suggested_slide_role": "narrative",
                        "key_points": ["能力概览", "使用方式"],
                    },
                    {
                        "slide_number": 3,
                        "title": "结束",
                        "suggested_slide_role": "closing",
                        "key_points": ["谢谢"],
                    }
                ]
            },
        )

        await stage_select_layouts(state)

        assert state.layout_selections[0]["layout_id"] == "intro-slide"
        assert state.layout_selections[0]["group"] == "cover"
        assert state.layout_selections[0]["sub_group"] == "default"
        assert state.layout_selections[0]["variant_id"] == "title-centered"
        assert state.layout_selections[0]["design_traits"]["style"] == "editorial"
        assert state.layout_selections[1]["group"] == "narrative"
        assert state.layout_selections[1]["sub_group"] == "icon-points"
        assert state.layout_selections[1]["variant_id"] == "feature-cards"
        assert state.layout_selections[1]["design_traits"]["style"] == "card-based"
        assert state.layout_selections[1]["layout_id"] == "bullet-with-icons-cards"
        assert state.layout_selections[2]["layout_id"] == "thank-you"

    asyncio.run(_case())


def test_stage_select_layouts_logs_layout_decision_trace(monkeypatch, caplog):
    async def _case():
        from app.services.agents import layout_selector as layout_selector_mod

        agent = _FakeLayoutSelectorAgent(
            [
                {
                    "slide_number": 1,
                    "group": "cover",
                    "sub_group": "default",
                    "variant_id": "title-centered",
                    "reason": "封面",
                },
                {
                    "slide_number": 2,
                    "group": "narrative",
                    "sub_group": "default",
                    "variant_id": "unknown-variant",
                    "reason": "普通正文说明",
                },
                {
                    "slide_number": 3,
                    "group": "closing",
                    "sub_group": "default",
                    "variant_id": "closing-center",
                    "reason": "结束页",
                },
            ]
        )
        monkeypatch.setattr(layout_selector_mod, "layout_selector_agent", agent, raising=False)

        state = PipelineState(
            raw_content="这是一页常规介绍页，没有截图或时间线。",
            topic="产品概览",
            num_pages=3,
            outline={
                "items": [
                    {"slide_number": 1, "title": "封面", "suggested_slide_role": "cover"},
                    {
                        "slide_number": 2,
                        "title": "主要结论",
                        "content_brief": "介绍三个核心结论和价值点。",
                        "suggested_slide_role": "narrative",
                        "key_points": ["结论一", "结论二", "结论三"],
                    },
                    {"slide_number": 3, "title": "结束", "suggested_slide_role": "closing"},
                ]
            },
        )

        caplog.set_level(logging.INFO, logger="app.services.pipeline.graph")
        await stage_select_layouts(state)

        records = [
            record
            for record in caplog.records
            if record.message == "Layout decision resolved"
            and getattr(record, "slide_number", None) == 2
        ]
        assert len(records) == 1
        record = records[0]
        assert record.selection_source == "model"
        assert record.outline_role == "narrative"
        assert record.requested_sub_group == "default"
        assert record.resolved_sub_group == "icon-points"
        assert record.requested_variant_id == "unknown-variant"
        assert record.resolved_variant_id == "icon-pillars"
        assert record.final_layout_id == "bullet-with-icons"
        assert record.diversity_adjusted is False
        assert record.used_safety_default is False

    asyncio.run(_case())


def test_stage_select_layouts_fallback_uses_capability_grid_for_four_capabilities(monkeypatch):
    async def _case():
        from app.services.agents import layout_selector as layout_selector_mod

        class _ExplodingLayoutSelectorAgent:
            async def run(self, prompt: str):
                raise RuntimeError("boom")

        monkeypatch.setattr(
            layout_selector_mod,
            "layout_selector_agent",
            _ExplodingLayoutSelectorAgent(),
            raising=False,
        )

        state = PipelineState(
            raw_content="这一页要总览四个核心能力模块。",
            topic="产品能力总览",
            num_pages=3,
            outline={
                "items": [
                    {"slide_number": 1, "title": "封面", "suggested_slide_role": "cover"},
                    {
                        "slide_number": 2,
                        "title": "核心能力矩阵",
                        "content_brief": "总览四个能力模块与适用场景。",
                        "suggested_slide_role": "narrative",
                        "key_points": ["能力一", "能力二", "能力三", "能力四"],
                    },
                    {"slide_number": 3, "title": "结束", "suggested_slide_role": "closing"},
                ]
            },
        )

        await stage_select_layouts(state)

        assert state.layout_selections[1]["sub_group"] == "capability-grid"
        assert state.layout_selections[1]["layout_id"] == "bullet-icons-only"
        assert state.layout_selections[1]["reason"] == "fallback"

    asyncio.run(_case())


def test_stage_select_layouts_maps_narrative_sub_group_to_layout(monkeypatch):
    async def _case():
        from app.services.agents import layout_selector as layout_selector_mod

        agent = _FakeLayoutSelectorAgent(
            [
                {
                    "slide_number": 1,
                    "group": "cover",
                    "sub_group": "default",
                    "layout_id": "intro-slide",
                    "reason": "封面",
                },
                {
                    "slide_number": 2,
                    "group": "narrative",
                    "sub_group": "visual-explainer",
                    "layout_id": "bullet-with-icons",
                    "reason": "这页需要图文案例说明",
                },
                {
                    "slide_number": 3,
                    "group": "closing",
                    "sub_group": "default",
                    "layout_id": "thank-you",
                    "reason": "结束页",
                },
            ]
        )
        monkeypatch.setattr(layout_selector_mod, "layout_selector_agent", agent, raising=False)

        state = PipelineState(
            raw_content="这里包含一个产品案例与界面截图说明。",
            topic="案例说明",
            num_pages=3,
            outline={
                "items": [
                    {
                        "slide_number": 1,
                        "title": "封面",
                        "suggested_slide_role": "cover",
                        "key_points": ["欢迎页"],
                    },
                    {
                        "slide_number": 2,
                        "title": "案例展示",
                        "content_brief": "通过产品界面截图和案例讲解说明主要价值。",
                        "suggested_slide_role": "narrative",
                        "key_points": ["案例背景", "界面截图", "价值说明"],
                    },
                    {
                        "slide_number": 3,
                        "title": "结束",
                        "suggested_slide_role": "closing",
                        "key_points": ["谢谢"],
                    },
                ]
            },
        )

        await stage_select_layouts(state)

        assert state.layout_selections[1]["group"] == "narrative"
        assert state.layout_selections[1]["sub_group"] == "visual-explainer"
        assert state.layout_selections[1]["layout_id"] == "image-and-description"
        assert state.layout_selections[1]["variant_id"] == "media-feature"
        assert state.layout_selections[1]["design_traits"]["style"] == "editorial"

    asyncio.run(_case())


def test_stage_select_layouts_normalizes_invalid_sub_group_before_layout_fallback(monkeypatch):
    async def _case():
        from app.services.agents import layout_selector as layout_selector_mod

        agent = _FakeLayoutSelectorAgent(
            [
                {
                    "slide_number": 1,
                    "group": "cover",
                    "sub_group": "default",
                    "layout_id": "intro-slide",
                    "reason": "封面",
                },
                {
                    "slide_number": 2,
                    "group": "narrative",
                    "sub_group": "default",
                    "layout_id": "bullet-with-icons",
                    "reason": "模型没有识别结构层",
                },
                {
                    "slide_number": 3,
                    "group": "closing",
                    "sub_group": "default",
                    "layout_id": "thank-you",
                    "reason": "结束页",
                },
            ]
        )
        monkeypatch.setattr(layout_selector_mod, "layout_selector_agent", agent, raising=False)

        state = PipelineState(
            raw_content="这一页需要通过产品界面截图和案例说明来解释能力价值。",
            topic="案例说明",
            num_pages=3,
            outline={
                "items": [
                    {
                        "slide_number": 1,
                        "title": "封面",
                        "suggested_slide_role": "cover",
                        "key_points": ["欢迎页"],
                    },
                    {
                        "slide_number": 2,
                        "title": "案例展示",
                        "content_brief": "通过产品界面截图和案例讲解说明主要价值。",
                        "suggested_slide_role": "narrative",
                        "key_points": ["案例背景", "界面截图", "价值说明"],
                    },
                    {
                        "slide_number": 3,
                        "title": "结束",
                        "suggested_slide_role": "closing",
                        "key_points": ["谢谢"],
                    },
                ]
            },
        )

        await stage_select_layouts(state)

        assert state.layout_selections[1]["group"] == "narrative"
        assert state.layout_selections[1]["sub_group"] == "visual-explainer"
        assert state.layout_selections[1]["layout_id"] == "image-and-description"
        assert state.layout_selections[1]["variant_id"] == "media-feature"
        assert state.layout_selections[1]["design_traits"]["style"] == "editorial"

    asyncio.run(_case())


def test_stage_select_layouts_normalizes_invalid_evidence_sub_group(monkeypatch):
    async def _case():
        from app.services.agents import layout_selector as layout_selector_mod

        agent = _FakeLayoutSelectorAgent(
            [
                {
                    "slide_number": 1,
                    "group": "cover",
                    "sub_group": "default",
                    "layout_id": "intro-slide",
                    "reason": "封面",
                },
                {
                    "slide_number": 2,
                    "group": "evidence",
                    "sub_group": "visual-explainer",
                    "layout_id": "image-and-description",
                    "reason": "模型误把论据页当成 narrative 图文说明",
                },
                {
                    "slide_number": 3,
                    "group": "closing",
                    "sub_group": "default",
                    "layout_id": "thank-you",
                    "reason": "结束页",
                },
            ]
        )
        monkeypatch.setattr(layout_selector_mod, "layout_selector_agent", agent, raising=False)

        state = PipelineState(
            raw_content="这一页展示关键指标和实验结论。",
            topic="实验结果",
            num_pages=3,
            outline={
                "items": [
                    {
                        "slide_number": 1,
                        "title": "封面",
                        "suggested_slide_role": "cover",
                        "key_points": ["欢迎页"],
                    },
                    {
                        "slide_number": 2,
                        "title": "关键指标",
                        "content_brief": "通过核心指标和结果结论说明实验表现。",
                        "suggested_slide_role": "evidence",
                        "key_points": ["实验结果", "关键指标", "结论"],
                    },
                    {
                        "slide_number": 3,
                        "title": "结束",
                        "suggested_slide_role": "closing",
                        "key_points": ["谢谢"],
                    },
                ]
            },
        )

        await stage_select_layouts(state)

        assert state.layout_selections[1]["group"] == "evidence"
        assert state.layout_selections[1]["sub_group"] == "stat-summary"
        assert state.layout_selections[1]["layout_id"] != "image-and-description"
        assert state.layout_selections[1]["layout_id"] == "metrics-slide"
        assert state.layout_selections[1]["variant_id"] == "kpi-grid"
        assert state.layout_selections[1]["design_traits"] == {
            "tone": "formal",
            "style": "data-first",
            "density": "medium",
        }

    asyncio.run(_case())


def test_stage_select_layouts_maps_evidence_chart_analysis_to_chart_layout(monkeypatch):
    async def _case():
        from app.services.agents import layout_selector as layout_selector_mod

        agent = _FakeLayoutSelectorAgent(
            [
                {
                    "slide_number": 1,
                    "group": "cover",
                    "sub_group": "default",
                    "layout_id": "intro-slide",
                    "reason": "封面",
                },
                {
                    "slide_number": 2,
                    "group": "evidence",
                    "sub_group": "chart-analysis",
                    "layout_id": "metrics-slide",
                    "reason": "需要图表与分析结论并置",
                },
                {
                    "slide_number": 3,
                    "group": "closing",
                    "sub_group": "default",
                    "layout_id": "thank-you",
                    "reason": "结束页",
                },
            ]
        )
        monkeypatch.setattr(layout_selector_mod, "layout_selector_agent", agent, raising=False)

        state = PipelineState(
            raw_content="这一页展示趋势图表、同比变化和两条关键 takeaway。",
            topic="实验结果分析",
            num_pages=3,
            outline={
                "items": [
                    {"slide_number": 1, "title": "封面", "suggested_slide_role": "cover"},
                    {
                        "slide_number": 2,
                        "title": "趋势图表分析",
                        "content_brief": "通过图表展示趋势变化，并总结关键结论。",
                        "suggested_slide_role": "evidence",
                        "key_points": ["图表趋势", "同比变化", "关键 takeaway"],
                    },
                    {"slide_number": 3, "title": "结束", "suggested_slide_role": "closing"},
                ]
            },
        )

        await stage_select_layouts(state)

        assert state.layout_selections[1]["sub_group"] == "chart-analysis"
        assert state.layout_selections[1]["layout_id"] == "chart-with-bullets"
        assert state.layout_selections[1]["variant_id"] == "chart-takeaways"

    asyncio.run(_case())


def test_stage_select_layouts_infers_process_timeline_sub_group(monkeypatch):
    async def _case():
        from app.services.agents import layout_selector as layout_selector_mod

        agent = _FakeLayoutSelectorAgent(
            [
                {
                    "slide_number": 1,
                    "group": "cover",
                    "sub_group": "default",
                    "layout_id": "intro-slide",
                    "reason": "封面",
                },
                {
                    "slide_number": 2,
                    "group": "process",
                    "sub_group": "default",
                    "layout_id": "numbered-bullets",
                    "reason": "模型没有识别时间线结构",
                },
                {
                    "slide_number": 3,
                    "group": "closing",
                    "sub_group": "default",
                    "layout_id": "thank-you",
                    "reason": "结束页",
                },
            ]
        )
        monkeypatch.setattr(layout_selector_mod, "layout_selector_agent", agent, raising=False)

        state = PipelineState(
            raw_content="按季度推进 roadmap，包含里程碑与阶段目标。",
            topic="项目里程碑",
            num_pages=3,
            outline={
                "items": [
                    {"slide_number": 1, "title": "封面", "suggested_slide_role": "cover"},
                    {
                        "slide_number": 2,
                        "title": "季度里程碑",
                        "content_brief": "按时间线展示阶段推进和关键里程碑。",
                        "suggested_slide_role": "process",
                        "key_points": ["Q1", "Q2", "里程碑"],
                    },
                    {"slide_number": 3, "title": "结束", "suggested_slide_role": "closing"},
                ]
            },
        )

        await stage_select_layouts(state)

        assert state.layout_selections[1]["sub_group"] == "timeline-milestone"
        assert state.layout_selections[1]["layout_id"] == "timeline"
        assert state.layout_selections[1]["variant_id"] == "timeline-band"

    asyncio.run(_case())


def test_stage_select_layouts_infers_comparison_response_mapping(monkeypatch):
    async def _case():
        from app.services.agents import layout_selector as layout_selector_mod

        agent = _FakeLayoutSelectorAgent(
            [
                {
                    "slide_number": 1,
                    "group": "cover",
                    "sub_group": "default",
                    "layout_id": "intro-slide",
                    "reason": "封面",
                },
                {
                    "slide_number": 2,
                    "group": "comparison",
                    "sub_group": "default",
                    "layout_id": "two-column-compare",
                    "reason": "模型没有识别挑战到方案映射",
                },
                {
                    "slide_number": 3,
                    "group": "closing",
                    "sub_group": "default",
                    "layout_id": "thank-you",
                    "reason": "结束页",
                },
            ]
        )
        monkeypatch.setattr(layout_selector_mod, "layout_selector_agent", agent, raising=False)

        state = PipelineState(
            raw_content="先说明客户痛点，再给出对应方案和结果。",
            topic="挑战与回应",
            num_pages=3,
            outline={
                "items": [
                    {"slide_number": 1, "title": "封面", "suggested_slide_role": "cover"},
                    {
                        "slide_number": 2,
                        "title": "挑战与方案",
                        "content_brief": "将客户痛点映射到具体回应方案和结果。",
                        "suggested_slide_role": "comparison",
                        "key_points": ["客户挑战", "对应方案", "最终结果"],
                    },
                    {"slide_number": 3, "title": "结束", "suggested_slide_role": "closing"},
                ]
            },
        )

        await stage_select_layouts(state)

        assert state.layout_selections[1]["sub_group"] == "response-mapping"
        assert state.layout_selections[1]["layout_id"] == "challenge-outcome"
        assert state.layout_selections[1]["variant_id"] == "challenge-response"

    asyncio.run(_case())


def test_stage_select_layouts_uses_safety_layout_when_default_layout_is_missing(monkeypatch):
    async def _case():
        from app.models import layout_registry as layout_registry_mod
        from app.services.agents import layout_selector as layout_selector_mod

        original_get_layout = layout_registry_mod.get_layout

        def _fake_get_layout(layout_id: str):
            if layout_id == "image-and-description":
                return None
            return original_get_layout(layout_id)

        monkeypatch.setattr(layout_registry_mod, "get_layout", _fake_get_layout)

        agent = _FakeLayoutSelectorAgent(
            [
                {
                    "slide_number": 1,
                    "group": "cover",
                    "sub_group": "default",
                    "layout_id": "intro-slide",
                    "reason": "封面",
                },
                {
                    "slide_number": 2,
                    "group": "narrative",
                    "sub_group": "visual-explainer",
                    "layout_id": "image-and-description",
                    "reason": "需要图文案例说明",
                },
                {
                    "slide_number": 3,
                    "group": "closing",
                    "sub_group": "default",
                    "layout_id": "thank-you",
                    "reason": "结束页",
                },
            ]
        )
        monkeypatch.setattr(layout_selector_mod, "layout_selector_agent", agent, raising=False)

        state = PipelineState(
            raw_content="这一页需要通过产品界面截图和案例说明来解释能力价值。",
            topic="案例说明",
            num_pages=3,
            outline={
                "items": [
                    {
                        "slide_number": 1,
                        "title": "封面",
                        "suggested_slide_role": "cover",
                        "key_points": ["欢迎页"],
                    },
                    {
                        "slide_number": 2,
                        "title": "案例展示",
                        "content_brief": "通过产品界面截图和案例讲解说明主要价值。",
                        "suggested_slide_role": "narrative",
                        "key_points": ["案例背景", "界面截图", "价值说明"],
                    },
                    {
                        "slide_number": 3,
                        "title": "结束",
                        "suggested_slide_role": "closing",
                        "key_points": ["谢谢"],
                    },
                ]
            },
        )

        await stage_select_layouts(state)

        assert state.layout_selections[1]["layout_id"] == "bullet-with-icons"
        assert state.layout_selections[1]["variant_id"] == "icon-pillars"
        assert state.layout_selections[1]["design_traits"]["style"] == "icon-led"

    asyncio.run(_case())

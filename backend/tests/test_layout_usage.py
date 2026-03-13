import asyncio
from types import SimpleNamespace

from app.models.layout_registry import (
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
from app.services.pipeline.graph import PipelineState, stage_select_layouts
from app.services.pipeline.layout_usage import infer_document_and_slide_usage, infer_usage_tags


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
    assert "变体:" in catalog
    assert "适用领域" in catalog
    assert "职责:" in catalog
    assert "结构:" in catalog
    assert "设计:" in catalog
    assert "适用时机:" in catalog
    assert "避免时机:" in catalog
    assert "usage 偏向:" in catalog
    assert "学术汇报" in catalog
    assert "商业汇报" in catalog
    assert "图标要点 (icon-points)" in catalog
    assert "用于正文中分点说明 3-4 个能力、优势或结论" in catalog


def test_get_layout_variant_catalog_describes_role_to_variant_tracks():
    catalog = get_layout_variant_catalog()
    assert "角色 `narrative` / 变体 `icon-points`" in catalog
    assert "`bullet-with-icons`(图标要点)" in catalog
    assert "角色 `evidence` / 变体 `default`" in catalog


def test_layout_registry_exposes_variant_metadata_for_trial_and_default_groups():
    bullet_layout = get_layout("bullet-with-icons")
    assert bullet_layout is not None
    assert bullet_layout.group == "narrative"
    assert bullet_layout.sub_group == "icon-points"
    assert bullet_layout.variant.composition == "icon-columns"
    assert bullet_layout.variant.tone == "assertive"
    assert bullet_layout.variant.style == "icon-led"
    assert bullet_layout.variant.density == "medium"
    assert bullet_layout.notes.purpose.startswith("用于正文中分点说明")
    assert "图标分点结构" in bullet_layout.notes.structure_signal

    outline_layout = get_layout("outline-slide")
    assert outline_layout is not None
    assert outline_layout.group == "agenda"
    assert outline_layout.sub_group == "default"
    assert outline_layout.variant.composition == "card-grid"
    assert outline_layout.variant.tone == "formal"
    assert outline_layout.variant.style == "card-based"
    assert outline_layout.variant.density == "medium"
    assert outline_layout.description.startswith("用于交代整份演示的章节骨架")
    assert outline_layout.notes.use_when.startswith("当你需要在正文前建立叙事顺序")


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
    assert get_layout_variant("bullet-with-icons") == "icon-points"
    assert get_layout_variant("image-and-description") == "visual-explainer"
    assert get_layout_variant("bullet-icons-only") == "capability-grid"
    assert get_layout_variant("metrics-slide") == "default"

    assert get_layout_variant_label("narrative", "icon-points") == "图标要点"
    assert get_layout_variant_description("narrative", "visual-explainer").startswith("以单张主视觉")
    assert get_variants_for_role("narrative") == (
        "icon-points",
        "visual-explainer",
        "capability-grid",
    )
    assert get_variants_for_role("cover") == ("default",)


def test_layout_role_contract_describes_page_function_and_variant_pilot():
    assert get_layout_role_description("cover").startswith("定义演示开场身份")
    assert get_layout_role_description("narrative").startswith("承接常规正文叙述")
    assert is_variant_pilot_role("narrative") is True
    assert is_variant_pilot_role("evidence") is False

    contract = format_role_contract_for_prompt()
    assert "`cover`" in contract
    assert "`agenda`" in contract
    assert "首个 variant 试点组" in contract


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
        assert "角色匹配布局: `metrics-slide`, `metrics-with-image`, `chart-with-bullets`, `table-info`" in prompt
        assert "候选子组:" in prompt
        assert "`default`(标准论据页:" in prompt
        assert "优先候选布局:" in prompt
        assert "`chart-with-bullets`" in prompt
        assert "尽量避免连续页面选择完全相同的 `layout_id`" in prompt
        assert "请为每页输出 group、sub_group、layout_id 和 reason。不要输出 variant。" in prompt

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
        assert "无明确 usage 候选，按结构选择" in prompt

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
        assert state.layout_selections[0]["variant"]["composition"] == "hero-center"
        assert state.layout_selections[1]["group"] == "narrative"
        assert state.layout_selections[1]["sub_group"] == "icon-points"
        assert state.layout_selections[1]["variant"]["composition"] == "icon-columns"
        assert state.layout_selections[1]["layout_id"] == "bullet-with-icons"
        assert state.layout_selections[2]["layout_id"] == "thank-you"

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
        assert state.layout_selections[1]["variant"]["composition"] == "media-split"

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
        assert state.layout_selections[1]["variant"]["style"] == "editorial"

    asyncio.run(_case())


def test_stage_select_layouts_forces_default_sub_group_for_non_narrative_groups(monkeypatch):
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
        assert state.layout_selections[1]["sub_group"] == "default"
        assert state.layout_selections[1]["layout_id"] != "image-and-description"
        assert state.layout_selections[1]["layout_id"] in {
            "metrics-slide",
            "metrics-with-image",
            "chart-with-bullets",
            "table-info",
        }
        assert (
            state.layout_selections[1]["variant"]
            == get_layout(state.layout_selections[1]["layout_id"]).variant.__dict__
        )

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
        assert state.layout_selections[1]["variant"]["composition"] == "icon-columns"

    asyncio.run(_case())

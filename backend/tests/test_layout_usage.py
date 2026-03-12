import asyncio
from types import SimpleNamespace

from app.models.layout_registry import get_layout_catalog
from app.services.pipeline.layout_roles import (
    format_role_contract_for_prompt,
    get_layout_role,
    get_layout_role_description,
    is_variant_pilot_role,
    normalize_outline_items_roles,
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
    assert "适用领域" in catalog
    assert "学术汇报" in catalog
    assert "商业汇报" in catalog


def test_layout_role_mapping_matches_expected_layout_roles():
    assert get_layout_role("intro-slide") == "cover"
    assert get_layout_role("outline-slide") == "agenda"
    assert get_layout_role("section-header") == "section-divider"
    assert get_layout_role("metrics-slide") == "evidence"
    assert get_layout_role("two-column-compare") == "comparison"
    assert get_layout_role("timeline") == "process"
    assert get_layout_role("quote-slide") == "highlight"
    assert get_layout_role("thank-you") == "closing"


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
                {"slide_number": 1, "layout_id": "intro-slide", "reason": "标题页"},
                {"slide_number": 2, "layout_id": "chart-with-bullets", "reason": "实验结果更适合图表"},
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
        assert "文档级 Usage 推断: 学术汇报" in prompt
        assert "页内 Usage:" in prompt
        assert "角色: evidence" in prompt
        assert "角色匹配布局: `metrics-slide`, `metrics-with-image`, `chart-with-bullets`, `table-info`" in prompt
        assert "优先候选布局:" in prompt
        assert "`chart-with-bullets`" in prompt

    asyncio.run(_case())


def test_stage_select_layouts_prompt_falls_back_when_usage_missing(monkeypatch):
    async def _case():
        from app.services.agents import layout_selector as layout_selector_mod

        agent = _FakeLayoutSelectorAgent(
            [{"slide_number": 1, "layout_id": "bullet-with-icons", "reason": "默认要点布局"}]
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
                {"slide_number": 1, "layout_id": "intro-slide", "reason": "封面"},
                {"slide_number": 2, "layout_id": "metrics-slide", "reason": "模型误选了数据布局"},
                {"slide_number": 3, "layout_id": "thank-you", "reason": "结束页"},
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
        assert state.layout_selections[1]["layout_id"] == "bullet-with-icons"
        assert state.layout_selections[2]["layout_id"] == "thank-you"

    asyncio.run(_case())

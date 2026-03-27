from app.services.generation.legacy.deck_adapter import AgentDeck, deck_to_layout_selections, deck_to_slides


def test_legacy_deck_to_slides_maps_richer_layouts_without_guessing():
    deck = AgentDeck.model_validate(
        {
            "title": "Richer Layouts",
            "slides": [
                {
                    "slideNumber": 1,
                    "title": "双栏对比",
                    "role": "comparison",
                    "left": {"heading": "旧流程", "items": ["双阶段", "工具面过大"]},
                    "right": {"heading": "新流程", "items": ["单阶段", "模板直填"]},
                },
                {
                    "slideNumber": 2,
                    "title": "实施路径",
                    "role": "process",
                    "steps": [
                        {"title": "整理摘要", "description": "先生成本地 source brief"},
                        {"title": "选择布局", "description": "按结构提示决定 layout"},
                        {"title": "填充模板", "description": "直接产出 layout-native payload"},
                        {"title": "本地审计", "description": "减少 normalizer fallback"},
                    ],
                },
                {
                    "slideNumber": 3,
                    "title": "关键句",
                    "role": "highlight",
                    "quote": "真正的问题不是模板丑，而是模板吃不到好内容。",
                    "context": "当前 presentation 质量诊断",
                },
                {
                    "slideNumber": 4,
                    "title": "谢谢",
                    "role": "closing",
                    "subtitle": "欢迎继续迭代 presentation 效果",
                    "contact": "zhiyan@example.com",
                },
            ],
        }
    )

    selections = deck_to_layout_selections(deck)
    assert [item["layout_id"] for item in selections] == [
        "two-column-compare",
        "numbered-bullets-track",
        "quote-banner",
        "thank-you-contact",
    ]

    slides = deck_to_slides(deck)
    assert slides[0].layout_type == "two-column-compare"
    assert slides[0].content_data["left"]["heading"] == "旧流程"
    assert slides[1].layout_type == "numbered-bullets-track"
    assert len(slides[1].content_data["items"]) == 4
    assert slides[2].layout_type == "quote-banner"
    assert slides[2].content_data["quote"].startswith("真正的问题")
    assert slides[3].layout_type == "thank-you-contact"
    assert slides[3].content_data["contact"] == "zhiyan@example.com"


def test_legacy_deck_to_slides_prefers_card_layout_for_dense_bullet_items():
    deck = AgentDeck.model_validate(
        {
            "title": "Cards",
            "slides": [
                {
                    "slideNumber": 1,
                    "title": "四个重点",
                    "role": "narrative",
                    "items": [
                        {"title": "问题识别", "description": "先识别内容被压平的节点"},
                        {"title": "模板匹配", "description": "让内容直接进入正确模板"},
                        {"title": "质量门槛", "description": "落盘前做 deck audit"},
                        {"title": "渲染兼容", "description": "保持 editor 与 export 不回归"},
                    ],
                }
            ],
        }
    )

    slides = deck_to_slides(deck)
    assert slides[0].layout_type == "bullet-with-icons-cards"
    assert len(slides[0].content_data["items"]) == 4
    assert slides[0].content_data["items"][0]["description"] == "先识别内容被压平的节点"

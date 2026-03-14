from app.services.presentations.normalizer import normalize_presentation_payload


def _wrap_slides(slides):
    return {
        "presentationId": "pres-test",
        "title": "测试",
        "slides": slides,
    }


def test_normalize_two_column_compare_from_items():
    payload = _wrap_slides(
        [
            {
                "slideId": "slide-1",
                "layoutId": "two-column-compare",
                "contentData": {
                    "title": "核心框架",
                    "items": [
                        {"title": "要点一", "description": "描述一"},
                        {"title": "要点二", "description": "描述二"},
                        {"title": "要点三", "description": "描述三"},
                    ],
                },
            }
        ]
    )

    normalized, changed, report = normalize_presentation_payload(payload)
    assert changed is True
    assert report["repaired_slide_count"] == 1
    content = normalized["slides"][0]["contentData"]
    assert "left" in content
    assert "right" in content
    assert content["left"]["heading"] == "要点 A"
    assert isinstance(content["left"]["items"], list)
    assert isinstance(content["right"]["items"], list)


def test_normalize_intro_slide_presenter_to_author():
    payload = _wrap_slides(
        [
            {
                "slideId": "slide-intro",
                "layoutId": "intro-slide",
                "contentData": {
                    "title": "项目介绍",
                    "subtitle": "副标题",
                    "presenter": "张三",
                    "date": "2026",
                },
            }
        ]
    )

    normalized, changed, report = normalize_presentation_payload(payload)
    assert changed is True
    assert "intro-slide-shape" in report["repair_types"]
    content = normalized["slides"][0]["contentData"]
    assert content["author"] == "张三"
    assert "presenter" not in content


def test_normalize_bullet_with_icons_placeholder_aliases_to_status_state():
    payload = _wrap_slides(
        [
            {
                "slideId": "slide-bullets",
                "layoutId": "bullet-with-icons",
                "contentData": {
                    "title": "Key findings",
                    "items": [
                        {"title": "Content unavailable", "description": "Content unavailable"},
                        {"title": "Fallback generated", "description": "Fallback generated"},
                    ],
                },
            }
        ]
    )

    normalized, changed, report = normalize_presentation_payload(payload)
    assert changed is True
    assert "bullet-with-icons-fallback-state" in report["repair_types"]
    content = normalized["slides"][0]["contentData"]
    assert content == {
        "title": "Key findings",
        "items": [],
        "status": {
            "title": "内容暂未就绪",
            "message": "该页正在生成或已回退，可稍后重试。",
        },
    }


def test_normalize_thank_you_contact_info_to_contact():
    payload = _wrap_slides(
        [
            {
                "slideId": "slide-thanks",
                "layoutId": "thank-you",
                "contentData": {
                    "title": "谢谢",
                    "subtitle": "欢迎交流",
                    "contact_info": "hello@example.com",
                },
            }
        ]
    )

    normalized, changed, report = normalize_presentation_payload(payload)
    assert changed is True
    assert "thank-you-shape" in report["repair_types"]
    content = normalized["slides"][0]["contentData"]
    assert content["contact"] == "hello@example.com"
    assert "contact_info" not in content


def test_normalize_quote_attribution_to_author():
    payload = _wrap_slides(
        [
            {
                "slideId": "slide-quote",
                "layoutId": "quote-slide",
                "contentData": {
                    "quote": "大道至简",
                    "attribution": "某作者",
                },
            }
        ]
    )

    normalized, changed, report = normalize_presentation_payload(payload)
    assert changed is True
    assert "quote-slide-shape" in report["repair_types"]
    content = normalized["slides"][0]["contentData"]
    assert content["author"] == "某作者"
    assert "attribution" not in content


def test_normalize_table_info_from_columns_rows_dict():
    payload = _wrap_slides(
        [
            {
                "slideId": "slide-2",
                "layoutId": "table-info",
                "contentData": {
                    "title": "数据表",
                    "columns": ["名称", "数值"],
                    "rows": [
                        {"名称": "A", "数值": "10"},
                        {"名称": "B", "数值": "20"},
                    ],
                },
            }
        ]
    )

    normalized, changed, report = normalize_presentation_payload(payload)
    assert changed is True
    assert "table-info-shape" in report["repair_types"]
    content = normalized["slides"][0]["contentData"]
    assert content["headers"] == ["名称", "数值"]
    assert content["rows"] == [["A", "10"], ["B", "20"]]


def test_normalize_challenge_outcome_from_legacy_sides():
    payload = _wrap_slides(
        [
            {
                "slideId": "slide-3",
                "layoutId": "challenge-outcome",
                "contentData": {
                    "title": "问题与方案",
                    "challenge": {"title": "挑战", "items": [{"text": "挑战一"}, {"text": "挑战二"}]},
                    "outcome": {"title": "方案", "items": [{"text": "方案一"}, {"text": "方案二"}]},
                },
            }
        ]
    )

    normalized, changed, report = normalize_presentation_payload(payload)
    assert changed is True
    assert "challenge-outcome-shape" in report["repair_types"]
    content = normalized["slides"][0]["contentData"]
    assert content["items"] == [
        {"challenge": "挑战一", "outcome": "方案一"},
        {"challenge": "挑战二", "outcome": "方案二"},
    ]


def test_normalize_challenge_outcome_canonicalizes_legacy_placeholder_aliases():
    payload = _wrap_slides(
        [
            {
                "slideId": "slide-legacy-challenge",
                "layoutId": "challenge-outcome",
                "contentData": {
                    "title": "问题与方案",
                    "items": [
                        {"challenge": "Content unavailable", "outcome": "Pending"},
                    ],
                },
            }
        ]
    )

    normalized, changed, report = normalize_presentation_payload(payload)
    assert changed is True
    assert "challenge-outcome-shape" in report["repair_types"]
    content = normalized["slides"][0]["contentData"]
    assert content["items"] == [
        {"challenge": "内容生成中", "outcome": "待补充"},
    ]


def test_unrecoverable_slide_reported_without_modification():
    payload = _wrap_slides(
        [
            {
                "slideId": "slide-4",
                "layoutId": "table-info",
                "contentData": {"title": "坏数据", "rows": []},
            }
        ]
    )

    normalized, changed, report = normalize_presentation_payload(payload)
    assert changed is False
    assert normalized["slides"][0]["contentData"] == payload["slides"][0]["contentData"]
    assert report["invalid_slide_count"] == 1


def test_normalize_two_column_compare_from_string_columns():
    payload = _wrap_slides(
        [
            {
                "slideId": "slide-5",
                "layoutId": "two-column-compare",
                "contentData": {
                    "title": "比较维度",
                    "left": "**左栏**\n- 要点一\n- 要点二",
                    "right": "| 栏目 | 新增内容 |\n|---|---|\n| 方法 | 细化步骤 |",
                },
            }
        ]
    )

    normalized, changed, report = normalize_presentation_payload(payload)
    assert changed is True
    assert "two-column-compare-shape" in report["repair_types"]
    content = normalized["slides"][0]["contentData"]
    assert content["left"]["heading"] == "要点 A"
    assert isinstance(content["left"]["items"], list)
    assert len(content["left"]["items"]) >= 1
    assert content["right"]["heading"] == "要点 B"
    assert isinstance(content["right"]["items"], list)
    assert len(content["right"]["items"]) >= 1


def test_normalize_two_column_compare_canonicalizes_legacy_placeholder_aliases():
    payload = _wrap_slides(
        [
            {
                "slideId": "slide-compare-aliases",
                "layoutId": "two-column-compare",
                "contentData": {
                    "title": "Compare",
                    "items": ["Content unavailable", "Pending"],
                },
            }
        ]
    )

    normalized, changed, report = normalize_presentation_payload(payload)
    assert changed is True
    assert "two-column-compare-from-items" in report["repair_types"]
    content = normalized["slides"][0]["contentData"]
    assert content["left"]["items"] == ["内容生成中"]
    assert content["right"]["items"] == ["待补充"]


def test_normalize_outline_slide_from_items_alias_and_pad_sections():
    payload = _wrap_slides(
        [
            {
                "slideId": "slide-outline",
                "layoutId": "outline-slide",
                "contentData": {
                    "title": "Outline",
                    "items": [
                        {"title": "Background", "description": "Project context"},
                        {"label": "Method"},
                        "Findings",
                    ],
                },
            }
        ]
    )

    normalized, changed, report = normalize_presentation_payload(payload)
    assert changed is True
    assert "outline-slide-shape" in report["repair_types"]
    content = normalized["slides"][0]["contentData"]
    assert content["sections"] == [
        {"title": "Background", "description": "Project context"},
        {"title": "Method"},
        {"title": "Findings"},
        {"title": "\u7ed3\u8bba"},
    ]

def test_normalize_image_layout_backfills_source_from_url():
    payload = _wrap_slides(
        [
            {
                "slideId": "slide-image-url",
                "layoutId": "metrics-with-image",
                "contentData": {
                    "title": "Existing Asset",
                    "metrics": [{"value": "1", "label": "Asset"}],
                    "image": {
                        "prompt": "brand gallery cover",
                        "url": "https://example.com/cover.png",
                    },
                },
            }
        ]
    )

    normalized, changed, report = normalize_presentation_payload(payload)
    assert changed is True
    assert "image-ref-source" in report["repair_types"]
    image = normalized["slides"][0]["contentData"]["image"]
    assert image["source"] == "existing"


def test_normalize_image_layout_backfills_source_from_prompt_only():
    payload = _wrap_slides(
        [
            {
                "slideId": "slide-image-prompt",
                "layoutId": "image-and-description",
                "contentData": {
                    "title": "AI Image",
                    "description": "Prompt-only image",
                    "image": {
                        "prompt": "modern office with analytics dashboard",
                    },
                },
            }
        ]
    )

    normalized, changed, report = normalize_presentation_payload(payload)
    assert changed is True
    assert "image-ref-source" in report["repair_types"]
    image = normalized["slides"][0]["contentData"]["image"]
    assert image["source"] == "ai"

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

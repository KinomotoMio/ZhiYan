from app.services.pipeline.graph import _format_outline_item_for_layout_prompt
from app.services.pipeline.layout_roles import normalize_outline_items_roles
from app.services.pipeline.layout_usage import format_usage_tags, rank_layouts_by_usage


def test_normalize_outline_items_roles_preserves_content_hints():
    items = normalize_outline_items_roles(
        [
            {"slide_number": 1, "title": "封面", "suggested_slide_role": "cover"},
            {"slide_number": 2, "title": "目录", "suggested_slide_role": "agenda", "key_points": ["A", "B"]},
            {
                "slide_number": 3,
                "title": "数据趋势",
                "suggested_slide_role": "evidence",
                "content_hints": ["chart"],
                "key_points": ["同比增长 30%"],
            },
            {"slide_number": 4, "title": "方法", "suggested_slide_role": "process"},
            {"slide_number": 5, "title": "结论", "suggested_slide_role": "highlight"},
            {"slide_number": 6, "title": "致谢", "suggested_slide_role": "closing"},
        ],
        num_pages=6,
    )

    assert items[2]["content_hints"] == ["chart"]


def test_format_outline_item_for_layout_prompt_includes_content_hints_when_present():
    formatted = _format_outline_item_for_layout_prompt(
        {
            "slide_number": 3,
            "title": "数据趋势",
            "key_points": ["同比增长 30%"],
            "content_hints": ["chart", "timeline"],
            "suggested_slide_role": "evidence",
        },
        document_usage_tags=(),
        slide_usage_tags={},
        layout_entries=[],
        format_usage_tags_fn=format_usage_tags,
        rank_layouts_by_usage_fn=rank_layouts_by_usage,
    )
    assert "content_hints" in formatted
    assert "chart" in formatted
    assert "timeline" in formatted


def test_format_outline_item_for_layout_prompt_omits_content_hints_when_empty():
    formatted = _format_outline_item_for_layout_prompt(
        {
            "slide_number": 3,
            "title": "数据趋势",
            "key_points": ["同比增长 30%"],
            "content_hints": [],
            "suggested_slide_role": "evidence",
        },
        document_usage_tags=(),
        slide_usage_tags={},
        layout_entries=[],
        format_usage_tags_fn=format_usage_tags,
        rank_layouts_by_usage_fn=rank_layouts_by_usage,
    )
    assert "content_hints" not in formatted


from app.services.pipeline.graph import _resolve_layout_sub_group, _resolve_layout_variant


def test_content_hints_missing_keeps_requested_sub_group():
    item = {
        "slide_number": 2,
        "title": "实验结果概览",
        "content_brief": "展示关键指标与结论",
        "key_points": ["准确率 92%", "召回率 88%"],
    }

    assert (
        _resolve_layout_sub_group(item, role="evidence", requested_sub_group="stat-summary")
        == "stat-summary"
    )


def test_content_hints_chart_overrides_keywords_and_requested_sub_group():
    # Even if the text and the model output lean towards "table", a chart hint should win.
    item = {
        "slide_number": 2,
        "title": "实验结果对比",
        "content_brief": "用表格呈现参数矩阵，但本页需要图表解读趋势。",
        "key_points": ["表格矩阵", "参数对比", "趋势解读"],
        "content_hints": ["chart"],
    }

    sub_group = _resolve_layout_sub_group(item, role="evidence", requested_sub_group="table-matrix")
    assert sub_group == "chart-analysis"

    variant = _resolve_layout_variant(
        item,
        role="evidence",
        sub_group=sub_group,
        requested_variant_id="data-matrix",
        usage_tags=(),
    )
    assert variant == "chart-takeaways"


def test_content_hints_table_overrides_requested_sub_group():
    item = {
        "slide_number": 3,
        "title": "参数与规格汇总",
        "content_brief": "需要矩阵型表格来对齐多个维度。",
        "key_points": ["规格表", "维度对齐"],
        "content_hints": ["table"],
    }

    sub_group = _resolve_layout_sub_group(item, role="evidence", requested_sub_group="chart-analysis")
    assert sub_group == "table-matrix"

    variant = _resolve_layout_variant(
        item,
        role="evidence",
        sub_group=sub_group,
        requested_variant_id="chart-takeaways",
        usage_tags=(),
    )
    assert variant == "data-matrix"


def test_content_hints_timeline_overrides_process_step_flow():
    item = {
        "slide_number": 4,
        "title": "落地路线图",
        "content_brief": "按里程碑展示推进节奏。",
        "key_points": ["Q1 试点", "Q2 推广", "Q3 复盘"],
        "content_hints": ["timeline"],
    }

    sub_group = _resolve_layout_sub_group(item, role="process", requested_sub_group="step-flow")
    assert sub_group == "timeline-milestone"

    variant = _resolve_layout_variant(
        item,
        role="process",
        sub_group=sub_group,
        requested_variant_id="numbered-steps",
        usage_tags=(),
    )
    assert variant == "timeline-band"


def test_content_hints_image_promotes_visual_explainer_for_narrative():
    item = {
        "slide_number": 5,
        "title": "产品界面示例",
        "content_brief": "用截图说明关键交互点。",
        "key_points": ["界面截图", "关键交互", "价值说明"],
        "content_hints": ["image"],
    }

    sub_group = _resolve_layout_sub_group(item, role="narrative", requested_sub_group="icon-points")
    assert sub_group == "visual-explainer"

    variant = _resolve_layout_variant(
        item,
        role="narrative",
        sub_group=sub_group,
        requested_variant_id="icon-pillars",
        usage_tags=(),
    )
    assert variant == "media-feature"


def test_content_signal_primary_guides_sub_group_when_requested_is_invalid():
    item = {
        "slide_number": 6,
        "title": "能力概览",
        "content_brief": "本页默认没有明显关键词。",
        "key_points": ["能力A", "能力B", "能力C"],
    }

    sub_group = _resolve_layout_sub_group(
        item,
        role="narrative",
        requested_sub_group="default",
        content_signal_primary={
            "predicted_type": "image",
            "confidence": 0.81,
            "suggested_sub_group": "visual-explainer",
            "strategy": "semantic",
            "signal_source": "semantic",
        },
    )
    assert sub_group == "visual-explainer"

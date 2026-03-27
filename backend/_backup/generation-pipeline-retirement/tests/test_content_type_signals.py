from app.services.pipeline.content_type_signals import (
    CONTENT_STRATEGY_RULES,
    CONTENT_STRATEGY_SEMANTIC,
    CONTENT_TYPE_UNKNOWN,
    infer_content_signals,
    infer_rules_signal,
    infer_semantic_signal,
)


def test_infer_rules_signal_prefers_explicit_content_hints():
    item = {
        "title": "实验结果页",
        "content_brief": "这页主要讲趋势与对比。",
        "key_points": ["趋势分析", "同比变化"],
        "content_hints": ["chart"],
    }

    signal = infer_rules_signal(item, role="evidence")

    assert signal["strategy"] == CONTENT_STRATEGY_RULES
    assert signal["predicted_type"] == "chart"
    assert signal["suggested_sub_group"] == "chart-analysis"
    assert signal["confidence"] >= 0.95
    assert "content_hint:chart" in signal["evidence_tokens"]


def test_infer_semantic_signal_supports_mixed_language_inputs():
    item = {
        "title": "Product walkthrough",
        "content_brief": "用 screenshot 说明核心交互路径。",
        "key_points": ["界面截图", "关键流程", "visual showcase"],
    }

    signal = infer_semantic_signal(item, role="narrative")

    assert signal["strategy"] == CONTENT_STRATEGY_SEMANTIC
    assert signal["predicted_type"] == "image"
    assert signal["suggested_sub_group"] == "visual-explainer"
    assert signal["confidence"] > 0.0


def test_infer_content_signals_applies_threshold_fallback_for_primary():
    item = {
        "title": "季度路线图",
        "content_brief": "按里程碑展示 Q1 Q2 Q3 计划。",
        "key_points": ["Q1 试点", "Q2 推进", "Q3 验收"],
    }

    signals = infer_content_signals(
        item,
        role="process",
        primary_strategy=CONTENT_STRATEGY_SEMANTIC,
        shadow_enabled=True,
        confidence_threshold=0.95,
    )

    assert signals["primary"]["strategy"] == CONTENT_STRATEGY_SEMANTIC
    assert signals["primary"]["predicted_type"] == CONTENT_TYPE_UNKNOWN
    assert signals["primary"]["signal_source"] == "fallback"
    assert signals["primary"]["suggested_sub_group"] == ""
    assert signals["shadow"] is not None


def test_infer_content_signals_supports_shadow_toggle():
    item = {
        "title": "规格矩阵",
        "content_brief": "用 table 展示参数对照。",
        "key_points": ["规格", "参数", "对照"],
    }

    signals = infer_content_signals(
        item,
        role="evidence",
        primary_strategy=CONTENT_STRATEGY_RULES,
        shadow_enabled=False,
        confidence_threshold=0.55,
    )

    assert signals["primary"]["strategy"] == CONTENT_STRATEGY_RULES
    assert signals["shadow"] is None

from app.services.generation.loading_title import (
    DEFAULT_LOADING_TITLE,
    build_loading_title,
    compact_loading_title,
)


def test_compact_loading_title_extracts_subject_from_long_prompt():
    text = "请基于以下内容生成一个关于人工智能对未来工作影响的10页PPT，需要适合管理层汇报。"

    assert compact_loading_title(text) == "人工智能对未来工作影响"


def test_compact_loading_title_trims_prompt_boilerplate():
    text = "设计一个针对寻求融资的初创公司提案演示文稿"

    assert compact_loading_title(text) == "针对寻求融资的初创公司提案"


def test_build_loading_title_prefers_topic_and_falls_back_to_sources():
    assert build_loading_title(topic="", source_names=["年度复盘-最终版-v6.pptx"]) == "年度复盘-最终版-v6"
    assert build_loading_title(topic="", source_names=["a.pdf", "b.pdf"]) == "基于2个来源生成"
    assert build_loading_title(topic="", source_names=[]) == DEFAULT_LOADING_TITLE

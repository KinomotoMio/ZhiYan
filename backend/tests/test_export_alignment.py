import io
import zipfile

from app.models.slide import Presentation
from app.services.export.layout_rules import (
    get_bullet_with_icons_columns,
    get_outline_slide_columns,
    is_bullet_icons_only_compact,
)
from app.services.export.pdf_exporter import build_presentation_html
from app.services.export.pptx_exporter import export_pptx


def _slide_xml_text(pptx_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(pptx_bytes), "r") as archive:
        xml_parts: list[str] = []
        for name in archive.namelist():
            if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                xml_parts.append(archive.read(name).decode("utf-8", errors="ignore"))
    return "\n".join(xml_parts)


def test_build_presentation_html_renders_content_data_without_components():
    payload = {
        "presentationId": "pres-test",
        "title": "测试文稿",
        "slides": [
            {
                "slideId": "slide-1",
                "layoutType": "intro-slide",
                "layoutId": "intro-slide",
                "contentData": {
                    "title": "对齐基线",
                    "subtitle": "统一渲染链路",
                    "author": "工程团队",
                },
                "components": [],
            }
        ],
    }

    html = build_presentation_html(payload)
    assert "对齐基线" in html
    assert "统一渲染链路" in html
    assert "工程团队" in html
    assert "内容为空" not in html


def test_build_presentation_html_renders_outline_slide_cards():
    payload = {
        "presentationId": "pres-outline-html",
        "title": "测试文稿",
        "slides": [
            {
                "slideId": "slide-1",
                "layoutType": "outline-slide",
                "layoutId": "outline-slide",
                "contentData": {
                    "title": "汇报目录",
                    "subtitle": "本次汇报从背景、方法、结果到结论逐步展开。",
                    "sections": [
                        {"title": "背景", "description": "问题定义与业务场景"},
                        {"title": "方法", "description": "研究方法与分析框架"},
                        {"title": "结果", "description": "关键发现与数据表现"},
                        {"title": "结论", "description": "建议动作与后续计划"},
                    ],
                },
                "components": [],
            }
        ],
    }

    html = build_presentation_html(payload)
    assert "汇报目录" in html
    assert "display:flex;gap:56px;flex:1;margin-top:48px;" in html
    assert "问题定义与业务场景" in html
    assert "建议动作与后续计划" in html
    assert "01" in html
    assert "04" in html


def test_build_presentation_html_renders_editorial_bullet_columns():
    payload = {
        "presentationId": "pres-bullets",
        "title": "测试文稿",
        "slides": [
            {
                "slideId": "slide-1",
                "layoutType": "bullet-with-icons",
                "layoutId": "bullet-with-icons",
                "contentData": {
                    "title": "核心能力",
                    "items": [
                        {"icon": {"query": "zap"}, "title": "自动化协同", "description": "减少重复动作"},
                        {"icon": {"query": "shield"}, "title": "治理与安全", "description": "统一权限边界"},
                        {"icon": {"query": "rocket"}, "title": "交付效率", "description": ""},
                    ],
                },
                "components": [],
            }
        ],
    }

    html = build_presentation_html(payload)
    assert "核心能力" in html
    assert "01" in html
    assert "02" in html
    assert "自动化协同" in html
    assert "position:absolute;left:0;top:50%" in html
    assert "height:50%" in html
    assert 'width="20" height="20"' in html
    assert "ZA" in html
    assert "font-size:21px;font-weight:700;line-height:1.08;letter-spacing:-0.04em;color:#3b82f6" in html
    assert "background:rgba(59,130,246,0.08);border-radius:3px;padding:0.05em 0.22em 0.12em;box-decoration-break:clone" in html
    assert "减少重复动作" in html
    assert "grid-template-columns:repeat(3,1fr)" in html


def test_build_presentation_html_renders_bullet_status_panel_when_items_unavailable():
    payload = {
        "presentationId": "pres-bullets-status-html",
        "title": "测试文稿",
        "slides": [
            {
                "slideId": "slide-1",
                "layoutType": "bullet-with-icons",
                "layoutId": "bullet-with-icons",
                "contentData": {
                    "title": "关键发现",
                    "items": [],
                    "status": {
                        "title": "内容暂未就绪",
                        "message": "该页正在生成或已回退，可稍后重试。",
                    },
                },
                "components": [],
            }
        ],
    }

    html = build_presentation_html(payload)
    assert "关键发现" in html
    assert "内容暂未就绪" in html
    assert "该页正在生成或已回退，可稍后重试。" in html
    assert "grid-template-columns:repeat(0,1fr)" not in html


def test_build_presentation_html_canonicalizes_compare_and_challenge_alias_placeholders():
    payload = {
        "presentationId": "pres-fallback-alias-html",
        "title": "测试文稿",
        "slides": [
            {
                "slideId": "slide-compare",
                "layoutType": "two-column-compare",
                "layoutId": "two-column-compare",
                "contentData": {
                    "title": "Compare",
                    "items": ["Content unavailable", "Pending"],
                },
                "components": [],
            },
            {
                "slideId": "slide-challenge",
                "layoutType": "challenge-outcome",
                "layoutId": "challenge-outcome",
                "contentData": {
                    "title": "问题与方案",
                    "items": [
                        {"challenge": "Content unavailable", "outcome": "Pending"},
                    ],
                },
                "components": [],
            },
        ],
    }

    html = build_presentation_html(payload)
    assert "内容生成中" in html
    assert "待补充" in html
    assert "Content unavailable" not in html
    assert "Fallback generated" not in html


def test_build_presentation_html_preserves_legitimate_english_pending_content():
    payload = {
        "presentationId": "pres-pending-html",
        "title": "测试文稿",
        "slides": [
            {
                "slideId": "slide-compare",
                "layoutType": "two-column-compare",
                "layoutId": "two-column-compare",
                "contentData": {
                    "title": "Workflow",
                    "items": ["Security review", "Pending"],
                },
                "components": [],
            },
            {
                "slideId": "slide-bullets",
                "layoutType": "bullet-with-icons",
                "layoutId": "bullet-with-icons",
                "contentData": {
                    "title": "Status",
                    "items": [
                        {"icon": {"query": "clock-3"}, "title": "Pending", "description": "Awaiting approval"},
                        {"icon": {"query": "shield"}, "title": "Approved", "description": "Security cleared"},
                        {"icon": {"query": "rocket"}, "title": "Ready", "description": "Queued for launch"},
                    ],
                },
                "components": [],
            },
        ],
    }

    html = build_presentation_html(payload)
    assert "Security review" in html
    assert "Pending" in html
    assert "Awaiting approval" in html
    assert "待补充" not in html


def test_build_presentation_html_renders_bullet_icons_only_icon_tokens():
    payload = {
        "presentationId": "pres-icons-html",
        "title": "测试文稿",
        "slides": [
            {
                "slideId": "slide-1",
                "layoutType": "bullet-icons-only",
                "layoutId": "bullet-icons-only",
                "contentData": {
                    "title": "能力矩阵",
                    "items": [
                        {"icon": {"query": "database"}, "label": "数据中台"},
                        {"icon": {"query": "shield"}, "label": "权限治理"},
                    ],
                },
                "components": [],
            }
        ],
    }

    html = build_presentation_html(payload)
    assert "能力矩阵" in html
    assert 'width="40" height="40"' in html
    assert "DA" in html
    assert "SH" in html
    assert "数据中台" in html


def test_export_pptx_accepts_alias_fields():
    presentation = Presentation.model_validate(
        {
            "presentationId": "pres-alias",
            "title": "导出别名兼容",
            "slides": [
                {
                    "slideId": "slide-1",
                    "layoutType": "intro-slide",
                    "layoutId": "intro-slide",
                    "contentData": {
                        "title": "封面标题",
                        "presenter": "别名作者",
                        "date": "2026",
                    },
                    "components": [],
                },
                {
                    "slideId": "slide-2",
                    "layoutType": "thank-you",
                    "layoutId": "thank-you",
                    "contentData": {
                        "title": "谢谢",
                        "contact_info": "hello@example.com",
                    },
                    "components": [],
                },
                {
                    "slideId": "slide-3",
                    "layoutType": "challenge-outcome",
                    "layoutId": "challenge-outcome",
                    "contentData": {
                        "title": "问题与方案",
                        "items": [
                            {"challenge": "问题A", "outcome": "方案A"},
                            {"challenge": "问题B", "outcome": "方案B"},
                        ],
                    },
                    "components": [],
                },
            ],
        }
    )

    pptx_bytes = export_pptx(presentation)
    xml_text = _slide_xml_text(pptx_bytes)

    assert "封面标题" in xml_text
    assert "别名作者" in xml_text
    assert "hello@example.com" in xml_text
    assert "问题A" in xml_text
    assert "方案A" in xml_text


def test_export_pptx_renders_bullet_status_panel_when_items_unavailable():
    presentation = Presentation.model_validate(
        {
            "presentationId": "pres-bullets-status-pptx",
            "title": "状态导出",
            "slides": [
                {
                    "slideId": "slide-bullets-status",
                    "layoutType": "bullet-with-icons",
                    "layoutId": "bullet-with-icons",
                    "contentData": {
                        "title": "关键发现",
                        "items": [],
                        "status": {
                            "title": "内容暂未就绪",
                            "message": "该页正在生成或已回退，可稍后重试。",
                        },
                    },
                    "components": [],
                }
            ],
        }
    )

    pptx_bytes = export_pptx(presentation)
    xml_text = _slide_xml_text(pptx_bytes)

    assert "关键发现" in xml_text
    assert "内容暂未就绪" in xml_text
    assert "该页正在生成或已回退，可稍后重试。" in xml_text


def test_build_presentation_html_renders_outline_slide_structure():
    payload = {
        "presentationId": "pres-outline",
        "title": "Outline Test",
        "slides": [
            {
                "slideId": "slide-outline",
                "layoutType": "outline-slide",
                "layoutId": "outline-slide",
                "contentData": {
                    "title": "Project Outline",
                    "subtitle": "Used to verify outline export structure.",
                    "sections": [
                        {"title": "Background", "description": "Project context and motivation"},
                        {"title": "Method", "description": "Research and execution approach"},
                        {"title": "Findings", "description": "Core observations and metrics"},
                        {"title": "Results", "description": "Outcome and impact"},
                        {"title": "Next Steps", "description": "Follow-up actions"},
                    ],
                },
                "components": [],
            }
        ],
    }

    html = build_presentation_html(payload)
    assert "Project Outline" in html
    assert "Used to verify outline export structure." in html
    assert "Background" in html
    assert "Next Steps" in html
    assert "01" in html
    assert "05" in html


def test_export_pptx_renders_outline_slide_text():
    presentation = Presentation.model_validate(
        {
            "presentationId": "pres-outline-pptx",
            "title": "Outline Export",
            "slides": [
                {
                    "slideId": "slide-outline",
                    "layoutType": "outline-slide",
                    "layoutId": "outline-slide",
                    "contentData": {
                        "title": "Project Outline",
                        "subtitle": "Used to verify PPTX export.",
                        "sections": [
                            {"title": "Background", "description": "Project context and motivation"},
                            {"title": "Method", "description": "Research and execution approach"},
                            {"title": "Findings", "description": "Core observations and metrics"},
                            {"title": "Results", "description": "Outcome and impact"},
                            {"title": "Next Steps", "description": "Follow-up actions"},
                        ],
                    },
                    "components": [],
                }
            ],
        }
    )

    pptx_bytes = export_pptx(presentation)
    xml_text = _slide_xml_text(pptx_bytes)

    assert "Project Outline" in xml_text
    assert "Used to verify PPTX export." in xml_text
    assert "Background" in xml_text
    assert "Next Steps" in xml_text


def test_export_pptx_renders_bullet_with_icons_as_columns():
    presentation = Presentation.model_validate(
        {
            "presentationId": "pres-bullets-pptx",
            "title": "导出栏目布局",
            "slides": [
                {
                    "slideId": "slide-1",
                    "layoutType": "bullet-with-icons",
                    "layoutId": "bullet-with-icons",
                    "contentData": {
                        "title": "核心能力",
                        "items": [
                            {"icon": {"query": "zap"}, "title": "自动化协同", "description": "减少重复动作"},
                            {"icon": {"query": "shield"}, "title": "治理与安全", "description": "统一权限边界"},
                            {"icon": {"query": "rocket"}, "title": "交付效率", "description": ""},
                        ],
                    },
                    "components": [],
                }
            ],
        }
    )

    pptx_bytes = export_pptx(presentation)
    xml_text = _slide_xml_text(pptx_bytes)

    assert "核心能力" in xml_text
    assert "01" in xml_text
    assert "02" in xml_text
    assert "03" in xml_text
    assert "自动化协同" in xml_text
    assert "减少重复动作" in xml_text
    assert "• 自动化协同" not in xml_text
    assert "ZA" in xml_text
    assert "SH" in xml_text
    assert "3B82F6" in xml_text
    assert "EFF5FE" in xml_text


def test_export_layout_rules_match_preview_thresholds():
    assert get_outline_slide_columns(4) == 2
    assert get_outline_slide_columns(5) == 3
    assert get_bullet_with_icons_columns(1) == 3
    assert get_bullet_with_icons_columns(3) == 3
    assert get_bullet_with_icons_columns(4) == 4
    assert is_bullet_icons_only_compact(6) is False
    assert is_bullet_icons_only_compact(7) is True


def test_export_pptx_renders_bullet_icons_only_icon_tokens():
    presentation = Presentation.model_validate(
        {
            "presentationId": "pres-icons-pptx",
            "title": "能力矩阵导出",
            "slides": [
                {
                    "slideId": "slide-1",
                    "layoutType": "bullet-icons-only",
                    "layoutId": "bullet-icons-only",
                    "contentData": {
                        "title": "能力矩阵",
                        "items": [
                            {"icon": {"query": "database"}, "label": "数据中台"},
                            {"icon": {"query": "shield"}, "label": "权限治理"},
                        ],
                    },
                    "components": [],
                }
            ],
        }
    )

    pptx_bytes = export_pptx(presentation)
    xml_text = _slide_xml_text(pptx_bytes)

    assert "能力矩阵" in xml_text
    assert "DA" in xml_text
    assert "SH" in xml_text
    assert "数据中台" in xml_text


def test_export_pptx_renders_outline_slide_cards():
    presentation = Presentation.model_validate(
        {
            "presentationId": "pres-outline-pptx",
            "title": "目录导航导出",
            "slides": [
                {
                    "slideId": "slide-1",
                    "layoutType": "outline-slide",
                    "layoutId": "outline-slide",
                    "contentData": {
                        "title": "汇报目录",
                        "subtitle": "本次汇报从背景、方法、结果到结论逐步展开。",
                        "sections": [
                            {"title": "背景", "description": "问题定义与业务场景"},
                            {"title": "方法", "description": "研究方法与分析框架"},
                            {"title": "结果", "description": "关键发现与数据表现"},
                            {"title": "结论", "description": "建议动作与后续计划"},
                        ],
                    },
                    "components": [],
                }
            ],
        }
    )

    pptx_bytes = export_pptx(presentation)
    xml_text = _slide_xml_text(pptx_bytes)

    assert "汇报目录" in xml_text
    assert "问题定义与业务场景" in xml_text
    assert "研究方法与分析框架" in xml_text
    assert "背景" in xml_text
    assert "结论" in xml_text
    assert "01" in xml_text
    assert "04" in xml_text

def test_build_presentation_html_renders_metrics_slide_executive_summary_and_legacy_fallback():
    payload = {
        "presentationId": "pres-metrics-html",
        "title": "Metrics Test",
        "slides": [
            {
                "slideId": "slide-1",
                "layoutType": "metrics-slide",
                "layoutId": "metrics-slide",
                "contentData": {
                    "title": "Quarterly Snapshot",
                    "conclusion": "Enterprise adoption is no longer the bottleneck.",
                    "conclusionBrief": "Coverage expanded across the org, so review latency is the next constraint.",
                    "metrics": [
                        {"value": "92%", "label": "Adoption", "description": "active team usage"},
                        {"value": "14d", "label": "Lead Time", "description": "from brief to deck"},
                    ],
                },
                "components": [],
            },
            {
                "slideId": "slide-2",
                "layoutType": "metrics-slide",
                "layoutId": "metrics-slide",
                "contentData": {
                    "title": "Legacy Snapshot",
                    "metrics": [
                        {"value": "3.6x", "label": "Reuse", "description": "template leverage"},
                        {"value": "11", "label": "Teams", "description": "pilot rollout"},
                    ],
                },
                "components": [],
            },
        ],
    }

    html = build_presentation_html(payload)
    assert "Enterprise adoption is no longer the bottleneck." in html
    assert "Coverage expanded across the org, so review latency is the next constraint." in html
    assert "min-height:168px" in html
    assert "Legacy Snapshot" in html
    assert "template leverage" in html


def test_export_pptx_renders_metrics_slide_executive_summary_and_legacy_fallback():
    presentation = Presentation.model_validate(
        {
            "presentationId": "pres-metrics-pptx",
            "title": "Metrics Export",
            "slides": [
                {
                    "slideId": "slide-1",
                    "layoutType": "metrics-slide",
                    "layoutId": "metrics-slide",
                    "contentData": {
                        "title": "Quarterly Snapshot",
                        "conclusion": "Enterprise adoption is no longer the bottleneck.",
                        "conclusionBrief": "Coverage expanded across the org, so review latency is the next constraint.",
                        "metrics": [
                            {"value": "92%", "label": "Adoption", "description": "active team usage"},
                            {"value": "14d", "label": "Lead Time", "description": "from brief to deck"},
                        ],
                    },
                    "components": [],
                },
                {
                    "slideId": "slide-2",
                    "layoutType": "metrics-slide",
                    "layoutId": "metrics-slide",
                    "contentData": {
                        "title": "Legacy Snapshot",
                        "metrics": [
                            {"value": "3.6x", "label": "Reuse", "description": "template leverage"},
                            {"value": "11", "label": "Teams", "description": "pilot rollout"},
                        ],
                    },
                    "components": [],
                },
            ],
        }
    )

    pptx_bytes = export_pptx(presentation)
    xml_text = _slide_xml_text(pptx_bytes)

    assert "Quarterly Snapshot" in xml_text
    assert "Enterprise adoption is no longer the bottleneck." in xml_text
    assert "Coverage expanded across the org, so review latency is the next constraint." in xml_text
    assert "Legacy Snapshot" in xml_text
    assert "template leverage" in xml_text

import io
import zipfile

from app.models.slide import Presentation
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
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in html
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

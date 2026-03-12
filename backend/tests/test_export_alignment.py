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
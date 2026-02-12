"""PPTX 导出 — 从 Slide JSON 生成 .pptx 文件

使用 python-pptx 将组件化的 Slide JSON 重建为 PowerPoint 文件。
坐标从百分比（0-100）转换为 EMU 单位。
"""

import io

from pptx import Presentation as PptxPresentation
from pptx.util import Inches, Pt, Emu
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor

from app.models.slide import Presentation, Slide, Component

# 16:9 宽屏尺寸
SLIDE_WIDTH = Inches(13.333)
SLIDE_HEIGHT = Inches(7.5)


def _pct_to_emu(pct: float, total: int) -> int:
    """百分比转 EMU"""
    return int(total * pct / 100)


def _parse_color(color_str: str | None) -> RGBColor | None:
    """解析 CSS 颜色字符串为 RGBColor"""
    if not color_str:
        return None
    color_str = color_str.strip().lstrip("#")
    if len(color_str) == 6:
        try:
            return RGBColor(
                int(color_str[0:2], 16),
                int(color_str[2:4], 16),
                int(color_str[4:6], 16),
            )
        except ValueError:
            return None
    return None


def _get_alignment(text_align: str | None) -> int | None:
    """文本对齐映射"""
    mapping = {
        "left": PP_ALIGN.LEFT,
        "center": PP_ALIGN.CENTER,
        "right": PP_ALIGN.RIGHT,
    }
    return mapping.get(text_align)


def _add_text_component(slide_obj, comp: Component) -> None:
    """添加文本组件到幻灯片"""
    pos = comp.position
    left = _pct_to_emu(pos.x, SLIDE_WIDTH)
    top = _pct_to_emu(pos.y, SLIDE_HEIGHT)
    width = _pct_to_emu(pos.width, SLIDE_WIDTH)
    height = _pct_to_emu(pos.height, SLIDE_HEIGHT)

    txBox = slide_obj.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True

    content = comp.content or ""
    style = comp.style

    # 处理列表格式
    lines = content.split("\n")
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        # 去除 bullet 前缀
        display_text = line.lstrip("•-* ").strip()

        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()

        p.text = display_text

        # 样式
        if style:
            font_size = style.font_size
            if font_size:
                p.font.size = Pt(font_size)
            if style.font_weight == "bold":
                p.font.bold = True
            color = _parse_color(style.color)
            if color:
                p.font.color.rgb = color
            alignment = _get_alignment(
                style.text_align.value if style.text_align else None
            )
            if alignment is not None:
                p.alignment = alignment


def _add_placeholder_component(slide_obj, comp: Component) -> None:
    """添加占位组件（图片/图表）"""
    pos = comp.position
    left = _pct_to_emu(pos.x, SLIDE_WIDTH)
    top = _pct_to_emu(pos.y, SLIDE_HEIGHT)
    width = _pct_to_emu(pos.width, SLIDE_WIDTH)
    height = _pct_to_emu(pos.height, SLIDE_HEIGHT)

    # 用文本框占位，显示描述
    txBox = slide_obj.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = f"[{comp.type.value}: {comp.content or '占位'}]"
    p.font.size = Pt(12)
    p.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
    p.alignment = PP_ALIGN.CENTER


def export_pptx(presentation: Presentation) -> bytes:
    """将 Presentation JSON 导出为 PPTX 字节"""
    prs = PptxPresentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT

    # 使用空白布局
    blank_layout = prs.slide_layouts[6]  # 通常是空白布局

    for slide_data in presentation.slides:
        slide_obj = prs.slides.add_slide(blank_layout)

        for comp in slide_data.components:
            if comp.type.value == "text":
                _add_text_component(slide_obj, comp)
            else:
                _add_placeholder_component(slide_obj, comp)

        # 演讲者注释
        if slide_data.speaker_notes:
            notes_slide = slide_obj.notes_slide
            notes_slide.notes_text_frame.text = slide_data.speaker_notes

    # 导出为字节
    buffer = io.BytesIO()
    prs.save(buffer)
    buffer.seek(0)
    return buffer.read()

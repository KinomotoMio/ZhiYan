"""PPTX 导出 — 从 Slide JSON 生成 .pptx 文件

使用 python-pptx 将组件化的 Slide JSON 重建为 PowerPoint 文件。
坐标从百分比（0-100）转换为 EMU 单位。
"""

import io
import re

from pptx import Presentation as PptxPresentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn

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
    mapping = {
        "left": PP_ALIGN.LEFT,
        "center": PP_ALIGN.CENTER,
        "right": PP_ALIGN.RIGHT,
    }
    return mapping.get(text_align)


def _is_bullet_line(line: str) -> tuple[bool, int, str]:
    """检测列表行。返回 (is_bullet, level, clean_text)"""
    # 嵌套列表（以空格/tab 开头）
    nested = re.match(r'^(\s{2,}|\t+)([•\-*]|\d+[.)])\s+(.*)', line)
    if nested:
        return True, 1, nested.group(3)
    # 无序列表
    unordered = re.match(r'^[•\-*]\s+(.*)', line)
    if unordered:
        return True, 0, unordered.group(1)
    # 有序列表
    ordered = re.match(r'^\d+[.)]\s+(.*)', line)
    if ordered:
        return True, 0, ordered.group(1)
    return False, 0, line


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
    lines = content.split("\n")

    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped:
            continue

        is_bullet, level, clean_text = _is_bullet_line(line_stripped)

        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()

        p.text = clean_text

        # 原生 bullet formatting
        if is_bullet:
            p.level = level
            pPr = p._pPr
            if pPr is None:
                pPr = p._p.get_or_add_pPr()
            buChar = pPr.makeelement(qn("a:buChar"), {"char": "•"})
            # 移除旧 bullet
            for old in pPr.findall(qn("a:buChar")):
                pPr.remove(old)
            for old in pPr.findall(qn("a:buNone")):
                pPr.remove(old)
            pPr.append(buChar)

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


def _set_slide_background(slide_obj, bg_color: str | None) -> None:
    """设置幻灯片背景色"""
    color = _parse_color(bg_color)
    if not color:
        return
    background = slide_obj.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _add_placeholder_component(slide_obj, comp: Component) -> None:
    """添加占位组件（图片/图表）"""
    pos = comp.position
    left = _pct_to_emu(pos.x, SLIDE_WIDTH)
    top = _pct_to_emu(pos.y, SLIDE_HEIGHT)
    width = _pct_to_emu(pos.width, SLIDE_WIDTH)
    height = _pct_to_emu(pos.height, SLIDE_HEIGHT)

    txBox = slide_obj.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = f"[{comp.type.value}: {comp.content or '占位'}]"
    p.font.size = Pt(12)
    p.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
    p.alignment = PP_ALIGN.CENTER

    # 添加浅色背景框
    shape = txBox
    fill = shape.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(0xF3, 0xF4, 0xF6)


def export_pptx(presentation: Presentation) -> bytes:
    """将 Presentation JSON 导出为 PPTX 字节"""
    prs = PptxPresentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT

    blank_layout = prs.slide_layouts[6]

    for slide_data in presentation.slides:
        slide_obj = prs.slides.add_slide(blank_layout)

        # 背景色（从 theme 或 layout 中决定）
        if presentation.theme and presentation.theme.background_color:
            _set_slide_background(slide_obj, presentation.theme.background_color)

        for comp in slide_data.components:
            if comp.type.value == "text":
                _add_text_component(slide_obj, comp)
            else:
                _add_placeholder_component(slide_obj, comp)

        # 演讲者注释
        if slide_data.speaker_notes:
            notes_slide = slide_obj.notes_slide
            notes_slide.notes_text_frame.text = slide_data.speaker_notes

    buffer = io.BytesIO()
    prs.save(buffer)
    buffer.seek(0)
    return buffer.read()

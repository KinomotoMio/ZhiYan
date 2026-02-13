"""PPTX 导出 — 从 Slide JSON 生成 .pptx 文件

使用 python-pptx 将 Slide JSON 重建为 PowerPoint 文件。
支持两种格式：
- 新版 layoutId + contentData：按结构化数据渲染
- 旧版 components：按组件坐标渲染（向后兼容）
"""

import io
import re

from pptx import Presentation as PptxPresentation
from pptx.util import Inches, Pt, Emu
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
    nested = re.match(r'^(\s{2,}|\t+)([•\-*]|\d+[.)])\s+(.*)', line)
    if nested:
        return True, 1, nested.group(3)
    unordered = re.match(r'^[•\-*]\s+(.*)', line)
    if unordered:
        return True, 0, unordered.group(1)
    ordered = re.match(r'^\d+[.)]\s+(.*)', line)
    if ordered:
        return True, 0, ordered.group(1)
    return False, 0, line


def _add_textbox(slide_obj, left: int, top: int, width: int, height: int,
                 text: str, font_size: float = 18, bold: bool = False,
                 color: RGBColor | None = None, alignment: int | None = None):
    """添加文本框的便捷函数"""
    txBox = slide_obj.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    if font_size:
        p.font.size = Pt(font_size)
    if bold:
        p.font.bold = True
    if color:
        p.font.color.rgb = color
    if alignment is not None:
        p.alignment = alignment
    return txBox


def _add_text_component(slide_obj, comp: Component) -> None:
    """添加文本组件到幻灯片（旧版）"""
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

        if is_bullet:
            p.level = level
            pPr = p._pPr
            if pPr is None:
                pPr = p._p.get_or_add_pPr()
            buChar = pPr.makeelement(qn("a:buChar"), {"char": "•"})
            for old in pPr.findall(qn("a:buChar")):
                pPr.remove(old)
            for old in pPr.findall(qn("a:buNone")):
                pPr.remove(old)
            pPr.append(buChar)

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
    """添加占位组件（图片/图表）— 旧版"""
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

    shape = txBox
    fill = shape.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(0xF3, 0xF4, 0xF6)


# ---------- 新版 contentData 渲染 ----------

PRIMARY_COLOR = RGBColor(0x3B, 0x82, 0xF6)
GRAY_600 = RGBColor(0x4B, 0x55, 0x63)
GRAY_400 = RGBColor(0x9C, 0xA3, 0xAF)


def _render_content_data(slide_obj, layout_id: str, data: dict, theme_color: RGBColor | None = None) -> None:
    """根据 layout_id 和 contentData 渲染幻灯片内容"""
    color = theme_color or PRIMARY_COLOR
    d = data

    if layout_id == "intro-slide":
        _add_textbox(slide_obj,
                     Inches(1.5), Inches(2.0), Inches(10), Inches(1.5),
                     d.get("title", ""), font_size=48, bold=True, color=color,
                     alignment=PP_ALIGN.CENTER)
        if d.get("subtitle"):
            _add_textbox(slide_obj,
                         Inches(2), Inches(3.8), Inches(9), Inches(0.8),
                         d["subtitle"], font_size=24, color=GRAY_600,
                         alignment=PP_ALIGN.CENTER)
        info_parts = []
        if d.get("presenter"):
            info_parts.append(d["presenter"])
        if d.get("date"):
            info_parts.append(d["date"])
        if info_parts:
            _add_textbox(slide_obj,
                         Inches(2), Inches(5.0), Inches(9), Inches(0.6),
                         " | ".join(info_parts), font_size=16, color=GRAY_400,
                         alignment=PP_ALIGN.CENTER)

    elif layout_id == "section-header":
        if d.get("section_number"):
            _add_textbox(slide_obj,
                         Inches(2), Inches(2.2), Inches(9), Inches(0.6),
                         str(d["section_number"]), font_size=18, color=color,
                         alignment=PP_ALIGN.CENTER)
        _add_textbox(slide_obj,
                     Inches(1.5), Inches(2.8), Inches(10), Inches(1.2),
                     d.get("title", ""), font_size=44, bold=True,
                     alignment=PP_ALIGN.CENTER)
        if d.get("subtitle"):
            _add_textbox(slide_obj,
                         Inches(2), Inches(4.2), Inches(9), Inches(0.8),
                         d["subtitle"], font_size=22, color=GRAY_600,
                         alignment=PP_ALIGN.CENTER)

    elif layout_id in ("bullet-with-icons", "bullet-icons-only"):
        _add_textbox(slide_obj,
                     Inches(0.8), Inches(0.5), Inches(11), Inches(1.0),
                     d.get("title", ""), font_size=36, bold=True)
        items = d.get("items") or d.get("features") or []
        y = Inches(1.8)
        for item in items[:6]:
            text = item.get("text", "") if isinstance(item, dict) else str(item)
            desc = item.get("description", "") if isinstance(item, dict) else ""
            _add_textbox(slide_obj,
                         Inches(1.2), y, Inches(10), Inches(0.5),
                         f"• {text}", font_size=22, bold=True)
            if desc:
                _add_textbox(slide_obj,
                             Inches(1.5), y + Inches(0.5), Inches(10), Inches(0.4),
                             desc, font_size=16, color=GRAY_600)
                y += Inches(1.1)
            else:
                y += Inches(0.7)

    elif layout_id == "numbered-bullets":
        _add_textbox(slide_obj,
                     Inches(0.8), Inches(0.5), Inches(11), Inches(1.0),
                     d.get("title", ""), font_size=36, bold=True)
        items = d.get("items") or d.get("steps") or []
        y = Inches(1.8)
        for i, item in enumerate(items[:6]):
            text = item.get("text", "") if isinstance(item, dict) else str(item)
            _add_textbox(slide_obj,
                         Inches(0.8), y, Inches(0.6), Inches(0.5),
                         str(i + 1), font_size=24, bold=True, color=color)
            _add_textbox(slide_obj,
                         Inches(1.6), y, Inches(10), Inches(0.5),
                         text, font_size=22)
            desc = item.get("description", "") if isinstance(item, dict) else ""
            if desc:
                _add_textbox(slide_obj,
                             Inches(1.6), y + Inches(0.5), Inches(10), Inches(0.4),
                             desc, font_size=16, color=GRAY_600)
                y += Inches(1.1)
            else:
                y += Inches(0.7)

    elif layout_id == "metrics-slide":
        _add_textbox(slide_obj,
                     Inches(0.8), Inches(0.5), Inches(11), Inches(1.0),
                     d.get("title", ""), font_size=36, bold=True)
        metrics = d.get("metrics") or []
        count = min(len(metrics), 4)
        if count > 0:
            card_width = 10.0 / count
            for i, m in enumerate(metrics[:4]):
                x = Inches(1.2 + i * card_width)
                _add_textbox(slide_obj,
                             x, Inches(2.8), Inches(card_width - 0.4), Inches(0.9),
                             m.get("value", ""), font_size=44, bold=True, color=color,
                             alignment=PP_ALIGN.CENTER)
                _add_textbox(slide_obj,
                             x, Inches(3.8), Inches(card_width - 0.4), Inches(0.5),
                             m.get("label", ""), font_size=18, bold=True,
                             alignment=PP_ALIGN.CENTER)
                if m.get("description"):
                    _add_textbox(slide_obj,
                                 x, Inches(4.4), Inches(card_width - 0.4), Inches(0.5),
                                 m["description"], font_size=14, color=GRAY_600,
                                 alignment=PP_ALIGN.CENTER)

    elif layout_id == "metrics-with-image":
        _add_textbox(slide_obj,
                     Inches(0.8), Inches(0.8), Inches(5.5), Inches(0.9),
                     d.get("title", ""), font_size=32, bold=True)
        metrics = d.get("metrics") or []
        y = Inches(2.0)
        for m in metrics[:4]:
            _add_textbox(slide_obj,
                         Inches(0.8), y, Inches(2), Inches(0.6),
                         m.get("value", ""), font_size=32, bold=True, color=color)
            _add_textbox(slide_obj,
                         Inches(3.0), y + Inches(0.05), Inches(3.5), Inches(0.5),
                         m.get("label", ""), font_size=16, color=GRAY_600)
            y += Inches(0.8)
        # 右侧图片占位
        _add_textbox(slide_obj,
                     Inches(7.0), Inches(0.8), Inches(5.5), Inches(5.9),
                     "[图片占位]", font_size=14, color=GRAY_400,
                     alignment=PP_ALIGN.CENTER)

    elif layout_id == "chart-with-bullets":
        _add_textbox(slide_obj,
                     Inches(0.8), Inches(0.5), Inches(11), Inches(1.0),
                     d.get("title", ""), font_size=36, bold=True)
        _add_textbox(slide_obj,
                     Inches(0.8), Inches(1.8), Inches(5.5), Inches(5.0),
                     "[图表占位]", font_size=14, color=GRAY_400,
                     alignment=PP_ALIGN.CENTER)
        bullets = d.get("bullets") or []
        y = Inches(2.0)
        for b in bullets[:5]:
            text = b.get("text", "") if isinstance(b, dict) else str(b)
            _add_textbox(slide_obj,
                         Inches(7.0), y, Inches(5.5), Inches(0.5),
                         f"• {text}", font_size=18)
            y += Inches(0.6)

    elif layout_id == "table-info":
        _add_textbox(slide_obj,
                     Inches(0.8), Inches(0.5), Inches(11), Inches(1.0),
                     d.get("title", ""), font_size=36, bold=True)
        columns = d.get("columns") or []
        rows = d.get("rows") or []
        if columns:
            n_cols = len(columns)
            n_rows = min(len(rows), 8) + 1
            col_w = min(10.0 / n_cols, 3.0)
            table_shape = slide_obj.shapes.add_table(
                n_rows, n_cols,
                Inches(0.8), Inches(1.8),
                Inches(col_w * n_cols), Inches(0.5 * n_rows),
            )
            table = table_shape.table
            for ci, col_name in enumerate(columns):
                cell = table.cell(0, ci)
                cell.text = str(col_name)
                for p in cell.text_frame.paragraphs:
                    p.font.bold = True
                    p.font.size = Pt(14)
            for ri, row in enumerate(rows[:8]):
                for ci, col_name in enumerate(columns):
                    cell = table.cell(ri + 1, ci)
                    cell.text = str(row.get(col_name, "")) if isinstance(row, dict) else ""
                    for p in cell.text_frame.paragraphs:
                        p.font.size = Pt(13)

    elif layout_id == "two-column-compare":
        _add_textbox(slide_obj,
                     Inches(0.8), Inches(0.5), Inches(11), Inches(1.0),
                     d.get("title", ""), font_size=36, bold=True)
        for side, x_offset in [("left", 0.8), ("right", 7.0)]:
            col = d.get(side) or {}
            col_title = col.get("title", "")
            _add_textbox(slide_obj,
                         Inches(x_offset), Inches(1.8), Inches(5.0), Inches(0.6),
                         col_title, font_size=24, bold=True, color=color)
            items = col.get("items") or []
            y = Inches(2.6)
            for item in items[:5]:
                text = item.get("text", "") if isinstance(item, dict) else str(item)
                _add_textbox(slide_obj,
                             Inches(x_offset), y, Inches(5.0), Inches(0.5),
                             f"• {text}", font_size=18)
                y += Inches(0.6)

    elif layout_id == "image-and-description":
        _add_textbox(slide_obj,
                     Inches(0.5), Inches(0.5), Inches(6.0), Inches(6.5),
                     "[图片占位]", font_size=14, color=GRAY_400,
                     alignment=PP_ALIGN.CENTER)
        _add_textbox(slide_obj,
                     Inches(7.0), Inches(1.5), Inches(5.5), Inches(0.9),
                     d.get("title", ""), font_size=32, bold=True)
        if d.get("description"):
            _add_textbox(slide_obj,
                         Inches(7.0), Inches(2.8), Inches(5.5), Inches(3.5),
                         d["description"], font_size=18, color=GRAY_600)

    elif layout_id == "timeline":
        _add_textbox(slide_obj,
                     Inches(0.8), Inches(0.5), Inches(11), Inches(1.0),
                     d.get("title", ""), font_size=36, bold=True)
        events = d.get("events") or d.get("items") or []
        count = min(len(events), 5)
        if count > 0:
            step = 10.0 / count
            for i, evt in enumerate(events[:5]):
                x = Inches(1.0 + i * step)
                _add_textbox(slide_obj,
                             x, Inches(2.5), Inches(step - 0.3), Inches(0.4),
                             evt.get("date", ""), font_size=14, color=color, bold=True,
                             alignment=PP_ALIGN.CENTER)
                _add_textbox(slide_obj,
                             x, Inches(3.0), Inches(step - 0.3), Inches(0.5),
                             evt.get("title", ""), font_size=18, bold=True,
                             alignment=PP_ALIGN.CENTER)
                if evt.get("description"):
                    _add_textbox(slide_obj,
                                 x, Inches(3.6), Inches(step - 0.3), Inches(0.6),
                                 evt["description"], font_size=13, color=GRAY_600,
                                 alignment=PP_ALIGN.CENTER)

    elif layout_id == "quote-slide":
        _add_textbox(slide_obj,
                     Inches(1.5), Inches(2.0), Inches(10), Inches(2.5),
                     f'"{d.get("quote", "")}"', font_size=32, bold=False,
                     alignment=PP_ALIGN.CENTER)
        if d.get("attribution"):
            _add_textbox(slide_obj,
                         Inches(2), Inches(5.0), Inches(9), Inches(0.6),
                         f'— {d["attribution"]}', font_size=18, color=GRAY_400,
                         alignment=PP_ALIGN.CENTER)

    elif layout_id == "challenge-outcome":
        _add_textbox(slide_obj,
                     Inches(0.8), Inches(0.5), Inches(11), Inches(1.0),
                     d.get("title", ""), font_size=36, bold=True)
        for side_key, x_offset, side_color in [
            ("challenge", 0.8, RGBColor(0xDC, 0x26, 0x26)),
            ("outcome", 7.0, RGBColor(0x16, 0xA3, 0x4A)),
        ]:
            side = d.get(side_key) or {}
            _add_textbox(slide_obj,
                         Inches(x_offset), Inches(1.8), Inches(5.0), Inches(0.6),
                         side.get("title", side_key.capitalize()), font_size=24, bold=True, color=side_color)
            items = side.get("items") or []
            y = Inches(2.6)
            for item in items[:5]:
                text = item.get("text", "") if isinstance(item, dict) else str(item)
                _add_textbox(slide_obj,
                             Inches(x_offset), y, Inches(5.0), Inches(0.5),
                             f"• {text}", font_size=18)
                y += Inches(0.6)

    elif layout_id == "thank-you":
        _add_textbox(slide_obj,
                     Inches(1.5), Inches(2.2), Inches(10), Inches(1.5),
                     d.get("title", "谢谢"), font_size=48, bold=True, color=color,
                     alignment=PP_ALIGN.CENTER)
        if d.get("subtitle"):
            _add_textbox(slide_obj,
                         Inches(2), Inches(4.0), Inches(9), Inches(0.8),
                         d["subtitle"], font_size=22, color=GRAY_600,
                         alignment=PP_ALIGN.CENTER)
        if d.get("contact_info"):
            _add_textbox(slide_obj,
                         Inches(2), Inches(5.2), Inches(9), Inches(0.6),
                         d["contact_info"], font_size=16, color=GRAY_400,
                         alignment=PP_ALIGN.CENTER)

    else:
        _add_textbox(slide_obj,
                     Inches(0.8), Inches(0.5), Inches(11), Inches(1.0),
                     d.get("title", f"[{layout_id}]"), font_size=36, bold=True)


def export_pptx(presentation: Presentation) -> bytes:
    """将 Presentation JSON 导出为 PPTX 字节"""
    prs = PptxPresentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT

    blank_layout = prs.slide_layouts[6]
    theme_color = _parse_color(
        presentation.theme.primary_color if presentation.theme else None
    )

    for slide_data in presentation.slides:
        slide_obj = prs.slides.add_slide(blank_layout)

        if presentation.theme and presentation.theme.background_color:
            _set_slide_background(slide_obj, presentation.theme.background_color)

        if slide_data.content_data and slide_data.layout_id:
            _render_content_data(slide_obj, slide_data.layout_id, slide_data.content_data, theme_color)
        else:
            for comp in slide_data.components:
                if comp.type.value == "text":
                    _add_text_component(slide_obj, comp)
                else:
                    _add_placeholder_component(slide_obj, comp)

        if slide_data.speaker_notes:
            notes_slide = slide_obj.notes_slide
            notes_slide.notes_text_frame.text = slide_data.speaker_notes

    buffer = io.BytesIO()
    prs.save(buffer)
    buffer.seek(0)
    return buffer.read()

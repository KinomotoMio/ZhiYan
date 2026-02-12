"""PPTX 模板解析 — 提取布局、配色、字体信息

使用 python-pptx 读取上传的 .pptx 文件，
提取 slide layouts、配色方案和字体配置。
"""

import io
import logging
from dataclasses import dataclass, field

from pptx import Presentation as PptxPresentation
from pptx.util import Emu

logger = logging.getLogger(__name__)


@dataclass
class SlotInfo:
    """layout 中的一个占位符插槽"""
    name: str
    role: str  # "title" | "body" | "subtitle" | "image" | "other"
    x_pct: float
    y_pct: float
    width_pct: float
    height_pct: float


@dataclass
class LayoutInfo:
    """一个 slide layout 的信息"""
    name: str
    slots: list[SlotInfo] = field(default_factory=list)


@dataclass
class ColorScheme:
    """配色方案"""
    primary: str = "#333333"
    secondary: str = "#666666"
    accent: str = "#3b82f6"
    background: str = "#ffffff"


@dataclass
class TemplateConfig:
    """解析后的模板配置"""
    template_id: str
    name: str
    layouts: list[LayoutInfo] = field(default_factory=list)
    colors: ColorScheme = field(default_factory=ColorScheme)
    font_family: str = "Microsoft YaHei"
    heading_font: str = "Microsoft YaHei"


def _emu_to_pct(emu_val: int, total_emu: int) -> float:
    """EMU 转百分比"""
    if total_emu == 0:
        return 0
    return round(emu_val / total_emu * 100, 1)


def _classify_placeholder(ph_type: int, ph_idx: int) -> str:
    """根据占位符类型推断角色"""
    # python-pptx placeholder types
    # 0=TITLE, 1=BODY, 2=CENTER_TITLE, 3=SUBTITLE, 12=OBJECT, 15=PICTURE
    role_map = {
        0: "title",
        1: "body",
        2: "title",
        3: "subtitle",
        12: "body",
        15: "image",
    }
    return role_map.get(ph_type, "other")


def parse_pptx_template(file_bytes: bytes, template_id: str, name: str) -> TemplateConfig:
    """解析 PPTX 文件，提取模板配置"""
    prs = PptxPresentation(io.BytesIO(file_bytes))

    slide_width = prs.slide_width or Emu(12192000)
    slide_height = prs.slide_height or Emu(6858000)

    layouts: list[LayoutInfo] = []

    for layout in prs.slide_layouts:
        layout_info = LayoutInfo(name=layout.name)

        for ph in layout.placeholders:
            slot = SlotInfo(
                name=ph.name,
                role=_classify_placeholder(ph.placeholder_format.type, ph.placeholder_format.idx),
                x_pct=_emu_to_pct(ph.left, slide_width),
                y_pct=_emu_to_pct(ph.top, slide_height),
                width_pct=_emu_to_pct(ph.width, slide_width),
                height_pct=_emu_to_pct(ph.height, slide_height),
            )
            layout_info.slots.append(slot)

        if layout_info.slots:
            layouts.append(layout_info)

    # 提取配色（从 theme 中读取）
    colors = ColorScheme()
    try:
        theme = prs.slide_masters[0].element
        # 尝试从 theme XML 中提取颜色
        ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
        color_elems = theme.findall(".//a:clrScheme/a:dk1//a:srgbClr", ns)
        if color_elems:
            colors.primary = f"#{color_elems[0].get('val', '333333')}"
        accent_elems = theme.findall(".//a:clrScheme/a:accent1//a:srgbClr", ns)
        if accent_elems:
            colors.accent = f"#{accent_elems[0].get('val', '3b82f6')}"
    except Exception as e:
        logger.debug("Could not extract theme colors: %s", e)

    config = TemplateConfig(
        template_id=template_id,
        name=name,
        layouts=layouts,
        colors=colors,
    )

    logger.info("Parsed template '%s': %d layouts", name, len(layouts))
    return config

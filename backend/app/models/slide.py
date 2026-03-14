"""Slide 数据模型 — 与 shared/schemas/slide.schema.json 保持同步

layout_id + content_data 是主渲染契约。
components 字段仅保留读兼容。
"""

from enum import Enum

from pydantic import BaseModel, Field


class ComponentType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    CHART = "chart"
    SHAPE = "shape"


class ComponentRole(str, Enum):
    TITLE = "title"
    SUBTITLE = "subtitle"
    BODY = "body"
    CAPTION = "caption"
    DECORATION = "decoration"
    ILLUSTRATION = "illustration"


class LayoutType(str, Enum):
    # 旧版 layout type（向后兼容）
    TITLE_SLIDE = "title-slide"
    TITLE_CONTENT = "title-content"
    TITLE_CONTENT_IMAGE = "title-content-image"
    TWO_COLUMN = "two-column"
    IMAGE_FULL = "image-full"
    SECTION_HEADER = "section-header"
    BLANK = "blank"
    # 新版 layout IDs（与 layout_registry 一致）
    INTRO_SLIDE = "intro-slide"
    INTRO_SLIDE_LEFT = "intro-slide-left"
    SECTION_HEADER_SIDE = "section-header-side"
    OUTLINE_SLIDE = "outline-slide"
    OUTLINE_SLIDE_RAIL = "outline-slide-rail"
    BULLET_WITH_ICONS = "bullet-with-icons"
    BULLET_WITH_ICONS_CARDS = "bullet-with-icons-cards"
    NUMBERED_BULLETS = "numbered-bullets"
    NUMBERED_BULLETS_TRACK = "numbered-bullets-track"
    METRICS_SLIDE = "metrics-slide"
    METRICS_SLIDE_BAND = "metrics-slide-band"
    METRICS_WITH_IMAGE = "metrics-with-image"
    CHART_WITH_BULLETS = "chart-with-bullets"
    TABLE_INFO = "table-info"
    TWO_COLUMN_COMPARE = "two-column-compare"
    IMAGE_AND_DESCRIPTION = "image-and-description"
    TIMELINE = "timeline"
    QUOTE_SLIDE = "quote-slide"
    QUOTE_BANNER = "quote-banner"
    BULLET_ICONS_ONLY = "bullet-icons-only"
    CHALLENGE_OUTCOME = "challenge-outcome"
    THANK_YOU = "thank-you"
    THANK_YOU_CONTACT = "thank-you-contact"


class TextAlign(str, Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class VerticalAlign(str, Enum):
    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"


class Position(BaseModel):
    x: float = Field(ge=0, le=100, description="左边距百分比")
    y: float = Field(ge=0, le=100, description="上边距百分比")
    width: float = Field(gt=0, le=100, description="宽度百分比")
    height: float = Field(gt=0, le=100, description="高度百分比")


class Style(BaseModel):
    font_size: float | None = Field(None, alias="fontSize")
    font_weight: str | None = Field(None, alias="fontWeight")
    font_style: str | None = Field(None, alias="fontStyle")
    color: str | None = None
    background_color: str | None = Field(None, alias="backgroundColor")
    text_align: TextAlign | None = Field(None, alias="textAlign")
    vertical_align: VerticalAlign | None = Field(None, alias="verticalAlign")
    opacity: float | None = Field(None, ge=0, le=1)

    model_config = {"populate_by_name": True}


class Component(BaseModel):
    id: str
    type: ComponentType
    role: ComponentRole
    content: str | None = None
    position: Position
    style: Style | None = None
    chart_data: dict | None = Field(None, alias="chartData")

    model_config = {"populate_by_name": True}


class Slide(BaseModel):
    slide_id: str = Field(alias="slideId")
    layout_type: str = Field(alias="layoutType")

    # 新增：具体 layout ID（对应 template-registry 中的布局）
    layout_id: str | None = Field(None, alias="layoutId")

    # 新增：结构化内容数据（按 layout schema 生成的 JSON）
    content_data: dict | None = Field(None, alias="contentData")

    # 旧版兼容字段（只读兼容）
    components: list[Component] = Field(default_factory=list)

    speaker_notes: str | None = Field(None, alias="speakerNotes")
    template_slot_mapping: dict[str, str] | None = Field(
        None, alias="templateSlotMapping"
    )

    model_config = {"populate_by_name": True}


class Theme(BaseModel):
    primary_color: str | None = Field(None, alias="primaryColor")
    secondary_color: str | None = Field(None, alias="secondaryColor")
    background_color: str | None = Field(None, alias="backgroundColor")
    font_family: str | None = Field(None, alias="fontFamily")
    heading_font_family: str | None = Field(None, alias="headingFontFamily")

    model_config = {"populate_by_name": True}


class Presentation(BaseModel):
    presentation_id: str = Field(alias="presentationId")
    title: str
    theme: Theme | None = None
    slides: list[Slide]

    model_config = {"populate_by_name": True}

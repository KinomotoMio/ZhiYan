"""Slide 数据模型 — 与 shared/schemas/slide.schema.json 保持同步"""

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
    TITLE_SLIDE = "title-slide"
    TITLE_CONTENT = "title-content"
    TITLE_CONTENT_IMAGE = "title-content-image"
    TWO_COLUMN = "two-column"
    IMAGE_FULL = "image-full"
    SECTION_HEADER = "section-header"
    BLANK = "blank"


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
    layout_type: LayoutType = Field(alias="layoutType")
    components: list[Component]
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

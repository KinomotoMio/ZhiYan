"""Slide data models kept in sync with shared/schemas/slide.schema.json."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.utils.scene_background import REMOVE_BACKGROUND, normalize_scene_background


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
    INTRO_SLIDE = "intro-slide"
    OUTLINE_SLIDE = "outline-slide"
    BULLET_WITH_ICONS = "bullet-with-icons"
    NUMBERED_BULLETS = "numbered-bullets"
    METRICS_SLIDE = "metrics-slide"
    METRICS_WITH_IMAGE = "metrics-with-image"
    CHART_WITH_BULLETS = "chart-with-bullets"
    TABLE_INFO = "table-info"
    TWO_COLUMN_COMPARE = "two-column-compare"
    IMAGE_AND_DESCRIPTION = "image-and-description"
    TIMELINE = "timeline"
    QUOTE_SLIDE = "quote-slide"
    BULLET_ICONS_ONLY = "bullet-icons-only"
    CHALLENGE_OUTCOME = "challenge-outcome"
    THANK_YOU = "thank-you"


class TextAlign(str, Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class VerticalAlign(str, Enum):
    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"


class SceneBackgroundPreset(str, Enum):
    HERO_GLOW = "hero-glow"
    SECTION_BAND = "section-band"
    OUTLINE_GRID = "outline-grid"
    QUOTE_FOCUS = "quote-focus"
    CLOSING_WASH = "closing-wash"


class SceneBackgroundEmphasis(str, Enum):
    SUBTLE = "subtle"
    BALANCED = "balanced"
    IMMERSIVE = "immersive"


class SceneBackgroundColorToken(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    NEUTRAL = "neutral"


class Position(BaseModel):
    x: float = Field(ge=0, le=100, description="Left percentage")
    y: float = Field(ge=0, le=100, description="Top percentage")
    width: float = Field(gt=0, le=100, description="Width percentage")
    height: float = Field(gt=0, le=100, description="Height percentage")


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


class SceneBackground(BaseModel):
    kind: Literal["scene"]
    preset: SceneBackgroundPreset
    emphasis: SceneBackgroundEmphasis | None = None
    color_token: SceneBackgroundColorToken | None = Field(None, alias="colorToken")

    model_config = {"populate_by_name": True}


class Slide(BaseModel):
    slide_id: str = Field(alias="slideId")
    layout_type: str = Field(alias="layoutType")
    layout_id: str | None = Field(None, alias="layoutId")
    content_data: dict | None = Field(None, alias="contentData")
    background: SceneBackground | None = None
    components: list[Component] = Field(default_factory=list)
    speaker_notes: str | None = Field(None, alias="speakerNotes")
    template_slot_mapping: dict[str, str] | None = Field(
        None, alias="templateSlotMapping"
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_scene_background_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "background" not in value:
            return value

        data = dict(value)
        layout_id = data.get("layoutId") or data.get("layoutType")
        normalized_background = normalize_scene_background(
            layout_id if isinstance(layout_id, str) else None,
            data.get("background"),
        )
        if normalized_background is REMOVE_BACKGROUND:
            data.pop("background", None)
        else:
            data["background"] = normalized_background
        return data

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

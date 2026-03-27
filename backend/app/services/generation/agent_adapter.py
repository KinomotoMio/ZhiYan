from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.slide import Slide
from app.services.pipeline.layout_roles import get_default_layout_for_role, normalize_slide_role


SupportedLayoutHint = Literal[
    "intro-slide",
    "intro-slide-left",
    "outline-slide",
    "outline-slide-rail",
    "section-header",
    "section-header-side",
    "bullet-with-icons",
    "bullet-with-icons-cards",
    "metrics-slide",
    "metrics-slide-band",
    "timeline",
    "quote-slide",
    "thank-you",
    "thank-you-contact",
]


class AgentPoint(BaseModel):
    title: str
    detail: str = ""


class AgentSection(BaseModel):
    title: str
    description: str = ""


class AgentMetric(BaseModel):
    value: str
    label: str
    description: str = ""


class AgentTimelineEvent(BaseModel):
    date: str
    title: str
    description: str = ""


class AgentDeckSlide(BaseModel):
    slide_number: int = Field(alias="slideNumber", ge=1)
    title: str
    role: str = "narrative"
    layout_hint: SupportedLayoutHint | None = Field(default=None, alias="layoutHint")
    subtitle: str = ""
    objective: str = ""
    body: str = ""
    points: list[AgentPoint] = Field(default_factory=list)
    sections: list[AgentSection] = Field(default_factory=list)
    metrics: list[AgentMetric] = Field(default_factory=list)
    events: list[AgentTimelineEvent] = Field(default_factory=list)
    quote: str = ""
    quote_author: str = Field(default="", alias="quoteAuthor")
    takeaway: str = ""
    speaker_notes: str = Field(default="", alias="speakerNotes")

    model_config = {"populate_by_name": True}


class AgentDeck(BaseModel):
    title: str = ""
    subtitle: str = ""
    storyline: str = ""
    slides: list[AgentDeckSlide] = Field(default_factory=list)


class AgentOutlineItem(BaseModel):
    slide_number: int = Field(alias="slideNumber", ge=1)
    title: str
    role: str = "narrative"
    objective: str = ""
    key_points: list[str] = Field(default_factory=list, alias="keyPoints")
    content_hints: list[str] = Field(default_factory=list, alias="contentHints")

    model_config = {"populate_by_name": True}


class AgentOutline(BaseModel):
    title: str = ""
    subtitle: str = ""
    storyline: str = ""
    items: list[AgentOutlineItem] = Field(default_factory=list)


def outline_to_job_outline(outline: AgentOutline) -> dict[str, Any]:
    return {
        "title": outline.title,
        "subtitle": outline.subtitle,
        "storyline": outline.storyline,
        "items": [
            {
                "slide_number": item.slide_number,
                "title": item.title,
                "suggested_slide_role": normalize_slide_role(item.role),
                "objective": item.objective,
                "key_points": list(item.key_points),
                "content_hints": list(item.content_hints),
            }
            for item in sorted(outline.items, key=lambda item: item.slide_number)
        ],
    }


def deck_to_layout_selections(deck: AgentDeck) -> list[dict[str, Any]]:
    selections: list[dict[str, Any]] = []
    for slide in sorted(deck.slides, key=lambda item: item.slide_number):
        layout_id = _resolve_layout_hint(slide)
        selections.append(
            {
                "slide_number": slide.slide_number,
                "layout_id": layout_id,
                "suggested_slide_role": normalize_slide_role(slide.role),
            }
        )
    return selections


def deck_to_slides(deck: AgentDeck) -> list[Slide]:
    slides: list[Slide] = []
    for item in sorted(deck.slides, key=lambda slide: slide.slide_number):
        layout_id = _resolve_layout_hint(item)
        content_data = _content_data_for_slide(item, layout_id)
        slides.append(
            Slide(
                slideId=f"slide-{item.slide_number}",
                layoutType=layout_id,
                layoutId=layout_id,
                contentData=content_data,
                components=[],
                speakerNotes=item.speaker_notes or None,
            )
        )
    return slides


def _resolve_layout_hint(slide: AgentDeckSlide) -> str:
    hinted = (slide.layout_hint or "").strip()
    if hinted:
        if hinted.startswith("metrics") and not slide.metrics:
            return "bullet-with-icons"
        if hinted == "timeline" and not slide.events:
            return "bullet-with-icons"
        if hinted == "quote-slide" and not (slide.quote or slide.body or slide.takeaway):
            return "bullet-with-icons"
        return hinted
    return get_default_layout_for_role(slide.role)


def _content_data_for_slide(slide: AgentDeckSlide, layout_id: str) -> dict[str, Any]:
    if layout_id in {"intro-slide", "intro-slide-left"}:
        return {
            "title": slide.title,
            "subtitle": slide.subtitle or slide.body or slide.objective,
        }
    if layout_id in {"outline-slide", "outline-slide-rail"}:
        sections = slide.sections or [
            AgentSection(title=point.title, description=point.detail)
            for point in slide.points
        ]
        return {
            "title": slide.title,
            "subtitle": slide.subtitle or slide.objective,
            "sections": [
                {"title": section.title, "description": section.description or None}
                for section in sections
                if section.title.strip()
            ],
        }
    if layout_id in {"section-header", "section-header-side"}:
        return {
            "title": slide.title,
            "subtitle": slide.subtitle or slide.objective or slide.takeaway or slide.body,
        }
    if layout_id in {"metrics-slide", "metrics-slide-band"}:
        return {
            "title": slide.title,
            "metrics": [
                {
                    "value": metric.value,
                    "label": metric.label,
                    "description": metric.description or None,
                }
                for metric in slide.metrics[:4]
            ],
            "conclusion": slide.takeaway or slide.subtitle or slide.body or slide.objective,
            "conclusionBrief": slide.body or slide.objective or slide.subtitle or slide.takeaway,
        }
    if layout_id == "timeline":
        return {
            "title": slide.title,
            "events": [
                {
                    "date": event.date,
                    "title": event.title,
                    "description": event.description or None,
                }
                for event in slide.events
            ],
        }
    if layout_id == "quote-slide":
        return {
            "quote": slide.quote or slide.body or slide.takeaway or slide.title,
            "author": slide.quote_author or None,
            "context": slide.subtitle or slide.objective or None,
        }
    if layout_id in {"thank-you", "thank-you-contact"}:
        return {
            "title": slide.title,
            "subtitle": slide.subtitle or slide.takeaway or slide.body,
            "contact": slide.body or None,
        }
    return {
        "title": slide.title,
        "items": [
            {
                "icon": {"query": point.title or "sparkles"},
                "title": point.title,
                "description": point.detail or "",
            }
            for point in slide.points
            if point.title.strip()
        ],
    }

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.models.slide import Slide
from app.services.layouts.layout_roles import get_default_layout_for_role, normalize_slide_role


SupportedLayoutHint = Literal[
    "intro-slide",
    "intro-slide-left",
    "outline-slide",
    "outline-slide-rail",
    "section-header",
    "section-header-side",
    "bullet-with-icons",
    "bullet-with-icons-cards",
    "bullet-icons-only",
    "numbered-bullets",
    "numbered-bullets-track",
    "metrics-slide",
    "metrics-slide-band",
    "metrics-with-image",
    "timeline",
    "two-column-compare",
    "challenge-outcome",
    "image-and-description",
    "quote-slide",
    "quote-banner",
    "thank-you",
    "thank-you-contact",
]


class AgentBulletItem(BaseModel):
    title: str
    description: str = ""
    icon_query: str = Field(default="", alias="iconQuery")

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            payload = dict(data)
            if "description" not in payload and "detail" in payload:
                payload["description"] = payload.get("detail")
            if "title" not in payload and "label" in payload:
                payload["title"] = payload.get("label")
            return payload
        return data


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
    icon_query: str = Field(default="", alias="iconQuery")

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            payload = dict(data)
            if "value" not in payload and "metric_value" in payload:
                payload["value"] = payload.get("metric_value")
            if "label" not in payload and "metric_label" in payload:
                payload["label"] = payload.get("metric_label")
            if "description" not in payload and "metric_description" in payload:
                payload["description"] = payload.get("metric_description")
            return payload
        return data


class AgentTimelineEvent(BaseModel):
    date: str
    title: str
    description: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            payload = dict(data)
            if "title" not in payload and "event_title" in payload:
                payload["title"] = payload.get("event_title")
            if "description" not in payload and "event_description" in payload:
                payload["description"] = payload.get("event_description")
            return payload
        return data


class AgentStep(BaseModel):
    title: str
    description: str = ""


class AgentCompareColumn(BaseModel):
    heading: str
    items: list[str] = Field(default_factory=list)
    icon_query: str = Field(default="", alias="iconQuery")

    model_config = {"populate_by_name": True}


class AgentChallengeOutcomeItem(BaseModel):
    challenge: str
    outcome: str


class AgentImageRef(BaseModel):
    source: str = "user"
    prompt: str = ""
    url: str = ""
    alt: str = ""


class AgentDeckSlide(BaseModel):
    slide_number: int = Field(alias="slideNumber", ge=1)
    title: str
    role: str = "narrative"
    layout_hint: SupportedLayoutHint | None = Field(default=None, alias="layoutHint")
    subtitle: str = ""
    objective: str = ""
    body: str = ""
    conclusion: str = ""
    takeaway: str = ""
    contact: str = ""
    items: list[AgentBulletItem] = Field(default_factory=list)
    points: list[AgentPoint] = Field(default_factory=list)
    sections: list[AgentSection] = Field(default_factory=list)
    metrics: list[AgentMetric] = Field(default_factory=list)
    events: list[AgentTimelineEvent] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
    left: AgentCompareColumn | None = None
    right: AgentCompareColumn | None = None
    challenge_outcomes: list[AgentChallengeOutcomeItem] = Field(default_factory=list, alias="challengeOutcomes")
    image: AgentImageRef | None = None
    description: str = ""
    bullets: list[str] = Field(default_factory=list)
    quote: str = ""
    quote_author: str = Field(default="", alias="quoteAuthor")
    context: str = ""
    speaker_notes: str = Field(default="", alias="speakerNotes")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def normalize_legacy_fields(self) -> "AgentDeckSlide":
        if not self.items and self.points:
            self.items = [
                AgentBulletItem(title=point.title, description=point.detail)
                for point in self.points
                if point.title.strip()
            ]
        return self


class AgentDeck(BaseModel):
    title: str = ""
    subtitle: str = ""
    storyline: str = ""
    slides: list[AgentDeckSlide] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_slide_numbers(self) -> "AgentDeck":
        numbers = [slide.slide_number for slide in self.slides]
        if len(numbers) != len(set(numbers)):
            raise ValueError("Deck slide numbers must be unique.")
        return self


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
        return hinted

    role = normalize_slide_role(slide.role)
    if slide.left and slide.right:
        return "two-column-compare"
    if slide.challenge_outcomes:
        return "challenge-outcome"
    if slide.image and slide.metrics:
        return "metrics-with-image"
    if slide.metrics:
        return "metrics-slide-band" if len(slide.metrics) <= 3 else "metrics-slide"
    if slide.events:
        return "timeline"
    if slide.steps:
        return "numbered-bullets-track" if len(slide.steps) >= 4 else "numbered-bullets"
    if slide.sections:
        return "outline-slide-rail" if len(slide.sections) >= 5 else "outline-slide"
    if slide.quote:
        return "quote-banner" if slide.context else "quote-slide"
    if slide.image and slide.description:
        return "image-and-description"
    if role == "agenda":
        return "outline-slide-rail" if len(slide.sections) >= 5 else "outline-slide"
    if role == "section-divider":
        return "section-header-side"
    if role == "comparison":
        return "challenge-outcome" if slide.challenge_outcomes else "two-column-compare"
    if role == "process":
        return "numbered-bullets-track" if slide.steps else "timeline"
    if role == "highlight":
        return "quote-banner"
    if role == "closing":
        return "thank-you-contact" if slide.contact else "thank-you"

    bullet_items = _bullet_items_for_slide(slide)
    if len(bullet_items) >= 4:
        return "bullet-with-icons-cards"
    return get_default_layout_for_role(slide.role)


def _content_data_for_slide(slide: AgentDeckSlide, layout_id: str) -> dict[str, Any]:
    if layout_id in {"intro-slide", "intro-slide-left"}:
        return {
            "title": slide.title,
            "subtitle": slide.subtitle or slide.body or slide.objective or slide.takeaway,
        }
    if layout_id in {"outline-slide", "outline-slide-rail"}:
        sections = slide.sections or [
            AgentSection(title=item.title, description=item.description)
            for item in _bullet_items_for_slide(slide)
        ]
        return {
            "title": slide.title,
            "subtitle": slide.subtitle or slide.objective or slide.takeaway,
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
    if layout_id in {"bullet-with-icons", "bullet-with-icons-cards"}:
        return {
            "title": slide.title,
            "items": [
                {
                    "icon": {"query": item.icon_query or item.title or "sparkles"},
                    "title": item.title,
                    "description": item.description or "",
                }
                for item in _bullet_items_for_slide(slide)
                if item.title.strip()
            ],
        }
    if layout_id == "bullet-icons-only":
        return {
            "title": slide.title,
            "items": [
                {
                    "icon": {"query": item.icon_query or item.title or "sparkles"},
                    "label": item.title,
                }
                for item in _bullet_items_for_slide(slide)
                if item.title.strip()
            ],
        }
    if layout_id in {"numbered-bullets", "numbered-bullets-track"}:
        steps = slide.steps or [
            AgentStep(title=item.title, description=item.description)
            for item in _bullet_items_for_slide(slide)
        ]
        return {
            "title": slide.title,
            "items": [
                {"title": step.title, "description": step.description or ""}
                for step in steps
                if step.title.strip()
            ],
        }
    if layout_id in {"metrics-slide", "metrics-slide-band"}:
        conclusion = slide.conclusion or slide.takeaway or slide.subtitle or slide.body or slide.objective
        return {
            "title": slide.title,
            "metrics": [
                {
                    "value": metric.value,
                    "label": metric.label,
                    "description": metric.description or None,
                    "icon": {"query": metric.icon_query} if metric.icon_query else None,
                }
                for metric in slide.metrics[:4]
            ],
            "conclusion": conclusion,
            "conclusionBrief": slide.body or slide.objective or slide.subtitle or conclusion,
        }
    if layout_id == "metrics-with-image":
        return {
            "title": slide.title,
            "metrics": [
                {
                    "value": metric.value,
                    "label": metric.label,
                    "description": metric.description or None,
                }
                for metric in slide.metrics[:3]
            ],
            "image": _image_payload(slide.image),
        }
    if layout_id == "timeline":
        events = slide.events or [
            AgentTimelineEvent(date=str(index + 1), title=step.title, description=step.description)
            for index, step in enumerate(slide.steps)
        ]
        return {
            "title": slide.title,
            "events": [
                {
                    "date": event.date,
                    "title": event.title,
                    "description": event.description or None,
                }
                for event in events
            ],
        }
    if layout_id == "two-column-compare":
        left = slide.left or AgentCompareColumn(heading="Before", items=["待补充"])
        right = slide.right or AgentCompareColumn(heading="After", items=["待补充"])
        return {
            "title": slide.title,
            "left": {
                "heading": left.heading,
                "items": list(left.items),
                "icon": {"query": left.icon_query} if left.icon_query else None,
            },
            "right": {
                "heading": right.heading,
                "items": list(right.items),
                "icon": {"query": right.icon_query} if right.icon_query else None,
            },
        }
    if layout_id == "challenge-outcome":
        return {
            "title": slide.title,
            "items": [
                {
                    "challenge": item.challenge,
                    "outcome": item.outcome,
                }
                for item in slide.challenge_outcomes
            ],
        }
    if layout_id == "image-and-description":
        return {
            "title": slide.title,
            "image": _image_payload(slide.image),
            "description": slide.description or slide.body,
            "bullets": list(slide.bullets) or None,
        }
    if layout_id in {"quote-slide", "quote-banner"}:
        return {
            "quote": slide.quote or slide.body or slide.takeaway or slide.title,
            "author": slide.quote_author or None,
            "context": slide.context or slide.subtitle or slide.objective or None,
        }
    if layout_id in {"thank-you", "thank-you-contact"}:
        return {
            "title": slide.title,
            "subtitle": slide.subtitle or slide.takeaway or slide.body,
            "contact": slide.contact or slide.body or None,
        }
    return {
        "title": slide.title,
        "items": [
            {
                "icon": {"query": item.icon_query or item.title or "sparkles"},
                "title": item.title,
                "description": item.description or "",
            }
            for item in _bullet_items_for_slide(slide)
            if item.title.strip()
        ],
    }


def _bullet_items_for_slide(slide: AgentDeckSlide) -> list[AgentBulletItem]:
    if slide.items:
        return slide.items
    if slide.points:
        return [
            AgentBulletItem(title=point.title, description=point.detail)
            for point in slide.points
            if point.title.strip()
        ]
    return []


def _image_payload(image: AgentImageRef | None) -> dict[str, Any] | None:
    if image is None:
        return None
    return {
        "source": image.source,
        "prompt": image.prompt,
        "url": image.url or None,
        "alt": image.alt or "",
    }

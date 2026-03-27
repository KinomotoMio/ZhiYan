from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.services.layouts.layout_roles import normalize_slide_role


class AgentOutlineItem(BaseModel):
    slide_number: int = Field(alias="slideNumber", ge=1)
    title: str
    role: str = "narrative"
    objective: str = ""
    key_points: list[str] = Field(default_factory=list, alias="keyPoints")
    content_hints: list[str] = Field(default_factory=list, alias="contentHints")

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            payload = dict(data)
            if "role" not in payload and "type" in payload:
                payload["role"] = payload.get("type")
            return payload
        return data


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

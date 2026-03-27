"""Active runtime state for the embedded AgentLoop generation flow."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.models.slide import Slide

ProgressHook = Callable[[str, int, int, str], Awaitable[None]]
SlideHook = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(slots=True)
class GenerationRuntimeState:
    raw_content: str = ""
    source_ids: list[str] = field(default_factory=list)
    topic: str = ""
    template_id: str | None = None
    num_pages: int = 5
    job_id: str | None = None
    document_metadata: dict[str, Any] = field(default_factory=dict)
    outline: dict[str, Any] = field(default_factory=dict)
    layout_selections: list[dict[str, Any]] = field(default_factory=list)
    slide_contents: list[dict[str, Any]] = field(default_factory=list)
    slides: list[Slide] = field(default_factory=list)
    verification_issues: list[dict[str, Any]] = field(default_factory=list)
    failed_slide_indices: list[int] = field(default_factory=list)

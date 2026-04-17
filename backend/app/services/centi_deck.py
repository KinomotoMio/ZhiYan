"""Centi-deck JS-module deck artifact: pydantic contracts, validation, render payload."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field


_MODULE_SOURCE_MAX_BYTES = 64 * 1024
_STRICT_PREAMBLE = '"use strict";'

_FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^\s*import\b", re.MULTILINE), "top-level `import` is not allowed"),
    (re.compile(r"\bimport\s*\("), "dynamic import() is not allowed"),
    (re.compile(r"\brequire\s*\("), "require() is not allowed"),
    (re.compile(r"\bfetch\s*\("), "fetch() is not allowed"),
    (re.compile(r"\bXMLHttpRequest\b"), "XMLHttpRequest is not allowed"),
    (re.compile(r"\beval\s*\("), "eval() is not allowed"),
    (re.compile(r"\bnew\s+Function\b"), "new Function() is not allowed"),
    (re.compile(r"\bdocument\.cookie\b"), "document.cookie is not allowed"),
    (re.compile(r"\blocalStorage\b"), "localStorage is not allowed"),
    (re.compile(r"\bsessionStorage\b"), "sessionStorage is not allowed"),
    (re.compile(r"\bindexedDB\b"), "indexedDB is not allowed"),
    (re.compile(r"\bnavigator\.sendBeacon\b"), "navigator.sendBeacon is not allowed"),
    (re.compile(r"\bWebSocket\b"), "WebSocket is not allowed"),
    (re.compile(r"\bnew\s+Worker\b"), "Worker is not allowed"),
    (re.compile(r"\bnew\s+SharedWorker\b"), "SharedWorker is not allowed"),
]

_EXPORT_DEFAULT_RE = re.compile(r"\bexport\s+default\b")


class CentiDeckSlide(BaseModel):
    """A single centi-deck slide: metadata + plain text view + ES module source."""

    slide_id: str = Field(alias="slideId")
    title: str
    plain_text: str = Field(alias="plainText")
    module_source: str = Field(alias="moduleSource")
    notes: str | None = None
    audio_url: str | None = Field(None, alias="audioUrl")
    actions: list[dict[str, Any]] = Field(default_factory=list)
    drilldowns: list[dict[str, Any]] = Field(default_factory=list)
    background: dict[str, Any] | None = None
    transition: str | None = None

    model_config = {"populate_by_name": True}


class CentiDeckArtifact(BaseModel):
    """Full deck artifact as persisted in session_presentations.payload_json."""

    version: str = "centi-deck-v1"
    title: str
    theme: dict[str, Any] | None = None
    presenter: dict[str, Any] | None = None
    export: dict[str, Any] | None = None
    slides: list[CentiDeckSlide]

    model_config = {"populate_by_name": True}


class CentiDeckRenderPayload(BaseModel):
    """Render payload served to frontend: artifact + capability flags + slide count."""

    artifact_version: str = Field(alias="artifactVersion")
    runtime_version: str = Field(alias="runtimeVersion")
    title: str
    slide_count: int = Field(alias="slideCount")
    theme: dict[str, Any] | None = None
    slides: list[CentiDeckSlide]
    presenter_capabilities: dict[str, Any] = Field(alias="presenterCapabilities")
    export_capabilities: dict[str, Any] = Field(alias="exportCapabilities")

    model_config = {"populate_by_name": True}


def validate_module_source(source: str, *, slide_id: str) -> str:
    """Validate and return (potentially strict-mode prepended) module source.

    Raises ValueError if the module violates the centi-deck author contract.
    """
    cleaned = str(source or "").strip()
    if not cleaned:
        raise ValueError(f"Slide {slide_id}: module_source is empty")
    if len(cleaned.encode("utf-8")) > _MODULE_SOURCE_MAX_BYTES:
        raise ValueError(
            f"Slide {slide_id}: module_source exceeds {_MODULE_SOURCE_MAX_BYTES} bytes"
        )
    if not _EXPORT_DEFAULT_RE.search(cleaned):
        raise ValueError(f"Slide {slide_id}: module must contain `export default`")
    for pattern, message in _FORBIDDEN_PATTERNS:
        match = pattern.search(cleaned)
        if match is not None:
            raise ValueError(
                f"Slide {slide_id}: {message} (matched {match.group(0)!r})"
            )
    if not (cleaned.startswith('"use strict"') or cleaned.startswith("'use strict'")):
        cleaned = f"{_STRICT_PREAMBLE}\n{cleaned}"
    return cleaned


def normalize_centi_deck_submission(
    *,
    payload: dict[str, Any],
    fallback_title: str,
    expected_slide_count: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize an agent-submitted centi-deck manifest.

    Returns (artifact_dict, render_payload_dict), both as JSON-mode model_dump
    with camelCase aliases.
    """
    artifact_in = CentiDeckArtifact.model_validate(payload or {})
    if not artifact_in.slides:
        raise ValueError("Centi-deck submission must include at least one slide.")
    if expected_slide_count is not None and len(artifact_in.slides) != expected_slide_count:
        raise ValueError(
            f"Centi-deck slide count mismatch: expected {expected_slide_count}, got {len(artifact_in.slides)}."
        )

    title = artifact_in.title.strip() or fallback_title.strip() or "新演示文稿"
    seen_ids: set[str] = set()
    normalized_slides: list[CentiDeckSlide] = []
    for index, slide in enumerate(artifact_in.slides, start=1):
        slide_id = (slide.slide_id or f"slide-{index}").strip() or f"slide-{index}"
        if slide_id in seen_ids:
            raise ValueError(f"Duplicate slideId: {slide_id}")
        seen_ids.add(slide_id)

        slide_title = slide.title.strip()
        if not slide_title:
            raise ValueError(f"Slide {slide_id}: title is empty")
        plain_text = slide.plain_text.strip()
        if not plain_text:
            raise ValueError(f"Slide {slide_id}: plain_text is empty")

        validated_source = validate_module_source(slide.module_source, slide_id=slide_id)

        normalized_slides.append(
            CentiDeckSlide(
                slideId=slide_id,
                title=slide_title,
                plainText=plain_text,
                moduleSource=validated_source,
                notes=_clean_str(slide.notes),
                audioUrl=_clean_str(slide.audio_url),
                actions=list(slide.actions or []),
                drilldowns=list(slide.drilldowns or []),
                background=dict(slide.background) if isinstance(slide.background, dict) else None,
                transition=_clean_str(slide.transition),
            )
        )

    artifact_out = CentiDeckArtifact(
        version="centi-deck-v1",
        title=title,
        theme=dict(artifact_in.theme) if isinstance(artifact_in.theme, dict) else None,
        presenter=dict(artifact_in.presenter) if isinstance(artifact_in.presenter, dict) else None,
        export=dict(artifact_in.export) if isinstance(artifact_in.export, dict) else None,
        slides=normalized_slides,
    )
    render_payload = CentiDeckRenderPayload(
        artifactVersion="centi-deck-v1",
        runtimeVersion="centi-deck-v1",
        title=title,
        slideCount=len(normalized_slides),
        theme=artifact_out.theme,
        slides=normalized_slides,
        presenterCapabilities={
            "navigation": True,
            "slideSync": True,
            "roomSync": False,
            "actions": False,
            "drilldowns": False,
        },
        exportCapabilities={
            "pdf": True,
            "printMode": True,
        },
    )
    return (
        artifact_out.model_dump(mode="json", by_alias=True, exclude_none=True),
        render_payload.model_dump(mode="json", by_alias=True, exclude_none=True),
    )


def _clean_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None

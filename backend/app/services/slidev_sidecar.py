from __future__ import annotations

from copy import deepcopy
from typing import Any


def empty_slidev_sidecar() -> dict[str, Any]:
    return {
        "speaker_notes": {},
        "speaker_audio": {},
    }


def normalize_slidev_sidecar(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return empty_slidev_sidecar()

    raw_notes = payload.get("speaker_notes")
    raw_audio = payload.get("speaker_audio")
    return {
        "speaker_notes": (
            {
                str(slide_id): str(notes).strip()
                for slide_id, notes in raw_notes.items()
                if str(slide_id).strip() and isinstance(notes, str)
            }
            if isinstance(raw_notes, dict)
            else {}
        ),
        "speaker_audio": (
            {
                str(slide_id): dict(meta)
                for slide_id, meta in raw_audio.items()
                if str(slide_id).strip() and isinstance(meta, dict)
            }
            if isinstance(raw_audio, dict)
            else {}
        ),
    }


def list_slidev_meta_slides(meta: dict[str, Any] | None) -> list[dict[str, Any]]:
    raw_slides = meta.get("slides") if isinstance(meta, dict) else None
    return [slide for slide in raw_slides if isinstance(slide, dict)] if isinstance(raw_slides, list) else []


def validate_slidev_slide_id(meta: dict[str, Any] | None, slide_id: str) -> dict[str, Any] | None:
    normalized_slide_id = str(slide_id or "").strip()
    if not normalized_slide_id:
        return None
    for slide in list_slidev_meta_slides(meta):
        if str(slide.get("slide_id") or "").strip() == normalized_slide_id:
            return slide
    return None


def build_slidev_context_presentation(
    *,
    markdown: str,
    meta: dict[str, Any] | None,
    sidecar: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_sidecar = normalize_slidev_sidecar(sidecar)
    slides = []
    for slide in list_slidev_meta_slides(meta):
        slide_id = str(slide.get("slide_id") or "").strip()
        if not slide_id:
            continue
        notes = normalized_sidecar["speaker_notes"].get(slide_id)
        speaker_audio = normalized_sidecar["speaker_audio"].get(slide_id)
        content_data = {
            "title": str(slide.get("title") or "").strip(),
            "role": str(slide.get("role") or "narrative").strip() or "narrative",
            "layout": str(slide.get("layout") or "default").strip() or "default",
        }
        slide_payload: dict[str, Any] = {
            "slideId": slide_id,
            "layoutType": "slidev-index",
            "layoutId": "slidev-index",
            "contentData": content_data,
            "components": [],
        }
        if notes:
            slide_payload["speakerNotes"] = notes
        if isinstance(speaker_audio, dict) and speaker_audio:
            slide_payload["speakerAudio"] = deepcopy(speaker_audio)
        slides.append(slide_payload)
    return {
        "presentationId": "pres-slidev-context",
        "title": str((meta or {}).get("title") or "新演示文稿"),
        "slides": slides,
        "slidevMarkdown": markdown,
    }


def build_slidev_persistence_payload(
    latest: dict[str, Any] | None,
    *,
    title: str,
) -> dict[str, Any]:
    artifacts = dict((latest or {}).get("artifacts") or {}) if isinstance((latest or {}).get("artifacts"), dict) else {}
    payload: dict[str, Any] = {
        "title": title,
        "outputMode": "slidev",
        "artifactStatus": (latest or {}).get("artifact_status") or "ready",
        "renderStatus": (latest or {}).get("render_status") or "pending",
        "renderError": (latest or {}).get("render_error"),
        "artifactAvailable": bool((latest or {}).get("artifact_available", True)),
        "renderAvailable": bool((latest or {}).get("render_available", False)),
    }
    if artifacts:
        payload["artifacts"] = deepcopy(artifacts)
    return payload

"""Narrative note helpers for group -> note_tag -> layout selection."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Literal, cast

from app.services.pipeline.layout_metadata import load_layout_metadata

NarrativeNoteTag = Literal["图标要点", "纯图标网格", "图文混排"]
LayoutNoteTag = NarrativeNoteTag

_METADATA = load_layout_metadata()

_FALLBACK_LAYOUT_NOTES: dict[str, tuple[str, str]] = {
    "bullet-with-icons": ("图标要点", "带图标的 3-4 个要点，适合功能介绍、优势列举"),
    "bullet-icons-only": ("纯图标网格", "4-8 个图标+标签的网格，适合技术栈、特性一览"),
    "image-and-description": ("图文混排", "图片+描述文字，适合产品展示、案例说明"),
}

_LAYOUT_ID_TO_NOTE: dict[str, tuple[LayoutNoteTag, str] | None] = {}
for layout_id, raw_entry in _METADATA.get("layouts", {}).items():
    note_tag = raw_entry.get("noteTag")
    note_text = raw_entry.get("noteText")
    if isinstance(note_tag, str) and isinstance(note_text, str):
        tag = note_tag.strip()
        text = note_text.strip()
        if tag and text and tag in ("图标要点", "纯图标网格", "图文混排"):
            _LAYOUT_ID_TO_NOTE[layout_id] = (cast(LayoutNoteTag, tag), text)
            continue
    _LAYOUT_ID_TO_NOTE[layout_id] = _FALLBACK_LAYOUT_NOTES.get(layout_id)

_NOTE_TAG_TO_LAYOUT_IDS: dict[LayoutNoteTag, tuple[str, ...]] = {}
_grouped_layouts: dict[LayoutNoteTag, list[str]] = defaultdict(list)
for layout_id, note in _LAYOUT_ID_TO_NOTE.items():
    if note is None:
        continue
    _grouped_layouts[note[0]].append(layout_id)
for tag in ("图标要点", "纯图标网格", "图文混排"):
    _NOTE_TAG_TO_LAYOUT_IDS[cast(LayoutNoteTag, tag)] = tuple(_grouped_layouts[cast(LayoutNoteTag, tag)])

_MEDIA_KEYWORDS = (
    "image",
    "photo",
    "screenshot",
    "hero",
    "visual",
    "图片",
    "配图",
    "照片",
    "截图",
    "视觉",
    "图示",
)
_GRID_KEYWORDS = (
    "grid",
    "matrix",
    "capability",
    "taxonomy",
    "icon-only",
    "网格",
    "矩阵",
    "能力清单",
    "能力图谱",
    "标签墙",
)


def get_layout_note_tag(layout_id: str) -> LayoutNoteTag | None:
    note = _LAYOUT_ID_TO_NOTE.get(layout_id)
    if not note:
        return None
    return note[0]


def get_layout_note_text(layout_id: str) -> str | None:
    note = _LAYOUT_ID_TO_NOTE.get(layout_id)
    if not note:
        return None
    return note[1]


def format_layout_note(layout_id: str, fallback_text: str) -> str:
    note = _LAYOUT_ID_TO_NOTE.get(layout_id)
    if not note:
        return fallback_text
    return f"【{note[0]}】{note[1]}"


def infer_narrative_note_tag(
    title: str,
    content_brief: str,
    key_points: Sequence[str] | None = None,
) -> NarrativeNoteTag:
    points = [str(point).strip() for point in (key_points or []) if str(point).strip()]
    haystack = " ".join([title or "", content_brief or "", *points]).lower()

    if any(keyword in haystack for keyword in _MEDIA_KEYWORDS):
        return "图文混排"

    if len(points) >= 5 or any(keyword in haystack for keyword in _GRID_KEYWORDS):
        return "纯图标网格"

    return "图标要点"


def get_layout_ids_for_note_tag(note_tag: LayoutNoteTag) -> tuple[str, ...]:
    return _NOTE_TAG_TO_LAYOUT_IDS.get(note_tag, ())

"""Helpers for normalizing and persisting AI-authored HTML slide decks."""

from __future__ import annotations

from html import unescape
import re
from typing import Any


_TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_SECTION_RE = re.compile(r"<section\b([^>]*)>(.*?)</section>", re.IGNORECASE | re.DOTALL)
_DATA_ATTR_RE = re.compile(r'data-(slide-id|slide-title)\s*=\s*"([^"]*)"|data-(slide-id|slide-title)\s*=\s*\'([^\']*)\'', re.IGNORECASE)
_SECTION_DATA_ATTR_RE = re.compile(
    r'\s*data-(?:slide-id|slide-title)\s*=\s*(?:"[^"]*"|\'[^\']*\')',
    re.IGNORECASE,
)
_NOTES_ASIDE_RE = re.compile(
    r"<aside\b(?=[^>]*\bclass\s*=\s*(?:\"[^\"]*\bnotes\b[^\"]*\"|'[^']*\bnotes\b[^']*'))[^>]*>(.*?)</aside>",
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_HEADING_RE = re.compile(r"<h[1-3]\b[^>]*>(.*?)</h[1-3]>", re.IGNORECASE | re.DOTALL)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_html_deck(
    *,
    html: str,
    fallback_title: str,
    expected_slide_count: int | None = None,
    existing_slides: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Normalize a raw deck into a stable Reveal-compatible HTML document."""
    raw_html = str(html or "").strip()
    if not raw_html:
        raise ValueError("HTML deck is empty.")

    title = _extract_title(raw_html) or fallback_title.strip() or "新演示文稿"
    custom_styles = "\n".join(
        block.strip() for block in _STYLE_RE.findall(raw_html) if str(block).strip()
    ).strip()

    raw_sections = list(_SECTION_RE.finditer(raw_html))
    if not raw_sections:
        raise ValueError("HTML deck must include at least one <section> slide.")
    if expected_slide_count is not None and len(raw_sections) != expected_slide_count:
        raise ValueError(
            f"HTML deck slide count mismatch: expected {expected_slide_count}, got {len(raw_sections)}."
        )

    section_html_parts: list[str] = []
    slides_meta: list[dict[str, Any]] = []
    existing_slide_by_id = _build_slide_lookup(existing_slides)
    for index, match in enumerate(raw_sections, start=1):
        attrs = match.group(1) or ""
        body = match.group(2) or ""
        slide_id = _extract_data_attr(attrs, "slide-id") or f"slide-{index}"
        slide_title = (
            _extract_data_attr(attrs, "slide-title")
            or _extract_heading(body)
            or f"第 {index} 页"
        )
        slide_title = _normalize_text(slide_title) or f"第 {index} 页"
        existing_slide = existing_slide_by_id.get(slide_id)
        requested_notes = _extract_slide_speaker_notes(existing_slide)
        body, speaker_notes = _upsert_speaker_notes(body, requested_notes)
        section_attrs = _build_section_attrs(
            attrs,
            slide_id=slide_id,
            slide_title=slide_title,
        )
        section_html_parts.append(
            f"<section{section_attrs}>{body}</section>"
        )
        slides_meta.append(
            {
                "index": index - 1,
                "slide_id": slide_id,
                "title": slide_title,
                "speaker_notes": speaker_notes,
            }
        )

    normalized_html = _build_reveal_document(
        title=title,
        sections_html="\n".join(section_html_parts),
        custom_styles=custom_styles,
    )
    meta = {
        "title": title,
        "slide_count": len(slides_meta),
        "slides": slides_meta,
    }
    presentation = _build_html_presentation_payload(
        title=title,
        slides_meta=slides_meta,
        existing_slide_by_id=existing_slide_by_id,
    )
    return normalized_html, meta, presentation


def _extract_title(html: str) -> str:
    match = _TITLE_RE.search(html)
    return _normalize_text(match.group(1) if match else "")


def _extract_heading(section_body: str) -> str:
    match = _HEADING_RE.search(section_body)
    return _normalize_text(match.group(1) if match else "")


def _extract_data_attr(attrs: str, expected_name: str) -> str:
    for match in _DATA_ATTR_RE.finditer(attrs):
        left_name = (match.group(1) or "").lower()
        left_value = match.group(2) or ""
        right_name = (match.group(3) or "").lower()
        right_value = match.group(4) or ""
        if left_name == expected_name:
            return _normalize_text(left_value)
        if right_name == expected_name:
            return _normalize_text(right_value)
    return ""


def _normalize_text(value: str) -> str:
    text = _TAG_RE.sub(" ", str(value or ""))
    text = unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _extract_slide_speaker_notes(slide: dict[str, Any] | None) -> str | None:
    if not isinstance(slide, dict):
        return None
    notes = str(slide.get("speakerNotes") or "").strip()
    return notes if notes else ""


def _build_slide_lookup(
    existing_slides: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for slide in existing_slides or []:
        if not isinstance(slide, dict):
            continue
        slide_id = str(slide.get("slideId") or "").strip()
        if not slide_id:
            continue
        lookup[slide_id] = slide
    return lookup


def _extract_existing_speaker_notes(section_body: str) -> str | None:
    match = _NOTES_ASIDE_RE.search(section_body or "")
    if not match:
        return None
    notes = _normalize_text(match.group(1))
    return notes or None


def _strip_existing_speaker_notes(section_body: str) -> str:
    body = _NOTES_ASIDE_RE.sub("", section_body or "")
    return body.rstrip()


def _render_speaker_notes(notes: str) -> str:
    return f'\n    <aside class="notes">{_escape_html(notes)}</aside>'


def _upsert_speaker_notes(section_body: str, requested_notes: str | None) -> tuple[str, str | None]:
    body_without_notes = _strip_existing_speaker_notes(section_body)
    existing_notes = _extract_existing_speaker_notes(section_body)

    if requested_notes is None:
        final_notes = existing_notes
    else:
        final_notes = requested_notes.strip() or None

    if final_notes:
        return f"{body_without_notes}{_render_speaker_notes(final_notes)}", final_notes
    return body_without_notes, None


def _escape_attr(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _escape_html(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _build_section_attrs(raw_attrs: str, *, slide_id: str, slide_title: str) -> str:
    preserved = _SECTION_DATA_ATTR_RE.sub(" ", str(raw_attrs or ""))
    preserved = _WHITESPACE_RE.sub(" ", preserved).strip()
    normalized = (
        f'data-slide-id="{_escape_attr(slide_id)}" '
        f'data-slide-title="{_escape_attr(slide_title)}"'
    )
    if preserved:
        return f" {preserved} {normalized}"
    return f" {normalized}"


def _build_presentation_slide(
    slide_meta: dict[str, Any],
    existing_slide: dict[str, Any] | None,
) -> dict[str, Any]:
    slide = {
        "slideId": slide_meta["slide_id"],
        "layoutType": "html-meta",
        "layoutId": "html-meta",
        "contentData": {
            "title": slide_meta["title"],
        },
        "components": [],
    }
    speaker_notes = slide_meta.get("speaker_notes")
    if isinstance(speaker_notes, str) and speaker_notes.strip():
        slide["speakerNotes"] = speaker_notes.strip()
    if isinstance(existing_slide, dict):
        speaker_audio = existing_slide.get("speakerAudio")
        if isinstance(speaker_audio, dict):
            slide["speakerAudio"] = speaker_audio
    return slide


def _build_html_presentation_payload(
    *,
    title: str,
    slides_meta: list[dict[str, Any]],
    existing_slide_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "presentationId": "pres-html",
        "title": title,
        "outputMode": "html",
        "htmlDeckMeta": {
            "title": title,
            "slideCount": len(slides_meta),
            "slides": [
                _build_html_meta_slide(item, existing_slide_by_id.get(item["slide_id"]))
                for item in slides_meta
            ],
        },
        "slides": [
            _build_presentation_slide(item, existing_slide_by_id.get(item["slide_id"]))
            for item in slides_meta
        ],
    }


def _build_html_meta_slide(
    slide_meta: dict[str, Any],
    existing_slide: dict[str, Any] | None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "index": slide_meta["index"],
        "slideId": slide_meta["slide_id"],
        "title": slide_meta["title"],
    }
    speaker_notes = slide_meta.get("speaker_notes")
    if isinstance(speaker_notes, str):
        item["speakerNotes"] = speaker_notes
    if isinstance(existing_slide, dict):
        speaker_audio = existing_slide.get("speakerAudio")
        if isinstance(speaker_audio, dict):
            item["speakerAudio"] = speaker_audio
    return item


def _build_reveal_document(*, title: str, sections_html: str, custom_styles: str) -> str:
    style_block = f"\n{custom_styles}\n" if custom_styles else ""
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_escape_attr(title)}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/reveal.css" />
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/theme/white.css" />
  <style>
    html, body {{
      width: 100%;
      height: 100%;
      margin: 0;
      overflow: hidden;
      background: #ffffff;
    }}
    body {{
      font-family: "IBM Plex Sans", "Inter", "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    }}
    .reveal {{
      width: 100%;
      height: 100%;
      color: #111827;
      background: #ffffff;
    }}
    .reveal .slides {{
      text-align: left;
    }}
    .reveal .slides section {{
      width: 100%;
      height: 100%;
      padding: 0 !important;
      box-sizing: border-box;
      text-align: left;
      top: 0 !important;
    }}
    .reveal .slides section * {{
      box-sizing: border-box;
    }}{style_block}
  </style>
</head>
<body>
  <div class="reveal" tabindex="-1">
    <div class="slides">
{sections_html}
    </div>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/reveal.js"></script>
  <script>
    const revealElement = document.querySelector('.reveal');
    const deck = new Reveal(revealElement);
    const embeddedPreview =
      window.__ZY_REVEAL_PREVIEW__ && typeof window.__ZY_REVEAL_PREVIEW__ === 'object'
        ? window.__ZY_REVEAL_PREVIEW__
        : {{}};
    const query = new URLSearchParams(window.location.search);
    const requestedSlide = Number.parseInt(
      String(embeddedPreview.slide ?? query.get('slide') ?? '0'),
      10
    );
    const initialSlide = Number.isFinite(requestedSlide) ? Math.max(0, requestedSlide) : 0;
    const requestedMode = embeddedPreview.mode ?? query.get('mode');
    const previewMode = requestedMode === 'thumbnail' ? 'thumbnail' : 'interactive';
    const isInteractive = previewMode === 'interactive';
    document.documentElement.dataset.previewMode = previewMode;

    const focusRevealSurface = () => {{
      if (!isInteractive) return;
      try {{
        window.focus();
      }} catch {{
      }}
      try {{
        revealElement?.focus({{ preventScroll: true }});
      }} catch {{
        try {{
          revealElement?.focus();
        }} catch {{
        }}
      }}
    }};

    const notifySlideChange = () => {{
      if (!isInteractive) return;
      const {{ h }} = deck.getIndices();
      window.parent.postMessage(
        {{ type: 'reveal-preview-slidechange', slideIndex: h }},
        window.location.origin
      );
    }};

    deck.on('ready', () => {{
      if (initialSlide > 0) {{
        deck.slide(initialSlide);
      }} else {{
        notifySlideChange();
      }}
      if (isInteractive) {{
        window.requestAnimationFrame(focusRevealSurface);
      }}
    }});
    if (isInteractive) {{
      deck.on('slidechanged', notifySlideChange);
    }}

    deck.initialize({{
      hash: false,
      width: 1280,
      height: 720,
      margin: 0,
      center: false,
      embedded: true,
    }});
  </script>
</body>
</html>"""

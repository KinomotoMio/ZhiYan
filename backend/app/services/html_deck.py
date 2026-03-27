"""Helpers for normalizing and persisting AI-authored HTML slide decks."""

from __future__ import annotations

from html import unescape
import re
from typing import Any


_TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_SECTION_RE = re.compile(r"<section\b([^>]*)>(.*?)</section>", re.IGNORECASE | re.DOTALL)
_DATA_ATTR_RE = re.compile(r'data-(slide-id|slide-title)\s*=\s*"([^"]*)"|data-(slide-id|slide-title)\s*=\s*\'([^\']*)\'', re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_HEADING_RE = re.compile(r"<h[1-3]\b[^>]*>(.*?)</h[1-3]>", re.IGNORECASE | re.DOTALL)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_html_deck(
    *,
    html: str,
    fallback_title: str,
    expected_slide_count: int | None = None,
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
        section_html_parts.append(
            f'<section data-slide-id="{_escape_attr(slide_id)}" '
            f'data-slide-title="{_escape_attr(slide_title)}">{body}</section>'
        )
        slides_meta.append(
            {
                "index": index - 1,
                "slide_id": slide_id,
                "title": slide_title,
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
    presentation = {
        "presentationId": "pres-html",
        "title": title,
        "slides": [
            {
                "slideId": item["slide_id"],
                "layoutType": "blank",
                "layoutId": "blank",
                "contentData": {
                    "title": item["title"],
                    "_htmlDeck": True,
                },
                "components": [],
            }
            for item in slides_meta
        ],
    }
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


def _escape_attr(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


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

    const focusRevealSurface = () => {{
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
      const {{ h }} = deck.getIndices();
      window.parent.postMessage(
        {{ type: 'reveal-preview-slidechange', slideIndex: h }},
        window.location.origin
      );
    }};

    deck.on('ready', () => {{
      notifySlideChange();
      window.requestAnimationFrame(focusRevealSurface);
    }});
    deck.on('slidechanged', notifySlideChange);

    deck.initialize({{
      hash: true,
      width: 1280,
      height: 720,
      margin: 0,
      center: false,
      embedded: true,
    }});
  </script>
</body>
</html>"""

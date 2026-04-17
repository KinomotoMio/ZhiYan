"""HTML runtime manifest parsing, sanitization, and render payload generation."""

from __future__ import annotations

from html import unescape
import json
import re
from typing import Any

from pydantic import BaseModel, Field

from app.models.slide import Presentation


_TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_SECTION_RE = re.compile(r"<section\b([^>]*)>(.*?)</section>", re.IGNORECASE | re.DOTALL)
_DATA_ATTR_RE = re.compile(
    r'data-(slide-id|slide-title)\s*=\s*"([^"]*)"|data-(slide-id|slide-title)\s*=\s*\'([^\']*)\'',
    re.IGNORECASE,
)
_NOTES_ASIDE_RE = re.compile(
    r"<aside\b(?=[^>]*\bclass\s*=\s*(?:\"[^\"]*\bnotes\b[^\"]*\"|'[^']*\bnotes\b[^']*'))[^>]*>(.*?)</aside>",
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_HEADING_RE = re.compile(r"<h[1-3]\b[^>]*>(.*?)</h[1-3]>", re.IGNORECASE | re.DOTALL)
_WHITESPACE_RE = re.compile(r"\s+")
_SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_IFRAME_TAG_RE = re.compile(r"<iframe\b[^>]*>.*?</iframe>", re.IGNORECASE | re.DOTALL)
_STYLE_TAG_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)
_DOCUMENT_TAG_RE = re.compile(r"</?(?:html|head|body)\b[^>]*>", re.IGNORECASE)
_EVENT_ATTR_RE = re.compile(
    r"""\s+on[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""",
    re.IGNORECASE,
)
_JAVASCRIPT_URL_RE = re.compile(r"javascript\s*:", re.IGNORECASE)
_IMPORT_RE = re.compile(r"@import\b[^;]*;?", re.IGNORECASE)
_EXPRESSION_RE = re.compile(r"expression\s*\(", re.IGNORECASE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


class HtmlRuntimeSlideManifest(BaseModel):
    slide_id: str = Field(alias="slideId")
    title: str
    body_html: str = Field(alias="bodyHtml")
    scoped_css: str | None = Field(None, alias="scopedCss")
    speaker_notes: str | None = Field(None, alias="speakerNotes")
    actions: list[dict[str, Any]] = Field(default_factory=list)
    drilldowns: list[dict[str, Any]] = Field(default_factory=list)
    background: dict[str, Any] | None = None
    transition: str | None = None

    model_config = {"populate_by_name": True}


class HtmlRuntimeManifest(BaseModel):
    version: str = "runtime_v2"
    title: str
    theme: dict[str, Any] | None = None
    presenter: dict[str, Any] | None = None
    export: dict[str, Any] | None = None
    slides: list[HtmlRuntimeSlideManifest]

    model_config = {"populate_by_name": True}


class HtmlRuntimeSlideRender(BaseModel):
    index: int
    slide_id: str = Field(alias="slideId")
    title: str
    html: str
    css: str = ""
    speaker_notes: str | None = Field(None, alias="speakerNotes")

    model_config = {"populate_by_name": True}


class HtmlRuntimeRenderPayload(BaseModel):
    artifact_version: str = Field(alias="artifactVersion")
    runtime_version: str = Field(alias="runtimeVersion")
    title: str
    slide_count: int = Field(alias="slideCount")
    theme: dict[str, Any] | None = None
    slides: list[HtmlRuntimeSlideRender]
    document_html: str = Field(alias="documentHtml")
    presenter_capabilities: dict[str, Any] = Field(alias="presenterCapabilities")
    export_capabilities: dict[str, Any] = Field(alias="exportCapabilities")

    model_config = {"populate_by_name": True}


def build_html_runtime_artifact(
    *,
    manifest_payload: dict[str, Any] | None = None,
    legacy_html: str | None = None,
    fallback_title: str,
    expected_slide_count: int | None = None,
    existing_slides: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if manifest_payload is None:
        manifest_payload = lift_legacy_html_to_manifest(
            html=legacy_html or "",
            fallback_title=fallback_title,
            expected_slide_count=expected_slide_count,
            existing_slides=existing_slides,
        )
    normalized_manifest = normalize_html_runtime_manifest(
        manifest_payload,
        fallback_title=fallback_title,
        expected_slide_count=expected_slide_count,
        existing_slides=existing_slides,
    )
    render_payload = build_html_runtime_render_payload(normalized_manifest)
    presentation = build_presentation_projection(
        normalized_manifest,
        existing_slides=existing_slides,
    )
    return (
        normalized_manifest.model_dump(mode="json", by_alias=True, exclude_none=True),
        render_payload.model_dump(mode="json", by_alias=True, exclude_none=True),
        presentation.model_dump(mode="json", by_alias=True, exclude_none=True),
    )


def normalize_html_runtime_manifest(
    manifest_payload: dict[str, Any],
    *,
    fallback_title: str,
    expected_slide_count: int | None = None,
    existing_slides: list[dict[str, Any]] | None = None,
) -> HtmlRuntimeManifest:
    manifest = HtmlRuntimeManifest.model_validate(manifest_payload or {})
    if not manifest.slides:
        raise ValueError("HTML runtime manifest must include at least one slide.")
    if expected_slide_count is not None and len(manifest.slides) != expected_slide_count:
        raise ValueError(
            f"HTML runtime slide count mismatch: expected {expected_slide_count}, got {len(manifest.slides)}."
        )

    title = _normalize_text(manifest.title) or fallback_title.strip() or "新演示文稿"
    existing_lookup = _build_existing_slide_lookup(existing_slides)
    normalized_slides: list[HtmlRuntimeSlideManifest] = []
    seen_ids: set[str] = set()
    for index, slide in enumerate(manifest.slides, start=1):
        slide_id = _normalize_identifier(slide.slide_id or f"slide-{index}")
        if not slide_id:
            slide_id = f"slide-{index}"
        if slide_id in seen_ids:
            raise ValueError(f"Duplicate HTML runtime slideId: {slide_id}")
        seen_ids.add(slide_id)

        body_html = sanitize_html_fragment(slide.body_html)
        if not body_html:
            raise ValueError(f"HTML runtime slide {slide_id} bodyHtml is empty after sanitization.")

        inferred_title = (
            _normalize_text(slide.title)
            or _extract_heading(body_html)
            or f"第 {index} 页"
        )
        scoped_css = scope_slide_css(
            sanitize_scoped_css(slide.scoped_css or ""),
            slide_id=slide_id,
        )
        existing_notes = _extract_slide_speaker_notes(existing_lookup.get(slide_id))
        speaker_notes = (
            slide.speaker_notes.strip()
            if isinstance(slide.speaker_notes, str) and slide.speaker_notes.strip()
            else existing_notes
        )
        normalized_slides.append(
            HtmlRuntimeSlideManifest(
                slideId=slide_id,
                title=inferred_title,
                bodyHtml=body_html,
                scopedCss=scoped_css or None,
                speakerNotes=speaker_notes or None,
                actions=list(slide.actions or []),
                drilldowns=list(slide.drilldowns or []),
                background=dict(slide.background) if isinstance(slide.background, dict) else None,
                transition=str(slide.transition).strip() or None if slide.transition is not None else None,
            )
        )

    return HtmlRuntimeManifest(
        version="runtime_v2",
        title=title,
        theme=dict(manifest.theme) if isinstance(manifest.theme, dict) else None,
        presenter=dict(manifest.presenter) if isinstance(manifest.presenter, dict) else None,
        export=dict(manifest.export) if isinstance(manifest.export, dict) else None,
        slides=normalized_slides,
    )


def build_html_runtime_render_payload(manifest: HtmlRuntimeManifest) -> HtmlRuntimeRenderPayload:
    slides: list[HtmlRuntimeSlideRender] = []
    for index, slide in enumerate(manifest.slides):
        slides.append(
            HtmlRuntimeSlideRender(
                index=index,
                slideId=slide.slide_id,
                title=slide.title,
                html=slide.body_html,
                css=slide.scoped_css or "",
                speakerNotes=slide.speaker_notes,
            )
        )
    payload = HtmlRuntimeRenderPayload(
        artifactVersion="runtime_v2",
        runtimeVersion="v2",
        title=manifest.title,
        slideCount=len(slides),
        theme=dict(manifest.theme) if isinstance(manifest.theme, dict) else None,
        slides=slides,
        documentHtml=build_runtime_document_html(manifest, slides),
        presenterCapabilities={
            "navigation": True,
            "slideSync": True,
            "roomSync": False,
            "actions": False,
            "drilldowns": False,
        },
        exportCapabilities={
            "pdf": True,
            "pptxProjection": True,
            "printMode": True,
        },
    )
    return payload


def build_presentation_projection(
    manifest: HtmlRuntimeManifest,
    *,
    existing_slides: list[dict[str, Any]] | None = None,
) -> Presentation:
    existing_lookup = _build_existing_slide_lookup(existing_slides)
    slides: list[dict[str, Any]] = []
    for slide in manifest.slides:
        existing = existing_lookup.get(slide.slide_id)
        item = {
            "slideId": slide.slide_id,
            "layoutType": "blank",
            "layoutId": "blank",
            "contentData": {
                "title": slide.title,
                "_htmlDeck": True,
                "_htmlRuntime": True,
                "_htmlBody": slide.body_html,
            },
            "components": [],
        }
        if slide.speaker_notes:
            item["speakerNotes"] = slide.speaker_notes
        if isinstance(existing, dict) and isinstance(existing.get("speakerAudio"), dict):
            item["speakerAudio"] = existing["speakerAudio"]
        slides.append(item)
    return Presentation.model_validate(
        {
            "presentationId": "pres-html-runtime",
            "title": manifest.title,
            "slides": slides,
        }
    )


def lift_legacy_html_to_manifest(
    *,
    html: str,
    fallback_title: str,
    expected_slide_count: int | None = None,
    existing_slides: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raw_html = str(html or "").strip()
    if not raw_html:
        raise ValueError("HTML deck is empty.")
    title = _extract_title(raw_html) or fallback_title.strip() or "新演示文稿"
    custom_styles = "\n".join(
        block.strip() for block in _STYLE_RE.findall(raw_html) if str(block).strip()
    ).strip()
    existing_lookup = _build_existing_slide_lookup(existing_slides)
    raw_sections = list(_SECTION_RE.finditer(raw_html))
    if not raw_sections:
        raise ValueError("HTML deck must include at least one <section> slide.")
    if expected_slide_count is not None and len(raw_sections) != expected_slide_count:
        raise ValueError(
            f"HTML deck slide count mismatch: expected {expected_slide_count}, got {len(raw_sections)}."
        )
    slides: list[dict[str, Any]] = []
    for index, match in enumerate(raw_sections, start=1):
        attrs = match.group(1) or ""
        body = match.group(2) or ""
        slide_id = _extract_data_attr(attrs, "slide-id") or f"slide-{index}"
        slide_title = (
            _extract_data_attr(attrs, "slide-title")
            or _extract_heading(body)
            or f"第 {index} 页"
        )
        existing = existing_lookup.get(slide_id)
        speaker_notes = _extract_existing_speaker_notes(body) or _extract_slide_speaker_notes(existing)
        body_without_notes = _strip_existing_speaker_notes(body)
        slides.append(
            {
                "slideId": slide_id,
                "title": slide_title,
                "bodyHtml": body_without_notes,
                "speakerNotes": speaker_notes,
                "scopedCss": custom_styles or None,
            }
        )
    return {
        "version": "legacy-lifted",
        "title": title,
        "slides": slides,
    }


def sanitize_html_fragment(html: str) -> str:
    cleaned = str(html or "").strip()
    cleaned = _HTML_COMMENT_RE.sub("", cleaned)
    cleaned = _SCRIPT_TAG_RE.sub("", cleaned)
    cleaned = _IFRAME_TAG_RE.sub("", cleaned)
    cleaned = _STYLE_TAG_RE.sub("", cleaned)
    cleaned = _DOCUMENT_TAG_RE.sub("", cleaned)
    cleaned = _EVENT_ATTR_RE.sub("", cleaned)
    cleaned = _JAVASCRIPT_URL_RE.sub("", cleaned)
    return cleaned.strip()


def sanitize_scoped_css(css: str) -> str:
    cleaned = str(css or "").strip()
    if not cleaned:
        return ""
    cleaned = _IMPORT_RE.sub("", cleaned)
    cleaned = _EXPRESSION_RE.sub("(", cleaned)
    cleaned = _JAVASCRIPT_URL_RE.sub("", cleaned)
    return cleaned.strip()


def scope_slide_css(css: str, *, slide_id: str) -> str:
    cleaned = str(css or "").strip()
    if not cleaned:
        return ""
    root_selector = f'[data-runtime-slide-id="{_escape_attr(slide_id)}"]'
    scoped_blocks: list[str] = []
    for chunk in cleaned.split("}"):
        block = chunk.strip()
        if not block or "{" not in block:
            continue
        selector, body = block.split("{", 1)
        selector = selector.strip()
        body = body.strip()
        if not selector or not body:
            continue
        if selector.startswith("@"):
            scoped_blocks.append(f"{selector} {{{body}}}")
            continue
        selectors = []
        for item in selector.split(","):
            candidate = item.strip()
            if not candidate:
                continue
            if candidate in {"html", "body", ":root"}:
                selectors.append(root_selector)
            else:
                selectors.append(f"{root_selector} {candidate}")
        if selectors:
            scoped_blocks.append(f"{', '.join(selectors)} {{{body}}}")
    return "\n".join(scoped_blocks)


def build_runtime_document_html(
    manifest: HtmlRuntimeManifest,
    slides: list[HtmlRuntimeSlideRender],
) -> str:
    slide_nodes: list[str] = []
    for slide in slides:
        notes_attr = (
            f' data-speaker-notes="{_escape_attr(slide.speaker_notes or "")}"'
            if slide.speaker_notes
            else ""
        )
        style_tag = f"<style>{slide.css}</style>" if slide.css else ""
        slide_nodes.append(
            (
                f'<section class="runtime-slide" data-runtime-slide-id="{_escape_attr(slide.slide_id)}" '
                f'data-runtime-slide-title="{_escape_attr(slide.title)}" data-runtime-slide-index="{slide.index}"'
                f"{notes_attr}>"
                '<div class="runtime-slide-frame">'
                f'<div class="runtime-slide-surface">{style_tag}{slide.html}</div>'
                "</div>"
                "</section>"
            )
        )
    theme_json = json.dumps(manifest.theme or {}, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_escape_attr(manifest.title)}</title>
  <style>
    :root {{
      --runtime-bg: {_css_var(manifest.theme, 'backgroundColor', '#0f172a')};
      --runtime-fg: {_css_var(manifest.theme, 'primaryColor', '#f8fafc')};
      --runtime-accent: {_css_var(manifest.theme, 'secondaryColor', '#38bdf8')};
      --runtime-surface: rgba(255,255,255,0.06);
      --runtime-shadow: 0 32px 96px rgba(15, 23, 42, 0.35);
      --runtime-radius: 28px;
      --runtime-font: {_css_font(manifest.theme, 'fontFamily', '\"Noto Sans SC\", \"Microsoft YaHei\", sans-serif')};
      --runtime-heading-font: {_css_font(manifest.theme, 'headingFontFamily', '\"Noto Sans SC\", \"Microsoft YaHei\", sans-serif')};
    }}
    * {{ box-sizing: border-box; }}
    html, body {{
      width: 100%;
      height: 100%;
      margin: 0;
      background: var(--runtime-bg);
      color: var(--runtime-fg);
      font-family: var(--runtime-font);
      overflow: hidden;
    }}
    body[data-runtime-mode="print"] {{
      overflow: auto;
      background: #ffffff;
      color: #0f172a;
    }}
    .runtime-root {{
      width: 100%;
      height: 100%;
      position: relative;
      overflow: hidden;
      background:
        radial-gradient(circle at top, rgba(56,189,248,0.18), transparent 35%),
        linear-gradient(160deg, rgba(15,23,42,0.98), rgba(30,41,59,0.98));
    }}
    body[data-runtime-mode="thumbnail"] .runtime-root {{
      background: transparent;
    }}
    body[data-runtime-mode="print"] .runtime-root {{
      background: #ffffff;
      overflow: visible;
      padding: 24px 0;
    }}
    .runtime-slides {{
      width: 100%;
      height: 100%;
      position: relative;
    }}
    .runtime-slide {{
      display: none;
      width: 100%;
      height: 100%;
      padding: 24px;
    }}
    .runtime-slide.is-active {{
      display: block;
    }}
    .runtime-slide-frame {{
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .runtime-slide-surface {{
      width: min(100vw - 48px, calc((100vh - 48px) * 16 / 9));
      height: min(calc((100vw - 48px) * 9 / 16), 100vh - 48px);
      background: var(--runtime-surface);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: var(--runtime-radius);
      box-shadow: var(--runtime-shadow);
      overflow: hidden;
      position: relative;
      color: inherit;
      font-family: inherit;
    }}
    .runtime-slide-surface h1,
    .runtime-slide-surface h2,
    .runtime-slide-surface h3,
    .runtime-slide-surface h4,
    .runtime-slide-surface h5,
    .runtime-slide-surface h6 {{
      font-family: var(--runtime-heading-font);
    }}
    .runtime-controls {{
      position: absolute;
      right: 18px;
      bottom: 18px;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      border-radius: 999px;
      background: rgba(15, 23, 42, 0.65);
      color: #e2e8f0;
      border: 1px solid rgba(255,255,255,0.12);
      backdrop-filter: blur(12px);
      font-size: 12px;
      line-height: 1;
    }}
    .runtime-controls button {{
      border: 0;
      border-radius: 999px;
      background: rgba(255,255,255,0.12);
      color: inherit;
      width: 28px;
      height: 28px;
      cursor: pointer;
      font: inherit;
    }}
    .runtime-controls button:disabled {{
      opacity: 0.35;
      cursor: default;
    }}
    .runtime-progress {{
      min-width: 72px;
      text-align: center;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    body[data-runtime-mode="thumbnail"] .runtime-controls {{
      display: none;
    }}
    body[data-runtime-mode="print"] .runtime-slide {{
      display: block;
      height: auto;
      min-height: 100vh;
      padding: 0;
      break-after: page;
      page-break-after: always;
    }}
    body[data-runtime-mode="print"] .runtime-slide:last-child {{
      break-after: auto;
      page-break-after: auto;
    }}
    body[data-runtime-mode="print"] .runtime-slide-frame {{
      min-height: auto;
    }}
    body[data-runtime-mode="print"] .runtime-slide-surface {{
      width: 1280px;
      height: 720px;
      margin: 0 auto;
      background: #ffffff;
      color: #0f172a;
      border: none;
      box-shadow: none;
      border-radius: 0;
    }}
    body[data-runtime-mode="print"] .runtime-controls {{
      display: none;
    }}
  </style>
</head>
<body>
  <div class="runtime-root">
    <div class="runtime-slides">
      {''.join(slide_nodes)}
    </div>
    <div class="runtime-controls" aria-label="HTML runtime controls">
      <button type="button" data-runtime-nav="prev" aria-label="Previous slide">&lsaquo;</button>
      <div class="runtime-progress" data-runtime-progress>1 / {len(slides)}</div>
      <button type="button" data-runtime-nav="next" aria-label="Next slide">&rsaquo;</button>
    </div>
  </div>
  <script>
    (function() {{
      const theme = {theme_json};
      const params = new URLSearchParams(window.location.search);
      const mode = params.get("mode") || "interactive";
      const slides = Array.from(document.querySelectorAll(".runtime-slide"));
      let currentIndex = Number.parseInt(params.get("slide") || "0", 10);
      if (!Number.isFinite(currentIndex) || currentIndex < 0) currentIndex = 0;
      if (currentIndex >= slides.length) currentIndex = Math.max(0, slides.length - 1);
      document.body.dataset.runtimeMode = mode;
      document.documentElement.style.setProperty("--runtime-bg", theme.backgroundColor || "#0f172a");
      document.documentElement.style.setProperty("--runtime-fg", theme.primaryColor || "#f8fafc");
      document.documentElement.style.setProperty("--runtime-accent", theme.secondaryColor || "#38bdf8");
      if (theme.fontFamily) {{
        document.documentElement.style.setProperty("--runtime-font", theme.fontFamily);
      }}
      if (theme.headingFontFamily) {{
        document.documentElement.style.setProperty("--runtime-heading-font", theme.headingFontFamily);
      }}

      const progressNode = document.querySelector("[data-runtime-progress]");
      const prevButton = document.querySelector("[data-runtime-nav='prev']");
      const nextButton = document.querySelector("[data-runtime-nav='next']");

      function notifyParent() {{
        try {{
          window.parent.postMessage(
            {{
              type: "html-runtime-slidechange",
              slideIndex: currentIndex,
            }},
            window.location.origin
          );
        }} catch (error) {{
          void error;
        }}
      }}

      function update() {{
        slides.forEach((slide, index) => {{
          slide.classList.toggle("is-active", mode === "print" || index === currentIndex);
        }});
        if (progressNode) {{
          progressNode.textContent = `${{Math.max(1, currentIndex + 1)}} / ${{slides.length || 1}}`;
        }}
        if (prevButton) prevButton.disabled = currentIndex <= 0;
        if (nextButton) nextButton.disabled = currentIndex >= slides.length - 1;
        notifyParent();
      }}

      function goTo(nextIndex) {{
        if (mode === "print") return;
        const bounded = Math.max(0, Math.min(slides.length - 1, nextIndex));
        if (bounded === currentIndex) return;
        currentIndex = bounded;
        update();
      }}

      if (prevButton) {{
        prevButton.addEventListener("click", () => goTo(currentIndex - 1));
      }}
      if (nextButton) {{
        nextButton.addEventListener("click", () => goTo(currentIndex + 1));
      }}

      window.addEventListener("keydown", (event) => {{
        if (mode === "thumbnail" || mode === "print") return;
        if (event.key === "ArrowRight" || event.key === "PageDown" || event.key === " ") {{
          event.preventDefault();
          goTo(currentIndex + 1);
        }} else if (event.key === "ArrowLeft" || event.key === "PageUp") {{
          event.preventDefault();
          goTo(currentIndex - 1);
        }} else if (event.key === "Home") {{
          event.preventDefault();
          goTo(0);
        }} else if (event.key === "End") {{
          event.preventDefault();
          goTo(slides.length - 1);
        }}
      }});

      window.addEventListener("message", (event) => {{
        if (event.origin !== window.location.origin) return;
        const payload = event.data;
        if (!payload || typeof payload !== "object") return;
        if (payload.type !== "html-runtime-go-to-slide") return;
        const nextIndex = Number.parseInt(String(payload.slideIndex ?? "0"), 10);
        if (!Number.isFinite(nextIndex)) return;
        goTo(nextIndex);
      }});

      update();
    }})();
  </script>
</body>
</html>"""


def build_legacy_html_document(manifest: dict[str, Any]) -> str:
    title = str(manifest.get("title") or "新演示文稿").strip() or "新演示文稿"
    sections: list[str] = []
    raw_slides = manifest.get("slides")
    if isinstance(raw_slides, list):
        for index, slide in enumerate(raw_slides, start=1):
            if not isinstance(slide, dict):
                continue
            slide_id = str(slide.get("slideId") or f"slide-{index}")
            slide_title = str(slide.get("title") or f"第 {index} 页")
            body_html = str(slide.get("bodyHtml") or "")
            speaker_notes = str(slide.get("speakerNotes") or "").strip()
            notes_html = f'<aside class="notes">{speaker_notes}</aside>' if speaker_notes else ""
            sections.append(
                f'<section data-slide-id="{_escape_attr(slide_id)}" data-slide-title="{_escape_attr(slide_title)}">{body_html}{notes_html}</section>'
            )
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\" />"
        f"<title>{_escape_attr(title)}</title></head><body>{''.join(sections)}</body></html>"
    )


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


def _normalize_identifier(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip())
    normalized = normalized.strip("-_")
    return normalized


def _extract_slide_speaker_notes(slide: dict[str, Any] | None) -> str | None:
    if not isinstance(slide, dict):
        return None
    notes = str(slide.get("speakerNotes") or "").strip()
    return notes if notes else None


def _build_existing_slide_lookup(
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


def _escape_attr(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _css_var(theme: dict[str, Any] | None, key: str, fallback: str) -> str:
    if isinstance(theme, dict):
        value = str(theme.get(key) or "").strip()
        if value:
            return value
    return fallback


def _css_font(theme: dict[str, Any] | None, key: str, fallback: str) -> str:
    if isinstance(theme, dict):
        value = str(theme.get(key) or "").strip()
        if value:
            return value
    return fallback

"""Unified deterministic HTML renderer for presentation payloads.

Primary path reads layoutId + contentData.
Legacy components rendering remains as read-only compatibility.
"""

from __future__ import annotations

import re
from html import escape
from typing import Any

from app.services.export.layout_rules import (
    get_bullet_with_icons_columns,
    is_bullet_icons_only_compact,
)
from app.services.export.scene_background import (
    build_theme_root_css,
    render_scene_background_frame,
)
from app.services.fallback_semantics import (
    CONTENT_GENERATING,
    PENDING_SUPPLEMENT,
    STATUS_MESSAGE,
    STATUS_TITLE,
    are_all_placeholder_texts,
    canonicalize_fallback_text,
    get_bullet_fallback_status,
    is_placeholder_text,
)
from app.services.presentations.normalizer import normalize_metrics_slide_data
from app.services.image_semantics import infer_image_source


def render_presentation_html(presentation_dict: dict[str, Any]) -> str:
    slides = presentation_dict.get("slides", [])
    total = len(slides)
    theme_css = build_theme_root_css(
        presentation_dict.get("theme") if isinstance(presentation_dict.get("theme"), dict) else None
    )
    slides_html = "".join(
        _render_single_slide(slide, idx + 1, total) for idx, slide in enumerate(slides)
    )

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Noto Sans SC', 'Microsoft YaHei', 'PingFang SC', 'Helvetica Neue', sans-serif; background: var(--background-color,#ffffff); color: var(--background-text,#111827); }}
        {theme_css}
        .slide {{ margin: 0; }}
        .slide-shell {{ position: relative; width: 100%; height: 100%; background: var(--background-color,#ffffff); overflow: hidden; isolation: isolate; }}
        .slide-content {{ position: relative; z-index: 1; width: 100%; height: 100%; }}
        @page {{ size: landscape; margin: 0; }}
    </style>
</head>
<body>
    {slides_html}
</body>
</html>"""


def _render_single_slide(slide: dict[str, Any], page_num: int, total: int) -> str:
    layout_id = str(slide.get("layoutId") or slide.get("layoutType") or "").strip()
    content_data = slide.get("contentData")

    content_html = ""
    if layout_id and isinstance(content_data, dict):
        content_html = _render_content_data(layout_id, content_data)
    if not content_html:
        content_html = _render_components(slide.get("components", []))

    if not content_html:
        content_html = '<div style="padding:60px;color:#9ca3af;">Content unavailable</div>'

    content_html = render_scene_background_frame(slide.get("background"), content_html)

    page_number_html = (
        f'<div style="position:absolute;bottom:2%;right:3%;'
        f'font-size:10px;color:#9ca3af;">{page_num} / {total}</div>'
    )
    return f"""
    <div class="slide" style="position:relative;width:100%;aspect-ratio:16/9;background:var(--background-color,#ffffff);page-break-after:always;overflow:hidden;">
        {content_html}
        {page_number_html}
    </div>
    """


def _render_components(components: Any) -> str:
    if not isinstance(components, list):
        return ""

    blocks: list[str] = []
    for comp in components:
        if not isinstance(comp, dict):
            continue
        pos = comp.get("position", {}) if isinstance(comp.get("position"), dict) else {}
        style = comp.get("style", {}) if isinstance(comp.get("style"), dict) else {}

        css_parts = [
            "position: absolute",
            f"left: {pos.get('x', 0)}%",
            f"top: {pos.get('y', 0)}%",
            f"width: {pos.get('width', 50)}%",
            f"height: {pos.get('height', 20)}%",
            "overflow: hidden",
        ]
        if style.get("fontSize"):
            css_parts.append(f"font-size: {style['fontSize']}px")
        if style.get("fontWeight"):
            css_parts.append(f"font-weight: {style['fontWeight']}")
        if style.get("color"):
            css_parts.append(f"color: {style['color']}")
        if style.get("textAlign"):
            css_parts.append(f"text-align: {style['textAlign']}")

        content = str(comp.get("content", ""))
        comp_type = str(comp.get("type", "text"))
        if comp_type == "text":
            content_html = _render_text_block(content)
        elif comp_type in ("image", "chart"):
            content_html = (
                '<div style="display:flex;align-items:center;justify-content:center;'
                'height:100%;background:#f3f4f6;border-radius:4px;color:#9ca3af;font-size:14px;">'
                f"[{escape(comp_type)}: {escape(content or '占位')}]</div>"
            )
        else:
            content_html = escape(content)

        css = "; ".join(css_parts)
        blocks.append(f'<div style="{css}">{content_html}</div>')
    return "\n".join(blocks)



OUTLINE_FALLBACK_TITLES = ("Background", "Analysis", "Solution", "Conclusion", "Implementation", "Summary")
MAX_OUTLINE_SECTIONS = 10
OUTLINE_RAIL_SINGLE_COLUMN_MAX = 3


def _normalize_outline_sections(raw: Any, *, min_sections: int = 4) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        raw = []

    sections: list[dict[str, str]] = []
    for index, item in enumerate(raw):
        title = ""
        description = ""
        if isinstance(item, str):
            title = item.strip()
        elif isinstance(item, dict):
            title = (
                _as_text(item.get("title"))
                or _as_text(item.get("text"))
                or _as_text(item.get("label"))
                or _as_text(item.get("heading"))
                or _as_text(item.get("name"))
            )
            description = (
                _as_text(item.get("description"))
                or _as_text(item.get("summary"))
                or _as_text(item.get("detail"))
            )

        if not title and not description:
            continue

        fallback_title = (
            OUTLINE_FALLBACK_TITLES[index]
            if index < len(OUTLINE_FALLBACK_TITLES)
            else f"Section {index + 1}"
        )
        section = {"title": title or fallback_title}
        if description:
            section["description"] = description
        sections.append(section)

    sections = sections[:MAX_OUTLINE_SECTIONS]
    while len(sections) < min_sections:
        sections.append({"title": OUTLINE_FALLBACK_TITLES[len(sections)]})
    return sections


def _split_outline_sections(sections: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    midpoint = (len(sections) + 1) // 2
    return sections[:midpoint], sections[midpoint:]


def _split_outline_rail_sections(
    sections: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if len(sections) <= OUTLINE_RAIL_SINGLE_COLUMN_MAX:
        return sections, []
    return _split_outline_sections(sections)


def _render_outline_column(column: list[dict[str, str]], start_index: int) -> str:
    if not column:
        return ""

    articles = []
    for offset, section in enumerate(column):
        index = start_index + offset + 1
        title = escape(section.get("title", f"Section {index}"))
        description = escape(section.get("description", ""))
        description_html = (
            f'<p style="font-size:15px;line-height:1.6;color:color-mix(in srgb, var(--background-text,#111827) 58%, transparent);margin:12px 0 0;max-width:420px;">{description}</p>'
            if description
            else ""
        )
        articles.append(
            '<article style="border-top:1px solid #dbe2ea;padding-top:18px;display:flex;gap:20px;">'
            '<div style="width:48px;flex-shrink:0;padding-top:4px;">'
            f'<div style="font-size:13px;font-weight:700;letter-spacing:0.18em;color:var(--primary-color,#3b82f6);">{index:02d}</div>'
            '</div>'
            '<div style="min-width:0;">'
            f'<h3 style="font-size:28px;font-weight:600;line-height:1.05;color:var(--background-text,#111827);margin:0;letter-spacing:-0.04em;">{title}</h3>'
            f'{description_html}'
            '</div>'
            '</article>'
        )

    return (
        f'<div style="flex:1;display:grid;grid-template-rows:repeat({len(column)},minmax(0,1fr));gap:24px;min-height:0;">'
        f'{"".join(articles)}'
        '</div>'
    )


def _render_outline_rail_column(
    column: list[dict[str, str]],
    start_index: int,
    *,
    dense: bool,
) -> str:
    if not column:
        return ""

    articles = []
    for offset, section in enumerate(column):
        index = start_index + offset + 1
        title = escape(section.get("title", f"Section {index}"))
        description = escape(section.get("description", ""))
        title_size = 20 if dense else 23
        description_size = 13 if dense else 14
        padding = "12px 16px" if dense else "16px 20px"
        description_html = (
            f'<p style="font-size:{description_size}px;line-height:1.6;color:#475569;margin:8px 0 0;">{description}</p>'
            if description
            else ""
        )
        articles.append(
            '<article style="position:relative;display:flex;gap:20px;min-height:0;">'
            '<div style="position:relative;z-index:1;display:flex;height:44px;width:44px;flex-shrink:0;align-items:center;justify-content:center;border-radius:9999px;background:var(--primary-color,#3b82f6);font-size:14px;font-weight:700;color:#ffffff;box-shadow:0 1px 2px rgba(15,23,42,0.12);">'
            f"{index:02d}"
            '</div>'
            f'<div style="min-width:0;border:1px solid #f1f5f9;border-radius:16px;background:#f8fafc;padding:{padding};">'
            f'<h3 style="font-size:{title_size}px;font-weight:700;line-height:1.2;color:var(--background-text,#111827);margin:0;">{title}</h3>'
            f"{description_html}"
            '</div>'
            '</article>'
        )

    return (
        f'<div style="position:relative;display:grid;grid-template-rows:repeat({len(column)},minmax(0,1fr));gap:20px;min-height:0;">'
        '<div style="position:absolute;left:22px;top:12px;bottom:12px;width:1px;background:#e2e8f0;"></div>'
        f'{"".join(articles)}'
        '</div>'
    )

def _render_content_data(layout_id: str, data: dict[str, Any]) -> str:
    d = data
    if layout_id in {"intro-slide", "intro-slide-left"}:
        author = _as_text(d.get("author")) or _as_text(d.get("presenter"))
        date = _as_text(d.get("date"))
        info_parts = [part for part in (author, date) if part]
        return (
            '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;padding:0 80px;text-align:center;">'
            f'<h1 style="font-size:52px;font-weight:700;line-height:1.2;color:var(--background-text,#111827);margin:0 0 16px;max-width:900px;">{escape(_as_text(d.get("title")))}</h1>'
            f'{_optional_paragraph(_as_text(d.get("subtitle")), "font-size:24px;line-height:1.5;color:color-mix(in srgb, var(--background-text,#111827) 60%, transparent);margin:0 0 40px;max-width:700px;")}'
            f'{_optional_paragraph(" / ".join(info_parts), "font-size:16px;line-height:1.5;color:color-mix(in srgb, var(--background-text,#111827) 40%, transparent);")}'
            "</div>"
        )

    if layout_id in {"section-header", "section-header-side"}:
        return (
            '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;padding:0 96px;text-align:center;">'
            '<div style="width:48px;height:4px;border-radius:9999px;background:var(--primary-color,#3b82f6);margin-bottom:32px;"></div>'
            f'<h2 style="font-size:44px;font-weight:700;line-height:1.3;color:var(--background-text,#111827);margin:0 0 16px;max-width:800px;">{escape(_as_text(d.get("title")))}</h2>'
            f'{_optional_paragraph(_as_text(d.get("subtitle")), "font-size:20px;line-height:1.5;color:color-mix(in srgb, var(--background-text,#111827) 50%, transparent);margin:0;max-width:600px;")}'
            "</div>"
        )

    if layout_id == "outline-slide":
        sections = _normalize_outline_sections(
            d.get("sections") if isinstance(d.get("sections"), list) else d.get("items"),
            min_sections=4,
        )
        left, right = _split_outline_sections(sections)
        subtitle = _as_text(d.get("subtitle"))
        return (
            '<div style="padding:56px 64px;height:100%;display:flex;flex-direction:column;">'
            '<div style="display:flex;align-items:flex-end;gap:40px;">'
            '<div style="max-width:560px;">'
            '<div style="width:64px;height:6px;border-radius:9999px;background:var(--primary-color,#3b82f6);margin-bottom:20px;"></div>'
            f'<h2 style="font-size:42px;font-weight:700;line-height:1.12;letter-spacing:-0.045em;color:var(--background-text,#111827);margin:0 0 16px;">{escape(_as_text(d.get("title"), "Outline"))}</h2>'
            f'{_optional_paragraph(subtitle, "font-size:17px;line-height:1.6;color:color-mix(in srgb, var(--background-text,#111827) 60%, transparent);margin:0;max-width:520px;")}'
            '</div>'
            '<div style="height:1px;flex:1;background:color-mix(in srgb, var(--background-text,#111827) 12%, transparent);margin-bottom:12px;"></div>'
            '</div>'
            '<div style="display:flex;gap:56px;flex:1;margin-top:48px;">'
            f'{_render_outline_column(left, 0)}'
            f'{_render_outline_column(right, len(left))}'
            '</div>'
            '</div>'
        )

    if layout_id == "outline-slide-rail":
        sections = _normalize_outline_sections(
            d.get("sections") if isinstance(d.get("sections"), list) else d.get("items"),
            min_sections=1,
        )
        left, right = _split_outline_rail_sections(sections)
        subtitle = _as_text(d.get("subtitle"))
        is_multi_column = bool(right)
        layout_style = "display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;height:100%;min-height:0;"
        return (
            '<div style="display:flex;height:100%;padding:56px 64px;background:linear-gradient(160deg,var(--slide-bg-start,#ffffff) 0%,var(--slide-bg-end,#f8fafc) 100%);color:var(--background-text,#111827);">'
            '<div style="display:flex;width:100%;gap:48px;">'
            '<section style="width:38%;flex-shrink:0;">'
            '<div style="margin-bottom:20px;font-size:12px;font-weight:600;letter-spacing:0.2em;text-transform:uppercase;color:var(--primary-color,#3b82f6);">Chapter Rail</div>'
            f'<h2 style="font-size:42px;font-weight:800;line-height:1.08;letter-spacing:-0.05em;color:var(--background-text,#111827);margin:0;">{escape(_as_text(d.get("title"), "Outline"))}</h2>'
            f'{_optional_paragraph(subtitle, "font-size:17px;line-height:1.65;color:#475569;margin:20px 0 0;")}'
            '</section>'
            '<section style="flex:1;border:1px solid #e2e8f0;border-radius:32px;background:#ffffff;padding:32px;box-shadow:0 1px 3px rgba(15,23,42,0.08);">'
            f'<div style="{"height:100%;min-height:0;" if not is_multi_column else layout_style}">'
            f'{_render_outline_rail_column(left, 0, dense=is_multi_column)}'
            f'{_render_outline_rail_column(right, len(left), dense=is_multi_column) if is_multi_column else ""}'
            '</div>'
            '</section>'
            '</div>'
            '</div>'
        )

    if layout_id in {"bullet-with-icons", "bullet-with-icons-cards"}:
        items_source = d.get("items")
        if not isinstance(items_source, list):
            items_source = d.get("features", [])
        items = items_source if isinstance(items_source, list) else []
        status = _bullet_status(d, items)
        if status is not None and len(items) == 0:
            return _render_bullet_status_panel(_as_text(d.get("title")), status)
        if status is not None and _placeholder_only_bullet_items(items):
            return _render_bullet_status_panel(_as_text(d.get("title")), status)

        col_count = get_bullet_with_icons_columns(len(items))
        compact = col_count == 4
        cards: list[str] = []
        for idx, item in enumerate(items):
            title = escape(_item_text(item))
            detail = escape(_item_detail(item))
            icon_query = _item_icon_query(item)
            cards.append(
                '<div style="position:relative;display:flex;flex-direction:column;height:100%;min-height:0;padding-left:16px;">'
                f'<div style="position:absolute;left:0;top:50%;transform:translateY(-50%);width:1px;height:{"46%" if compact else "50%"};background-color:rgba(17,24,39,0.12);"></div>'
                '<div style="display:flex;flex-direction:column;justify-content:center;flex:1;min-height:0;padding:8px 0;">'
                f'<div style="display:flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:9999px;background:rgba(59,130,246,0.12);margin-bottom:16px;flex-shrink:0;">{_icon_token_svg(icon_query, 20)}</div>'
                f'<h3 style="font-size:{19 if compact else 21}px;font-weight:700;line-height:1.08;letter-spacing:-0.04em;color:#3b82f6;margin:0 0 8px;min-width:0;">'
                '<span style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">'
                f'<span style="background:rgba(59,130,246,0.08);border-radius:3px;padding:{"0.04em 0.2em 0.1em" if compact else "0.05em 0.22em 0.12em"};box-decoration-break:clone;-webkit-box-decoration-break:clone;">{title}</span>'
                "</span></h3>"
                f'{_optional_paragraph(detail, f"font-size:{11.5 if compact else 12.5}px;line-height:1.42;color:rgba(17,24,39,0.72);margin:0;max-width:240px;")}'
                f'<div style="padding-top:16px;font-size:{52 if compact else 60}px;font-weight:400;line-height:0.92;letter-spacing:-0.06em;color:#111827;">{idx + 1:02d}</div>'
                "</div></div>"
            )
        return (
            '<div style="padding:56px 64px;height:100%;display:flex;flex-direction:column;">'
            f'<h2 style="font-size:36px;font-weight:700;line-height:1.3;color:#111827;margin:0 0 40px;">{escape(_as_text(d.get("title")))}</h2>'
            f'<div style="display:grid;grid-template-columns:repeat({col_count},1fr);column-gap:{18 if compact else 26}px;flex:1;min-height:0;">'
            f'{"".join(cards)}'
            "</div></div>"
        )

    if layout_id == "bullet-icons-only":
        items_source = d.get("items")
        if not isinstance(items_source, list):
            items_source = d.get("features", [])
        items = items_source if isinstance(items_source, list) else []
        compact = is_bullet_icons_only_compact(len(items))
        cards: list[str] = []
        for idx, item in enumerate(items):
            title = escape(_item_text(item))
            icon_query = _item_icon_query(item)
            cards.append(
                '<div style="position:relative;display:flex;align-items:center;min-height:92px;overflow:hidden;border-radius:28px;'
                'background:color-mix(in srgb, #111827 3%, white);padding:20px 24px;">'
                '<div style="position:absolute;left:28px;top:50%;width:96px;height:48px;border-radius:16px;'
                'background:rgba(59,130,246,0.16);transform:translateY(-50%) skewX(-22deg);"></div>'
                '<div style="position:relative;z-index:1;width:72px;height:72px;border-radius:22px;'
                'border:1px solid rgba(59,130,246,0.16);background:#ffffff;box-shadow:0 12px 32px rgba(15,23,42,0.08);'
                f'display:flex;align-items:center;justify-content:center;color:#3b82f6;flex-shrink:0;">{_icon_token_svg(icon_query, 40)}</div>'
                '<div style="position:relative;z-index:1;min-width:0;margin-left:24px;">'
                f'<div style="font-size:12px;font-weight:700;letter-spacing:0.24em;line-height:1;color:#6b7280;margin-bottom:8px;">{idx + 1:02d}</div>'
                f'<div style="font-size:{21 if compact else 24}px;font-weight:700;line-height:1.08;letter-spacing:-0.04em;color:#111827;">{title}</div>'
                "</div>"
                "</div>"
            )
        return (
            '<div style="padding:56px 64px;height:100%;display:flex;flex-direction:column;">'
            f'<h2 style="font-size:36px;font-weight:bold;line-height:1.3;margin-bottom:32px;">{escape(_as_text(d.get("title")))}</h2>'
            f'<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:{28 if compact else 40}px;row-gap:{18 if compact else 22}px;align-content:center;flex:1;min-height:0;">'
            f'{"".join(cards)}'
            "</div></div>"
        )

    if layout_id in {"numbered-bullets", "numbered-bullets-track"}:
        steps = d.get("items") if isinstance(d.get("items"), list) else d.get("steps", [])
        lines: list[str] = []
        for idx, item in enumerate(steps if isinstance(steps, list) else []):
            title = _item_text(item)
            desc = _item_detail(item)
            lines.append(
                '<div style="display:flex;gap:20px;align-items:flex-start;">'
                f'<span style="font-size:28px;font-weight:bold;color:#3b82f6;min-width:40px;">{idx + 1}</span>'
                "<div>"
                f'<p style="font-size:22px;font-weight:600;">{escape(title)}</p>'
                f'{_optional_paragraph(desc, "font-size:16px;color:#6b7280;margin-top:4px;")}'
                "</div></div>"
            )
        return (
            '<div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">'
            f'<h2 style="font-size:40px;font-weight:bold;margin-bottom:40px;">{escape(_as_text(d.get("title")))}</h2>'
            '<div style="display:flex;flex-direction:column;gap:24px;">'
            f"{''.join(lines)}"
            "</div></div>"
        )

    if layout_id in {"metrics-slide", "metrics-slide-band"}:
        normalized = normalize_metrics_slide_data(d)
        if normalized is None:
            return ""

        metrics = normalized.get("metrics")
        metrics = metrics if isinstance(metrics, list) else []
        conclusion = _as_text(normalized.get("conclusion"))
        conclusion_brief = _as_text(normalized.get("conclusionBrief"))
        has_executive_summary = bool(conclusion or conclusion_brief)
        cols = min(max(len(metrics), 1), 4)
        if not has_executive_summary:
            card_html = "".join(
                (
                    '<div style="text-align:center;padding:24px;">'
                    f'<p style="font-size:48px;font-weight:bold;color:#3b82f6;">{escape(_as_text(m.get("value")) if isinstance(m, dict) else _as_text(m))}</p>'
                    f'<p style="font-size:20px;font-weight:600;margin-top:12px;">{escape(_as_text(m.get("label")) if isinstance(m, dict) else "")}</p>'
                    f'{_optional_paragraph(_as_text(m.get("description")) if isinstance(m, dict) else "", "font-size:15px;color:#6b7280;margin-top:8px;")}'
                    "</div>"
                )
                for m in metrics
            )
            return (
                '<div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">'
                f'<h2 style="font-size:40px;font-weight:bold;margin-bottom:48px;">{escape(_as_text(normalized.get("title")))}</h2>'
                f'<div style="display:grid;grid-template-columns:repeat({cols},1fr);gap:40px;flex:1;align-items:center;">{card_html}</div>'
                "</div>"
            )

        conclusion_html = (
            f'<p style="font-size:32px;font-weight:700;line-height:1.2;color:#111827;">{escape(conclusion)}</p>'
            if conclusion
            else ""
        )
        brief_margin = "16px" if conclusion else "0"
        brief_html = (
            f'<p style="font-size:17px;line-height:1.6;color:#4b5563;margin-top:{brief_margin};max-width:960px;">{escape(conclusion_brief)}</p>'
            if conclusion_brief
            else ""
        )
        executive_card_html = "".join(
            (
                '<div style="display:flex;flex-direction:column;min-height:168px;padding:20px 24px;border-radius:16px;background:rgba(59,130,246,0.05);">'
                f'<p style="font-size:40px;font-weight:800;line-height:1.1;color:#3b82f6;">{escape(_as_text(m.get("value")) if isinstance(m, dict) else _as_text(m))}</p>'
                f'<p style="font-size:17px;font-weight:600;line-height:1.35;color:#111827;margin-top:8px;">{escape(_as_text(m.get("label")) if isinstance(m, dict) else "")}</p>'
                f'{_optional_paragraph(_as_text(m.get("description")) if isinstance(m, dict) else "", "font-size:13px;color:#6b7280;margin-top:4px;")}'
                "</div>"
            )
            for m in metrics
        )
        return (
            '<div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">'
            f'<h2 style="font-size:40px;font-weight:bold;margin-bottom:24px;">{escape(_as_text(normalized.get("title")))}</h2>'
            '<div style="margin-bottom:32px;border-radius:28px;border:1px solid rgba(59,130,246,0.15);background:linear-gradient(135deg,rgba(59,130,246,0.10),rgba(255,255,255,0.92));padding:32px 40px;">'
            f'{conclusion_html}{brief_html}'
            '</div>'
            f'<div style="display:grid;grid-template-columns:repeat({cols},1fr);gap:24px;flex:1;align-items:stretch;">{executive_card_html}</div>'
            '</div>'
        )

    if layout_id == "metrics-with-image":
        metrics = d.get("metrics")
        metrics = metrics if isinstance(metrics, list) else []
        image = d.get("image")
        image = image if isinstance(image, dict) else {}
        url = _sanitize_image_src(image.get("url"))
        alt = _as_text(image.get("alt")) or _as_text(image.get("prompt")) or "Image"
        if url:
            image_html = _render_image_fill(url, alt)
        else:
            title, detail = _get_image_placeholder_copy(image)
            image_html = _render_image_placeholder(title, detail)
        metric_html = "".join(
            (
                '<div style="margin-bottom:20px;">'
                f'<span style="font-size:36px;font-weight:bold;color:#3b82f6;">{escape(_as_text(m.get("value")) if isinstance(m, dict) else _as_text(m))}</span>'
                f'<span style="font-size:18px;color:#6b7280;margin-left:12px;">{escape(_as_text(m.get("label")) if isinstance(m, dict) else "")}</span>'
                "</div>"
            )
            for m in metrics
        )
        return (
            '<div style="display:grid;grid-template-columns:1fr 1fr;height:100%;">'
            '<div style="padding:60px;display:flex;flex-direction:column;justify-content:center;">'
            f'<h2 style="font-size:36px;font-weight:bold;margin-bottom:32px;">{escape(_as_text(d.get("title")))}</h2>'
            f"{metric_html}"
            '</div>'
            f'<div style="background:#f3f4f6;overflow:hidden;">{image_html}</div>'
            "</div>"
        )

    if layout_id == "chart-with-bullets":
        bullets = d.get("bullets")
        bullets = bullets if isinstance(bullets, list) else []
        bullet_html = "".join(
            f'<p style="font-size:20px;">• {escape(_item_text(b))}</p>' for b in bullets
        )
        return (
            '<div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">'
            f'<h2 style="font-size:40px;font-weight:bold;margin-bottom:32px;">{escape(_as_text(d.get("title")))}</h2>'
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:40px;flex:1;">'
            '<div style="background:#f9fafb;border:1px dashed #d1d5db;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#9ca3af;">[图表]</div>'
            f'<div style="display:flex;flex-direction:column;justify-content:center;gap:16px;">{bullet_html}</div>'
            "</div></div>"
        )

    if layout_id == "table-info":
        headers = _table_headers(d)
        rows = _table_rows(d, headers)
        if not headers or not rows:
            return ""
        head_html = "".join(
            f'<th style="text-align:left;padding:12px 16px;border-bottom:2px solid #3b82f6;font-weight:600;">{escape(header)}</th>'
            for header in headers
        )
        row_html = "".join(
            "<tr>"
            + "".join(
                f'<td style="padding:12px 16px;border-bottom:1px solid #e5e7eb;">{escape(cell)}</td>'
                for cell in row
            )
            + "</tr>"
            for row in rows
        )
        caption_html = _optional_paragraph(_as_text(d.get("caption")), "font-size:14px;color:#6b7280;margin-top:10px;")
        return (
            '<div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">'
            f'<h2 style="font-size:40px;font-weight:bold;margin-bottom:32px;">{escape(_as_text(d.get("title")))}</h2>'
            '<table style="width:100%;border-collapse:collapse;font-size:18px;">'
            f"<thead><tr>{head_html}</tr></thead><tbody>{row_html}</tbody></table>"
            f"{caption_html}"
            "</div>"
        )

    if layout_id == "two-column-compare":
        left, right = _compare_columns(d)
        return (
            '<div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">'
            f'<h2 style="font-size:40px;font-weight:bold;margin-bottom:32px;">{escape(_as_text(d.get("title"), "对比分析"))}</h2>'
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:48px;flex:1;">'
            f"{_render_compare_column(left)}"
            f"{_render_compare_column(right)}"
            "</div></div>"
        )

    if layout_id == "image-and-description":
        image = d.get("image")
        image = image if isinstance(image, dict) else {}
        url = _sanitize_image_src(image.get("url"))
        alt = _as_text(image.get("alt")) or _as_text(image.get("prompt")) or "Image"
        if url:
            image_html = _render_image_fill(url, alt)
        else:
            title, detail = _get_image_placeholder_copy(image)
            image_html = _render_image_placeholder(title, detail)
        bullets = d.get("bullets")
        bullets = bullets if isinstance(bullets, list) else []
        bullets_html = "".join(
            f'<p style="font-size:16px;color:#6b7280;margin-top:6px;">• {escape(_as_text(item))}</p>'
            for item in bullets
            if _as_text(item)
        )
        return (
            '<div style="display:grid;grid-template-columns:1fr 1fr;height:100%;">'
            f'<div style="background:#f3f4f6;overflow:hidden;">{image_html}</div>'
            '<div style="padding:60px;display:flex;flex-direction:column;justify-content:center;">'
            f'<h2 style="font-size:36px;font-weight:bold;margin-bottom:20px;">{escape(_as_text(d.get("title")))}</h2>'
            f'<p style="font-size:20px;color:#4b5563;line-height:1.6;">{escape(_as_text(d.get("description")))}</p>'
            f"{bullets_html}"
            "</div></div>"
        )

    if layout_id == "timeline":
        events = d.get("events")
        if not isinstance(events, list):
            events = d.get("items", [])
        events = events if isinstance(events, list) else []
        item_html = "".join(
            (
                '<div style="flex:1;text-align:center;padding:20px;">'
                f'<p style="font-size:16px;color:#3b82f6;font-weight:600;">{escape(_as_text(evt.get("date")) if isinstance(evt, dict) else "")}</p>'
                f'<p style="font-size:20px;font-weight:600;margin-top:8px;">{escape(_item_text(evt))}</p>'
                f'{_optional_paragraph(_item_detail(evt), "font-size:15px;color:#6b7280;margin-top:4px;")}'
                "</div>"
            )
            for evt in events
        )
        return (
            '<div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">'
            f'<h2 style="font-size:40px;font-weight:bold;margin-bottom:40px;">{escape(_as_text(d.get("title")))}</h2>'
            f'<div style="display:flex;gap:32px;flex:1;align-items:center;">{item_html}</div>'
            "</div>"
        )

    if layout_id in {"quote-slide", "quote-banner"}:
        author = _as_text(d.get("author")) or _as_text(d.get("attribution"))
        context = _as_text(d.get("context"))
        meta = " / ".join(part for part in (author, context) if part)
        meta_html = (
            '<div style="display:flex;align-items:center;gap:12px;">'
            '<div style="width:32px;height:2px;background:color-mix(in srgb, var(--primary-color,#3b82f6) 30%, transparent);"></div>'
            f'<span style="font-size:16px;line-height:1.5;color:color-mix(in srgb, var(--background-text,#111827) 50%, transparent);">{escape(meta)}</span>'
            '</div>'
            if meta
            else ""
        )
        return (
            '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;padding:0 96px;text-align:center;">'
            '<div style="font-size:80px;line-height:1;color:color-mix(in srgb, var(--primary-color,#3b82f6) 20%, transparent);margin-bottom:8px;">&ldquo;</div>'
            f'<blockquote style="font-size:30px;font-weight:500;line-height:1.6;color:var(--background-text,#111827);text-align:center;max-width:850px;margin:0 0 24px;">{escape(_as_text(d.get("quote")))}</blockquote>'
            f"{meta_html}"
            "</div>"
        )

    if layout_id == "challenge-outcome":
        pairs = _challenge_outcome_pairs(d)
        rows_html = "".join(
            (
                '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">'
                f'<div style="background:#fef2f2;border-radius:10px;padding:14px 16px;color:#b91c1c;">{escape(pair["challenge"])}</div>'
                f'<div style="background:#f0fdf4;border-radius:10px;padding:14px 16px;color:#15803d;">{escape(pair["outcome"])}</div>'
                "</div>"
            )
            for pair in pairs
        )
        return (
            '<div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">'
            f'<h2 style="font-size:40px;font-weight:bold;margin-bottom:24px;">{escape(_as_text(d.get("title"), "问题与方案"))}</h2>'
            f'<div style="display:flex;flex-direction:column;gap:14px;">{rows_html}</div>'
            "</div>"
        )

    if layout_id in {"thank-you", "thank-you-contact"}:
        contact = _as_text(d.get("contact")) or _as_text(d.get("contact_info"))
        return (
            '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;padding:0 96px;text-align:center;">'
            '<div style="width:64px;height:4px;border-radius:9999px;background:var(--primary-color,#3b82f6);margin-bottom:40px;"></div>'
            f'<h1 style="font-size:56px;font-weight:800;line-height:1.2;color:var(--background-text,#111827);margin:0 0 24px;">{escape(_as_text(d.get("title"), "Thanks"))}</h1>'
            f'{_optional_paragraph(_as_text(d.get("subtitle")), "font-size:22px;line-height:1.5;color:color-mix(in srgb, var(--background-text,#111827) 50%, transparent);margin:0 0 16px;max-width:600px;")}'
            f'{_optional_paragraph(contact, "font-size:16px;line-height:1.5;color:var(--primary-color,#3b82f6);margin:0;")}'
            "</div>"
        )

    title = _as_text(d.get("title"), f"[{layout_id}]")
    return f'<div style="padding:60px;"><h2 style="font-size:36px;">{escape(title)}</h2></div>'


def _optional_paragraph(text: str, style: str) -> str:
    if not text:
        return ""
    return f'<p style="{style}">{escape(text)}</p>'


def _render_text_block(content: str) -> str:
    if not content:
        return ""
    lines = content.split("\n")
    html_parts = []
    for line in lines:
        line = line.strip()
        if not line:
            html_parts.append("<br>")
            continue
        bullet_match = re.match(r"^[•\\-*]\\s+(.*)", line)
        if bullet_match:
            html_parts.append(f'<div style="padding-left:1.5em;">• {escape(bullet_match.group(1))}</div>')
            continue
        ordered_match = re.match(r"^(\\d+)[.)]\\s+(.*)", line)
        if ordered_match:
            html_parts.append(
                f'<div style="padding-left:1.5em;">{ordered_match.group(1)}. {escape(ordered_match.group(2))}</div>'
            )
            continue
        html_parts.append(f"<div>{escape(line)}</div>")
    return "\n".join(html_parts)


def _as_text(value: Any, default: str = "") -> str:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    if isinstance(value, (int, float, bool)):
        return str(value)
    return default


_IMAGE_SRC_ALLOWED_RE = re.compile(r"^https?://", re.IGNORECASE)
_IMAGE_DATA_URL_ALLOWED_RE = re.compile(
    r"^data:image/(png|jpeg|jpg|webp|gif);base64,",
    re.IGNORECASE,
)


def _sanitize_image_src(value: Any) -> str:
    url = _as_text(value)
    if not url:
        return ""
    if _IMAGE_SRC_ALLOWED_RE.match(url) or _IMAGE_DATA_URL_ALLOWED_RE.match(url):
        return url
    return ""


def _get_image_placeholder_copy(image: Any) -> tuple[str, str]:
    if not isinstance(image, dict):
        return ("待用户补图/上传", "")

    source = infer_image_source(image)
    prompt = _as_text(image.get("prompt"))

    if source == "ai":
        return (prompt or "AI 图片待生成", "")
    if source == "user":
        return ("待用户补图/上传", prompt)
    return ("待绑定现有素材", prompt)


def _render_image_placeholder(title: str, detail: str = "") -> str:
    title_html = escape(title) if title else "图片不可用"
    detail_html = escape(detail) if detail else ""
    detail_block = (
        f'<div style="margin-top:8px;font-size:12px;line-height:1.4;opacity:0.75;text-align:center;padding:0 24px;">{detail_html}</div>'
        if detail_html
        else ""
    )
    return (
        '<div style="height:100%;width:100%;background:#f3f4f6;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#9ca3af;overflow:hidden;">'
        f'<div style="font-size:13px;font-weight:600;opacity:0.85;text-align:center;padding:0 24px;">{title_html}</div>'
        f"{detail_block}"
        "</div>"
    )


def _render_image_fill(url: str, alt: str) -> str:
    # Match the frontend preview baseline: fill the container with cover cropping.
    return (
        f'<img src="{escape(url)}" alt="{escape(alt)}" '
        'style="width:100%;height:100%;object-fit:cover;display:block;" />'
    )


def _item_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return (
            _as_text(item.get("text"))
            or _as_text(item.get("title"))
            or _as_text(item.get("label"))
            or _as_text(item.get("challenge"))
            or _as_text(item.get("outcome"))
        )
    return ""


def _item_detail(item: Any) -> str:
    if isinstance(item, dict):
        return _as_text(item.get("description"))
    return ""


def _item_icon_query(item: Any) -> str:
    if isinstance(item, dict):
        icon = item.get("icon")
        if isinstance(icon, dict):
            query = _as_text(icon.get("query"))
            if query:
                return query
    return _item_text(item)


def _icon_token(query: str) -> str:
    cleaned = "".join(ch for ch in query if ch.isalnum())
    if not cleaned:
        return "IC"
    return cleaned[:2].upper()


def _icon_token_svg(query: str, size: int) -> str:
    token = escape(_icon_token(query))
    half = size / 2
    font_size = round(size * 0.34, 1)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}" aria-hidden="true">'
        f'<circle cx="{half}" cy="{half}" r="{half - 2}" fill="#EFF6FF" stroke="#BFDBFE" stroke-width="2"></circle>'
        f'<text x="50%" y="54%" text-anchor="middle" dominant-baseline="middle" '
        f'font-family="Arial, sans-serif" font-size="{font_size}" font-weight="700" fill="#2563EB">{token}</text>'
        "</svg>"
    )


def _bullet_card(item: Any) -> str:
    title = _item_text(item)
    detail = _item_detail(item)
    return (
        '<div style="padding:24px;">'
        f'<p style="font-size:22px;font-weight:600;margin-bottom:8px;">{escape(title)}</p>'
        f'{_optional_paragraph(detail, "font-size:16px;color:#6b7280;")}'
        "</div>"
    )


def _table_headers(data: dict[str, Any]) -> list[str]:
    raw = data.get("headers")
    if not isinstance(raw, list):
        raw = data.get("columns")
    if not isinstance(raw, list):
        return []
    return [_as_text(header) for header in raw if _as_text(header)]


def _table_rows(data: dict[str, Any], headers: list[str]) -> list[list[str]]:
    raw = data.get("rows")
    if not isinstance(raw, list):
        return []
    rows: list[list[str]] = []
    for row in raw:
        if isinstance(row, list):
            cells = [_as_text(cell) for cell in row]
            if len(cells) < len(headers):
                cells.extend([""] * (len(headers) - len(cells)))
            rows.append(cells[: len(headers)])
            continue
        if isinstance(row, dict):
            rows.append([_as_text(row.get(header)) for header in headers])
    return rows


def _column_heading(column: dict[str, Any], fallback: str) -> str:
    return _as_text(column.get("heading")) or _as_text(column.get("title")) or fallback


def _normalize_column_items(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    items = [_item_text(item) for item in raw]
    return [item for item in items if item]


def _normalize_status(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    title = _as_text(raw.get("title"), STATUS_TITLE)
    message = _as_text(raw.get("message"), STATUS_MESSAGE)
    return {"title": title, "message": message}


def _placeholder_only_bullet_items(raw_items: list[Any]) -> bool:
    if not raw_items:
        return False
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            return False
        title = canonicalize_fallback_text(_as_text(raw_item.get("title")))
        description = canonicalize_fallback_text(_as_text(raw_item.get("description")))
        if not title or title != description or not is_placeholder_text(title):
            return False
    return True


def _bullet_status(data: dict[str, Any], raw_items: list[Any]) -> dict[str, str] | None:
    explicit_status = _normalize_status(data.get("status"))
    if explicit_status is not None:
        return explicit_status
    if _placeholder_only_bullet_items(raw_items):
        return get_bullet_fallback_status()
    return None


def _render_bullet_status_panel(title: str, status: dict[str, str]) -> str:
    return (
        '<div style="padding:56px 64px;height:100%;display:flex;flex-direction:column;">'
        f'<h2 style="font-size:36px;font-weight:700;line-height:1.3;color:#111827;margin:0 0 40px;">{escape(title)}</h2>'
        '<div style="display:flex;flex:1;align-items:center;justify-content:center;">'
        '<div style="max-width:720px;border:1px solid #fde68a;border-radius:24px;background:#fffbeb;padding:36px 40px;text-align:center;box-shadow:0 10px 30px rgba(15,23,42,0.06);">'
        '<div style="margin:0 auto 16px;width:56px;height:56px;border-radius:18px;background:#fef3c7;color:#d97706;display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:700;">!</div>'
        f'<h3 style="font-size:24px;font-weight:700;line-height:1.3;color:#111827;margin:0;">{escape(status["title"])}</h3>'
        f'<p style="font-size:17px;line-height:1.6;color:rgba(17,24,39,0.7);margin:12px 0 0;">{escape(status["message"])}</p>'
        "</div></div></div>"
    )


def _compare_columns(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    left = data.get("left") if isinstance(data.get("left"), dict) else None
    right = data.get("right") if isinstance(data.get("right"), dict) else None

    if not left and not right:
        challenge = data.get("challenge") if isinstance(data.get("challenge"), dict) else {}
        outcome = data.get("outcome") if isinstance(data.get("outcome"), dict) else {}
        left = {
            "heading": _column_heading(challenge, "要点 A"),
            "items": _normalize_column_items(challenge.get("items")),
        }
        right = {
            "heading": _column_heading(outcome, "要点 B"),
            "items": _normalize_column_items(outcome.get("items")),
        }

    left_items_probe = left.get("items") if isinstance(left, dict) else []
    right_items_probe = right.get("items") if isinstance(right, dict) else []
    if (not left and not right) or (not left_items_probe and not right_items_probe):
        items = _normalize_column_items(data.get("items"))
        if are_all_placeholder_texts(items):
            items = [canonicalize_fallback_text(item) for item in items]
        if items:
            midpoint = max(1, (len(items) + 1) // 2)
            left = {"heading": "要点 A", "items": items[:midpoint]}
            right = {"heading": "要点 B", "items": items[midpoint:]}

    left = left or {}
    right = right or {}
    left_items = _normalize_column_items(left.get("items"))
    right_items = _normalize_column_items(right.get("items"))
    if are_all_placeholder_texts([*left_items, *right_items]):
        left_items = [canonicalize_fallback_text(item) for item in left_items]
        right_items = [canonicalize_fallback_text(item) for item in right_items]
    return (
        {"heading": _column_heading(left, "要点 A"), "items": left_items or [CONTENT_GENERATING]},
        {"heading": _column_heading(right, "要点 B"), "items": right_items or [CONTENT_GENERATING]},
    )


def _render_compare_column(column: dict[str, Any]) -> str:
    item_html = "".join(
        f'<p style="font-size:18px;margin-bottom:12px;">• {escape(item)}</p>'
        for item in column.get("items", [])
    )
    return (
        "<div>"
        f'<h3 style="font-size:24px;font-weight:600;margin-bottom:20px;color:#3b82f6;">{escape(_as_text(column.get("heading")))}</h3>'
        f"{item_html}"
        "</div>"
    )


def _challenge_outcome_pairs(data: dict[str, Any]) -> list[dict[str, str]]:
    raw_items = data.get("items")
    pairs: list[dict[str, str]] = []
    if isinstance(raw_items, list):
        for row in raw_items:
            if isinstance(row, dict):
                challenge = _as_text(row.get("challenge"), CONTENT_GENERATING)
                outcome = _as_text(row.get("outcome"), PENDING_SUPPLEMENT)
                if are_all_placeholder_texts([challenge, outcome]):
                    challenge = canonicalize_fallback_text(challenge)
                    outcome = canonicalize_fallback_text(outcome)
                pairs.append({"challenge": challenge, "outcome": outcome})
            elif isinstance(row, str):
                text = row.strip()
                if text:
                    pairs.append(
                        {
                            "challenge": text,
                            "outcome": PENDING_SUPPLEMENT,
                        }
                    )
    if pairs:
        return pairs

    challenge = data.get("challenge") if isinstance(data.get("challenge"), dict) else {}
    outcome = data.get("outcome") if isinstance(data.get("outcome"), dict) else {}
    challenge_items = _normalize_column_items(challenge.get("items"))
    outcome_items = _normalize_column_items(outcome.get("items"))
    if are_all_placeholder_texts([*challenge_items, *outcome_items]):
        challenge_items = [canonicalize_fallback_text(item) for item in challenge_items]
        outcome_items = [canonicalize_fallback_text(item) for item in outcome_items]
    count = max(len(challenge_items), len(outcome_items))
    for idx in range(count):
        pairs.append(
            {
                "challenge": challenge_items[idx] if idx < len(challenge_items) else CONTENT_GENERATING,
                "outcome": outcome_items[idx] if idx < len(outcome_items) else PENDING_SUPPLEMENT,
            }
        )
    return pairs or [{"challenge": CONTENT_GENERATING, "outcome": PENDING_SUPPLEMENT}]

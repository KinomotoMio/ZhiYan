"""Unified deterministic HTML renderer for presentation payloads.

Primary path reads layoutId + contentData.
Legacy components rendering remains as read-only compatibility.
"""

from __future__ import annotations

import re
from html import escape
from typing import Any


def render_presentation_html(presentation_dict: dict[str, Any]) -> str:
    slides = presentation_dict.get("slides", [])
    total = len(slides)
    slides_html = ""

    for idx, slide in enumerate(slides):
        slides_html += _render_single_slide(slide, idx + 1, total)

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Noto Sans SC', 'Microsoft YaHei', 'PingFang SC', 'Helvetica Neue', sans-serif; }}
        .slide {{ margin: 0; }}
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
        content_html = '<div style="padding:60px;color:#9ca3af;">内容为空</div>'

    page_number_html = (
        f'<div style="position:absolute;bottom:2%;right:3%;'
        f'font-size:10px;color:#9ca3af;">{page_num} / {total}</div>'
    )
    return f"""
    <div class="slide" style="position:relative;width:100%;aspect-ratio:16/9;background:white;page-break-after:always;overflow:hidden;">
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


def _normalize_outline_sections(raw: Any) -> list[dict[str, str]]:
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

        section = {"title": title or OUTLINE_FALLBACK_TITLES[index]}
        if description:
            section["description"] = description
        sections.append(section)

    sections = sections[:6]
    while len(sections) < 4:
        sections.append({"title": OUTLINE_FALLBACK_TITLES[len(sections)]})
    return sections


def _split_outline_sections(sections: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    midpoint = (len(sections) + 1) // 2
    return sections[:midpoint], sections[midpoint:]


def _render_outline_column(column: list[dict[str, str]], start_index: int) -> str:
    if not column:
        return ""

    articles = []
    for offset, section in enumerate(column):
        index = start_index + offset + 1
        title = escape(section.get("title", f"Section {index}"))
        description = escape(section.get("description", ""))
        description_html = (
            f'<p style="font-size:15px;line-height:1.6;color:#64748b;margin:12px 0 0;max-width:420px;">{description}</p>'
            if description
            else ""
        )
        articles.append(
            '<article style="border-top:1px solid #dbe2ea;padding-top:18px;display:flex;gap:20px;">'
            '<div style="width:48px;flex-shrink:0;padding-top:4px;">'
            f'<div style="font-size:13px;font-weight:700;letter-spacing:0.18em;color:#2563eb;">{index:02d}</div>'
            '</div>'
            '<div style="min-width:0;">'
            f'<h3 style="font-size:28px;font-weight:600;line-height:1.05;color:#0f172a;margin:0;letter-spacing:-0.04em;">{title}</h3>'
            f'{description_html}'
            '</div>'
            '</article>'
        )

    return (
        f'<div style="flex:1;display:grid;grid-template-rows:repeat({len(column)},minmax(0,1fr));gap:24px;min-height:0;">'
        f'{"".join(articles)}'
        '</div>'
    )

def _render_content_data(layout_id: str, data: dict[str, Any]) -> str:
    d = data
    if layout_id == "intro-slide":
        author = _as_text(d.get("author")) or _as_text(d.get("presenter"))
        date = _as_text(d.get("date"))
        info_parts = [part for part in (author, date) if part]
        return (
            '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;text-align:center;padding:60px;">'
            f'<h1 style="font-size:56px;font-weight:bold;color:#3b82f6;margin-bottom:24px;">{escape(_as_text(d.get("title")))}</h1>'
            f'{_optional_paragraph(_as_text(d.get("subtitle")), "font-size:28px;color:#6b7280;margin-bottom:40px;")}'
            f'{_optional_paragraph(" · ".join(info_parts), "font-size:18px;color:#9ca3af;")}'
            "</div>"
        )

    if layout_id == "section-header":
        section_no = d.get("section_number")
        badge_html = ""
        if section_no is not None and str(section_no).strip():
            badge_html = (
                f'<span style="font-size:20px;color:#3b82f6;margin-bottom:16px;">'
                f'{escape(str(section_no))}</span>'
            )
        return (
            '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;text-align:center;padding:80px;">'
            f"{badge_html}"
            f'<h2 style="font-size:48px;font-weight:bold;margin-bottom:20px;">{escape(_as_text(d.get("title")))}</h2>'
            f'{_optional_paragraph(_as_text(d.get("subtitle")), "font-size:24px;color:#6b7280;")}'
            "</div>"
        )

    if layout_id == "outline-slide":
        sections = _normalize_outline_sections(d.get("sections") if isinstance(d.get("sections"), list) else d.get("items"))
        left, right = _split_outline_sections(sections)
        subtitle = _as_text(d.get("subtitle"))
        return (
            '<div style="padding:56px 64px;height:100%;display:flex;flex-direction:column;background:linear-gradient(180deg,#ffffff 0%,#f8fafc 100%);">'
            '<div style="display:flex;align-items:flex-end;gap:40px;">'
            '<div style="max-width:560px;">'
            '<div style="width:64px;height:6px;border-radius:9999px;background:#2563eb;margin-bottom:20px;"></div>'
            f'<h2 style="font-size:42px;font-weight:bold;line-height:1.12;letter-spacing:-0.045em;color:#0f172a;margin:0 0 16px;">{escape(_as_text(d.get("title"), "Outline"))}</h2>'
            f'{_optional_paragraph(subtitle, "font-size:17px;line-height:1.6;color:#64748b;margin:0;max-width:520px;")}'
            '</div>'
            '<div style="height:1px;flex:1;background:#dbe2ea;margin-bottom:12px;"></div>'
            '</div>'
            '<div style="display:flex;gap:56px;flex:1;margin-top:48px;">'
            f'{_render_outline_column(left, 0)}'
            f'{_render_outline_column(right, len(left))}'
            '</div>'
            '</div>'
        )
    if layout_id in ("bullet-with-icons", "bullet-icons-only"):
        items = d.get("items") if isinstance(d.get("items"), list) else d.get("features", [])
        card_html = "".join(
            _bullet_card(item) for item in (items if isinstance(items, list) else [])
        )
        col_count = min(max(len(items) if isinstance(items, list) else 0, 1), 4)
        return (
            '<div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">'
            f'<h2 style="font-size:40px;font-weight:bold;margin-bottom:40px;">{escape(_as_text(d.get("title")))}</h2>'
            f'<div style="display:grid;grid-template-columns:repeat({col_count},1fr);gap:32px;flex:1;">'
            f"{card_html}"
            "</div></div>"
        )

    if layout_id == "numbered-bullets":
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

    if layout_id == "metrics-slide":
        metrics = d.get("metrics")
        metrics = metrics if isinstance(metrics, list) else []
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
        cols = min(max(len(metrics), 1), 4)
        return (
            '<div style="padding:60px 80px;height:100%;display:flex;flex-direction:column;">'
            f'<h2 style="font-size:40px;font-weight:bold;margin-bottom:48px;">{escape(_as_text(d.get("title")))}</h2>'
            f'<div style="display:grid;grid-template-columns:repeat({cols},1fr);gap:40px;flex:1;align-items:center;">'
            f"{card_html}"
            "</div></div>"
        )

    if layout_id == "metrics-with-image":
        metrics = d.get("metrics")
        metrics = metrics if isinstance(metrics, list) else []
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
            '</div><div style="background:#f3f4f6;display:flex;align-items:center;justify-content:center;color:#9ca3af;">[图片]</div>'
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
        bullets = d.get("bullets")
        bullets = bullets if isinstance(bullets, list) else []
        bullets_html = "".join(
            f'<p style="font-size:16px;color:#6b7280;margin-top:6px;">• {escape(_as_text(item))}</p>'
            for item in bullets
            if _as_text(item)
        )
        return (
            '<div style="display:grid;grid-template-columns:1fr 1fr;height:100%;">'
            '<div style="background:#f3f4f6;display:flex;align-items:center;justify-content:center;color:#9ca3af;">[图片]</div>'
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

    if layout_id == "quote-slide":
        author = _as_text(d.get("author")) or _as_text(d.get("attribution"))
        context = _as_text(d.get("context"))
        meta = " · ".join(part for part in (author, context) if part)
        return (
            '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;text-align:center;padding:80px 120px;">'
            f'<p style="font-size:36px;font-style:italic;color:#374151;line-height:1.5;">"{escape(_as_text(d.get("quote")))}"</p>'
            f'{_optional_paragraph(meta, "font-size:20px;color:#9ca3af;margin-top:32px;")}'
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

    if layout_id == "thank-you":
        contact = _as_text(d.get("contact")) or _as_text(d.get("contact_info"))
        return (
            '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;text-align:center;padding:80px;">'
            f'<h1 style="font-size:56px;font-weight:bold;color:#3b82f6;margin-bottom:24px;">{escape(_as_text(d.get("title"), "谢谢"))}</h1>'
            f'{_optional_paragraph(_as_text(d.get("subtitle")), "font-size:24px;color:#6b7280;margin-bottom:40px;")}'
            f'{_optional_paragraph(contact, "font-size:18px;color:#9ca3af;")}'
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

    left = left or {}
    right = right or {}
    left_items = _normalize_column_items(left.get("items"))
    right_items = _normalize_column_items(right.get("items"))
    return (
        {"heading": _column_heading(left, "要点 A"), "items": left_items or ["内容生成中"]},
        {"heading": _column_heading(right, "要点 B"), "items": right_items or ["内容生成中"]},
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
                challenge = _as_text(row.get("challenge"), "内容生成中")
                outcome = _as_text(row.get("outcome"), "待补充")
                pairs.append({"challenge": challenge, "outcome": outcome})
            elif isinstance(row, str):
                text = row.strip()
                if text:
                    pairs.append({"challenge": text, "outcome": "待补充"})
    if pairs:
        return pairs

    challenge = data.get("challenge") if isinstance(data.get("challenge"), dict) else {}
    outcome = data.get("outcome") if isinstance(data.get("outcome"), dict) else {}
    challenge_items = _normalize_column_items(challenge.get("items"))
    outcome_items = _normalize_column_items(outcome.get("items"))
    count = max(len(challenge_items), len(outcome_items))
    for idx in range(count):
        pairs.append(
            {
                "challenge": challenge_items[idx] if idx < len(challenge_items) else "内容生成中",
                "outcome": outcome_items[idx] if idx < len(outcome_items) else "待补充",
            }
        )
    return pairs or [{"challenge": "内容生成中", "outcome": "待补充"}]

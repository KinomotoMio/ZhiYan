from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.services.layouts.layout_roles import normalize_outline_items_roles


def normalize_planning_outline(outline: dict[str, Any] | BaseModel | None) -> dict[str, Any]:
    raw = outline.model_dump() if isinstance(outline, BaseModel) else dict(outline or {})
    items = raw.get("items") or []
    normalized_items: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        row = dict(item or {})
        title = str(row.get("title") or "").strip() or f"第 {index} 页"
        content_brief = str(
            row.get("content_brief") or row.get("note") or row.get("remark") or ""
        ).strip()
        key_points = [
            str(point).strip()
            for point in (row.get("key_points") or [])
            if str(point).strip()
        ][:5]
        if not key_points:
            key_points = [content_brief[:40]] if content_brief else [title]
        normalized_items.append(
            {
                "slide_number": index,
                "title": title,
                "content_brief": content_brief,
                "note": content_brief,
                "key_points": key_points,
                "content_hints": [
                    str(point).strip()
                    for point in (row.get("content_hints") or [])
                    if str(point).strip()
                ][:6],
                "source_references": [
                    str(point).strip()
                    for point in (row.get("source_references") or [])
                    if str(point).strip()
                ][:8],
                "suggested_slide_role": str(
                    row.get("suggested_slide_role")
                    or row.get("suggested_layout_category")
                    or "narrative"
                ).strip()
                or "narrative",
            }
        )
    normalized_items = normalize_outline_items_roles(
        normalized_items,
        num_pages=len(normalized_items),
    )
    for item in normalized_items:
        item["note"] = str(item.get("content_brief") or "").strip()
    return {
        "narrative_arc": str(raw.get("narrative_arc") or "问题→分析→方案→结论").strip(),
        "items": normalized_items,
    }

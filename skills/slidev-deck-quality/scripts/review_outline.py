#!/usr/bin/env python3
"""Review Slidev outline structure before markdown generation."""

from __future__ import annotations

import json
import sys
from typing import Any

REQUIRED_ROLES = {"cover", "closing"}


def main() -> int:
    payload = json.load(sys.stdin)
    parameters = payload.get("parameters") or {}
    outline_items = parameters.get("outline_items") or []
    expected_pages = parameters.get("expected_pages")
    result = review_outline(outline_items=outline_items, expected_pages=expected_pages)
    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


def review_outline(*, outline_items: Any, expected_pages: Any = None) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not isinstance(outline_items, list) or not outline_items:
        issues.append({"code": "missing_outline", "message": "Outline items are missing."})
        return _result(False, issues, warnings, [])

    roles: list[str] = []
    for item in outline_items:
        if not isinstance(item, dict):
            issues.append({"code": "invalid_outline_item", "message": "Outline items must be objects."})
            continue
        title = str(item.get("title") or "").strip()
        role = str(item.get("slide_role") or "").strip().lower()
        goal = str(item.get("goal") or "").strip()
        content_shape = str(item.get("content_shape") or "").strip()
        if not title or not role or not goal or not content_shape:
            issues.append(
                {
                    "code": "incomplete_outline_item",
                    "message": "Each outline item needs title, slide_role, content_shape, and goal.",
                }
            )
            continue
        roles.append(role)

    if roles:
        missing_roles = sorted(REQUIRED_ROLES.difference(roles))
        for role in missing_roles:
            issues.append({"code": f"missing_{role}", "message": f"Outline is missing a `{role}` slide."})

        if len(set(roles)) <= 2 and len(roles) >= 4:
            warnings.append(
                {
                    "code": "outline_role_monotony",
                    "message": "Outline uses too few distinct page roles for the deck length.",
                }
            )

    normalized_expected = _coerce_int(expected_pages)
    if normalized_expected is not None and abs(len(outline_items) - normalized_expected) >= 2:
        warnings.append(
            {
                "code": "outline_page_budget_mismatch",
                "message": f"Outline has {len(outline_items)} pages, noticeably different from expected {normalized_expected}.",
            }
        )

    return _result(not issues, issues, warnings, roles)


def _result(ok: bool, issues: list[dict[str, str]], warnings: list[dict[str, str]], roles: list[str]) -> dict[str, Any]:
    return {
        "ok": ok,
        "issues": issues,
        "warnings": warnings,
        "roles": roles,
    }


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())

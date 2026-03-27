"""AgentLoop-native verification and repair helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.models.slide import Slide
from app.services.generation.runtime_state import GenerationRuntimeState, ProgressHook
from app.services.presentations import normalize_presentation_payload


async def stage_verify_slides(
    state: GenerationRuntimeState,
    progress: ProgressHook | None = None,
    enable_vision: bool = True,
) -> None:
    del enable_vision

    if progress:
        await progress("verify", 1, 2, "检查演示页结构与可恢复问题...")

    issues: list[dict[str, Any]] = []
    failed_indices: list[int] = []
    for index, slide in enumerate(state.slides):
        report = _inspect_slide(slide)
        if report["issue"] is not None:
            issues.append(report["issue"])
        if report["failed"]:
            failed_indices.append(index)

    state.verification_issues = issues
    state.failed_slide_indices = failed_indices

    if progress:
        await progress("verify", 2, 2, "验证完成")


async def stage_fix_slides_once(
    state: GenerationRuntimeState,
    *,
    per_slide_timeout: float,
    target_slide_ids: set[str],
    progress: ProgressHook | None = None,
    on_slide=None,
) -> None:
    del per_slide_timeout

    if progress:
        await progress("fix", 1, max(1, len(target_slide_ids)), "生成修复建议...")

    repaired_slides: list[Slide] = []
    total = max(1, len(target_slide_ids))
    repaired = 0
    for index, slide in enumerate(state.slides):
        if slide.slide_id not in target_slide_ids:
            repaired_slides.append(slide)
            continue
        repaired += 1
        next_slide = _repair_slide(slide)
        repaired_slides.append(next_slide)
        if on_slide:
            await on_slide({"slide_index": index, "slide": next_slide.model_dump(mode="json", by_alias=True)})
        if progress:
            await progress("fix", repaired, total, f"已生成第 {repaired} 页修复建议")

    state.slides = repaired_slides
    state.failed_slide_indices = []
    state.verification_issues = []


def _inspect_slide(slide: Slide) -> dict[str, Any]:
    payload = {
        "presentationId": "pres-verify",
        "title": "验证",
        "slides": [slide.model_dump(mode="json", by_alias=True)],
    }
    normalized, changed, report = normalize_presentation_payload(payload)
    invalid_count = int(report.get("invalid_slide_count") or 0)
    repair_types = list(report.get("repair_types") or [])

    if invalid_count > 0:
        return {
            "failed": True,
            "issue": {
                "slide_id": slide.slide_id,
                "severity": "error",
                "tier": "hard",
                "category": "schema-invalid",
                "message": "页面内容不满足当前布局约束，需要修复后才能安全落盘。",
                "repair_types": repair_types,
            },
            "normalized_slide": normalized.get("slides", [None])[0],
        }

    if changed:
        return {
            "failed": False,
            "issue": {
                "slide_id": slide.slide_id,
                "severity": "warning",
                "tier": "advisory",
                "category": "normalization",
                "message": "页面内容可自动标准化，建议预览修复结果。",
                "repair_types": repair_types,
            },
            "normalized_slide": normalized.get("slides", [None])[0],
        }

    return {"failed": False, "issue": None, "normalized_slide": None}


def _repair_slide(slide: Slide) -> Slide:
    report = _inspect_slide(slide)
    if report["failed"]:
        return _fallback_slide(slide)
    normalized_slide = report.get("normalized_slide")
    if isinstance(normalized_slide, dict):
        try:
            return Slide.model_validate(normalized_slide)
        except Exception:
            pass
    return slide


def _fallback_slide(slide: Slide) -> Slide:
    data = deepcopy(slide.content_data or {})
    title = _pick_title(data) or f"第 {slide.slide_id.split('-')[-1]} 页"
    body = _pick_body(data)
    return Slide(
        slideId=slide.slide_id,
        layoutType="bullet-with-icons",
        layoutId="bullet-with-icons",
        contentData={
            "title": title,
            "items": [
                {
                    "icon": {"query": "sparkles"},
                    "title": "内容已自动修复",
                    "description": body or "原始页面不满足布局结构约束，已回退为通用要点页。",
                }
            ],
        },
        components=[],
        speakerNotes=slide.speaker_notes,
    )


def _pick_title(data: dict[str, Any]) -> str:
    for key in ("title", "quote", "label"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    sections = data.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if isinstance(section, dict):
                value = section.get("title")
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return ""


def _pick_body(data: dict[str, Any]) -> str:
    for key in ("subtitle", "conclusion", "context", "contact"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    items = data.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                value = item.get("description") or item.get("title")
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return ""

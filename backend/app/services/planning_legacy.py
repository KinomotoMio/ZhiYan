"""Create-page planning orchestration for REPL-style PPT kickoff."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.services.agents.outline_synthesizer import PresentationOutline
from app.services.layouts.layout_roles import normalize_outline_items_roles


MAX_CLARIFICATION_TURNS = 3


class PlanningBrief(BaseModel):
    topic: str = ""
    audience: str = ""
    objective: str = ""
    style: str = ""
    tone: str = ""
    preferred_pages: int | None = None
    extra_requirements: str = ""


class _OutlineRevisionResult(BaseModel):
    narrative_arc: str = ""
    items: list[dict[str, Any]] = Field(default_factory=list)


@dataclass
class PlanningTurnOutcome:
    assistant_message: str
    brief: dict[str, Any]
    outline: dict[str, Any] | None
    outline_version_increment: int = 0
    status: str = "collecting_requirements"
    events: list[dict[str, Any]] | None = None


_brief_agent = None
_outline_revision_agent = None


def _get_brief_agent():
    global _brief_agent
    if _brief_agent is None:
        from pydantic_ai import Agent

        from app.core.config import settings
        from app.core.model_resolver import resolve_model

        _brief_agent = Agent(
            model=resolve_model(settings.fast_model or settings.strong_model),
            output_type=PlanningBrief,
            instructions=(
                "你是 PPT 需求梳理助手。"
                "请基于当前 brief、最近几轮对话和用户最新输入，提炼稳定需求。"
                "只输出已明确表达或高置信可归纳的信息；不确定时留空。"
                "preferred_pages 仅在用户明确提到页数、篇幅、长短需求时填写。"
            ),
        )
    return _brief_agent


def _get_outline_revision_agent():
    global _outline_revision_agent
    if _outline_revision_agent is None:
        from pydantic_ai import Agent

        from app.core.config import settings
        from app.core.model_resolver import resolve_model

        _outline_revision_agent = Agent(
            model=resolve_model(settings.strong_model),
            output_type=_OutlineRevisionResult,
            instructions=(
                "你是演示文稿大纲编辑助手。"
                "你会根据用户反馈修改现有逐页大纲。"
                "必须保留 slide_number 连续，title 清晰，content_brief 简洁，"
                "并尽量保持每页角色合理。"
                "如果用户要求增删页、调序、改标题、补备注，都直接体现在输出里。"
                "不要输出解释，只输出结构化结果。"
            ),
        )
    return _outline_revision_agent


def build_opening_message() -> str:
    return (
        "想一起做什么样的 PPT？\n\n"
        "你可以直接告诉我主题、受众、目标，或者先把左侧素材勾上，我来帮你梳理成可确认的大纲。"
    )


def _normalize_brief_payload(brief: dict[str, Any] | None) -> dict[str, Any]:
    current = dict(brief or {})
    meta = current.get("_meta")
    if not isinstance(meta, dict):
        meta = {}
    current["_meta"] = {
        "clarification_turns": int(meta.get("clarification_turns") or 0),
        "user_turns": int(meta.get("user_turns") or 0),
    }
    return current


def _merge_brief(current: dict[str, Any] | None, extracted: PlanningBrief) -> dict[str, Any]:
    merged = _normalize_brief_payload(current)
    payload = extracted.model_dump(exclude_none=True)
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                merged[key] = normalized
        elif key == "preferred_pages" and isinstance(value, int) and value > 0:
            merged[key] = value
    return merged


def _brief_to_prompt_text(brief: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "topic",
        "audience",
        "objective",
        "style",
        "tone",
        "preferred_pages",
        "extra_requirements",
    ):
        value = brief.get(key)
        if value in (None, "", []):
            continue
        label = {
            "topic": "主题",
            "audience": "受众",
            "objective": "目标",
            "style": "风格",
            "tone": "语气",
            "preferred_pages": "页数偏好",
            "extra_requirements": "补充要求",
        }[key]
        parts.append(f"{label}: {value}")
    return "\n".join(parts)


def _source_summary(source_names: list[str]) -> str:
    cleaned = [item.strip() for item in source_names if item and item.strip()]
    if not cleaned:
        return "无素材"
    return "、".join(cleaned[:8])


async def extract_brief(
    *,
    current_brief: dict[str, Any] | None,
    recent_messages: list[dict[str, str]],
    user_message: str,
    source_names: list[str],
) -> dict[str, Any]:
    history_lines = []
    for item in recent_messages[-6:]:
        role = "用户" if item.get("role") == "user" else "助手"
        content = str(item.get("content") or "").strip()
        if content:
            history_lines.append(f"{role}: {content}")
    prompt = (
        f"当前 brief:\n{json.dumps(current_brief or {}, ensure_ascii=False, indent=2)}\n\n"
        f"已选素材: {_source_summary(source_names)}\n\n"
        f"最近对话:\n{chr(10).join(history_lines) or '（无）'}\n\n"
        f"用户最新输入:\n{user_message.strip()}\n"
    )
    result = await _get_brief_agent().run(prompt)
    return _merge_brief(current_brief, result.output)


def _missing_fields(brief: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not str(brief.get("topic") or "").strip():
        missing.append("topic")
    if not str(brief.get("audience") or "").strip():
        missing.append("audience")
    if not str(brief.get("objective") or "").strip():
        missing.append("objective")
    if not str(brief.get("style") or "").strip():
        missing.append("style")
    return missing


def _preferred_page_count(brief: dict[str, Any], outline: dict[str, Any] | None = None) -> int:
    preferred = brief.get("preferred_pages")
    if isinstance(preferred, int) and preferred > 0:
        return max(3, min(preferred, 20))
    if outline and isinstance(outline.get("items"), list) and outline["items"]:
        return max(3, min(len(outline["items"]), 20))
    return 6


def _should_generate_outline(
    *,
    brief: dict[str, Any],
    user_message: str,
    source_count: int,
) -> bool:
    meta = _normalize_brief_payload(brief)["_meta"]
    clarification_turns = int(meta.get("clarification_turns") or 0)
    user_turns = int(meta.get("user_turns") or 0)
    message_length = len(user_message.strip())
    missing = _missing_fields(brief)
    complex_task = (
        source_count >= 2
        or message_length >= 180
        or int(brief.get("preferred_pages") or 0) >= 8
    )
    if clarification_turns >= MAX_CLARIFICATION_TURNS:
        return True
    if source_count > 0 and user_turns >= 1 and message_length >= 24:
        return True
    if len(missing) <= 1 and user_turns >= 1:
        return True
    if user_turns >= 2 and not complex_task:
        return True
    if user_turns >= 3:
        return True
    return False


def _build_followup_question(brief: dict[str, Any]) -> str:
    missing = _missing_fields(brief)
    if not missing:
        return "我先按这个方向起一版大纲，你看看结构是否对路。"
    if missing[:2] == ["topic", "audience"] or "topic" in missing:
        return "我先补两个关键点：这份 PPT 主要讲什么主题，给谁看？"
    if "audience" in missing and "objective" in missing:
        return "这份 PPT 主要给谁看，希望他们看完后形成什么判断或动作？"
    if "style" in missing:
        return "表达风格上你更偏正式汇报、方案提案，还是更故事化一点？"
    return "我再确认一下：这份 PPT 最想达成的目标是什么？"


def normalize_planning_outline(
    outline: dict[str, Any] | PresentationOutline | _OutlineRevisionResult | None,
) -> dict[str, Any]:
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
            if content_brief:
                key_points = [content_brief[:40]]
            else:
                key_points = [title]
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


async def generate_outline(
    *,
    brief: dict[str, Any],
    content: str,
) -> dict[str, Any]:
    from app.services.agents.outline_synthesizer import outline_synthesizer_agent

    topic = str(brief.get("topic") or "综合演示").strip() or "综合演示"
    num_pages = _preferred_page_count(brief)
    brief_section = _brief_to_prompt_text(brief)
    prompt = (
        f"演示文稿主题：{topic}\n"
        f"目标页数：{num_pages} 页\n\n"
        f"需求摘要:\n{brief_section or '（用户尚未补充更多要求）'}\n\n"
        f"内容:\n{content.strip() or topic}\n\n"
        f"请生成一个 {num_pages} 页的演示文稿大纲。"
    )
    result = await outline_synthesizer_agent.run(prompt)
    return normalize_planning_outline(result.output)


async def revise_outline(
    *,
    current_outline: dict[str, Any],
    brief: dict[str, Any],
    user_message: str,
) -> dict[str, Any]:
    prompt = (
        f"当前需求摘要:\n{json.dumps(brief, ensure_ascii=False, indent=2)}\n\n"
        f"当前大纲:\n{json.dumps(current_outline, ensure_ascii=False, indent=2)}\n\n"
        f"用户修改意见:\n{user_message.strip()}\n"
    )
    result = await _get_outline_revision_agent().run(prompt)
    return normalize_planning_outline(result.output)


def build_outline_ready_message(outline: dict[str, Any]) -> str:
    items = outline.get("items") or []
    return (
        f"我先起了一版 {len(items)} 页的大纲，已经放在下面了。\n\n"
        "你可以直接改每页标题和备注、拖动顺序、增删页面，"
        "也可以继续用自然语言告诉我想怎么调整。"
    )


def build_outline_revised_message() -> str:
    return "我已经按你的反馈更新了大纲，看看现在的结构和页序是否更接近你想要的版本。"


async def handle_planning_turn(
    *,
    current_brief: dict[str, Any] | None,
    current_outline: dict[str, Any] | None,
    user_message: str,
    recent_messages: list[dict[str, str]],
    content: str,
    source_names: list[str],
    source_ids: list[str],
) -> PlanningTurnOutcome:
    merged_brief = await extract_brief(
        current_brief=current_brief,
        recent_messages=recent_messages,
        user_message=user_message,
        source_names=source_names,
    )
    meta = _normalize_brief_payload(merged_brief)["_meta"]
    meta["user_turns"] = int(meta.get("user_turns") or 0) + 1
    merged_brief["_meta"] = meta

    events: list[dict[str, Any]] = [
        {"type": "brief_updated", "brief": merged_brief},
    ]

    if current_outline and (current_outline.get("items") or []):
        next_outline = await revise_outline(
            current_outline=current_outline,
            brief=merged_brief,
            user_message=user_message,
        )
        events.append({"type": "outline_revised", "outline": next_outline})
        events.append({"type": "status_changed", "status": "outline_ready"})
        return PlanningTurnOutcome(
            assistant_message=build_outline_revised_message(),
            brief=merged_brief,
            outline=next_outline,
            outline_version_increment=1,
            status="outline_ready",
            events=events,
        )

    if not _should_generate_outline(
        brief=merged_brief,
        user_message=user_message,
        source_count=len(source_ids),
    ):
        meta["clarification_turns"] = min(
            MAX_CLARIFICATION_TURNS,
            int(meta.get("clarification_turns") or 0) + 1,
        )
        merged_brief["_meta"] = meta
        question = _build_followup_question(merged_brief)
        events.append({"type": "status_changed", "status": "collecting_requirements"})
        return PlanningTurnOutcome(
            assistant_message=question,
            brief=merged_brief,
            outline=None,
            status="collecting_requirements",
            events=events,
        )

    next_outline = await generate_outline(brief=merged_brief, content=content)
    events.append({"type": "outline_drafted", "outline": next_outline})
    events.append({"type": "status_changed", "status": "outline_ready"})
    return PlanningTurnOutcome(
        assistant_message=build_outline_ready_message(next_outline),
        brief=merged_brief,
        outline=next_outline,
        outline_version_increment=1,
        status="outline_ready",
        events=events,
    )

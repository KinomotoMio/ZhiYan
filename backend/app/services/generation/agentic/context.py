"""Deterministic helpers for generation agentic context management."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import is_dataclass
from typing import Any

from app.services.generation.agentic.types import AgenticMessage, AssistantMessage, UserMessage
from app.services.pipeline.graph import PipelineState


def summarize_state(state: PipelineState | None) -> str:
    """Summarize the current pipeline state in a compact, model-friendly form."""

    if state is None:
        return "（尚未开始生成）"

    parts: list[str] = []
    metadata = state.document_metadata or {}
    if metadata:
        detail_bits: list[str] = []
        char_count = _as_int(metadata.get("char_count"))
        if char_count > 0:
            detail_bits.append(f"{char_count} 字符")

        estimated_tokens = _as_int(metadata.get("estimated_tokens"))
        if estimated_tokens > 0:
            detail_bits.append(f"约 {estimated_tokens} tokens")

        heading_count = _as_int(metadata.get("heading_count"))
        if heading_count > 0:
            detail_bits.append(f"{heading_count} 个标题")

        if detail_bits:
            parts.append(f"文档已解析：{_join_detail_bits(detail_bits)}")
        else:
            parts.append("文档已解析")

    outline_titles = _extract_outline_titles(state.outline)
    if outline_titles:
        parts.append(f"大纲已生成：{len(outline_titles)} 个章节 - {_join_preview(outline_titles)}")
    elif state.outline:
        parts.append("大纲已生成")

    layouts = list(state.layout_selections or [])
    if layouts:
        layout_bits = _extract_layout_preview(layouts)
        suffix = f" - {_join_preview(layout_bits)}" if layout_bits else ""
        parts.append(f"布局已选择：{len(layouts)} 页{suffix}")

    slide_count = len(state.slides or [])
    if slide_count > 0:
        parts.append(f"幻灯片已生成：{slide_count} 页")
    elif state.slide_contents:
        parts.append(f"幻灯片已生成：{len(state.slide_contents)} 页")

    issue_bits = _summarize_issues(state.verification_issues or [])
    if issue_bits:
        parts.append(f"校验问题：{issue_bits}")

    if state.failed_slide_indices:
        indices = ", ".join(str(idx) for idx in state.failed_slide_indices[:8])
        suffix = f" 等 {len(state.failed_slide_indices)} 页" if len(state.failed_slide_indices) > 8 else ""
        parts.append(f"失败页：{indices}{suffix}")

    return "\n".join(parts) if parts else "（尚未开始生成）"


def compact_context(
    messages: Sequence[AgenticMessage],
    *,
    max_tokens: int = 80_000,
    keep_recent: int = 6,
    state_summary: str | None = None,
) -> list[AgenticMessage]:
    """Compact older messages into a single synthetic summary request."""

    preserved = list(messages)
    if not preserved:
        return []

    estimated_tokens = _estimate_tokens(preserved)
    if estimated_tokens <= max_tokens or len(preserved) <= keep_recent:
        return preserved

    keep_recent = max(0, keep_recent)
    recent = preserved[-keep_recent:] if keep_recent else []
    old_messages = preserved[:-keep_recent] if keep_recent else preserved

    summary_lines = [
        "以下是被压缩掉的旧上下文摘要。请结合这些摘要与最近消息继续推理：",
    ]
    if state_summary:
        summary_lines.extend(["", "当前状态：", state_summary, ""])
    for index, message in enumerate(old_messages, start=1):
        summary_lines.append(f"{index}. {_describe_message(message)}")

    summary_request = UserMessage(parts=["\n".join(summary_lines)])
    return [summary_request, *recent]


def _estimate_tokens(messages: Sequence[AgenticMessage]) -> int:
    char_count = 0
    for message in messages:
        char_count += len(_describe_message(message))
    return max(1, (char_count + 3) // 4)


def _describe_message(message: AgenticMessage) -> str:
    if isinstance(message, UserMessage):
        return f"user: {_describe_user_message(message)}"
    if isinstance(message, AssistantMessage):
        return f"assistant: {_describe_assistant_message(message)}"
    return repr(message)


def _describe_user_message(message: UserMessage) -> str:
    chunks: list[str] = []
    for part in message.parts:
        if isinstance(part, str):
            chunks.append(f"text={_shorten(part)}")
        else:
            label = "tool_error" if part.is_error else "tool_result"
            chunks.append(f"{label}({part.tool_name})={_shorten(_stringify(part.content))}")
    if message.instructions:
        chunks.append(f"instructions={_shorten(message.instructions)}")
    return "; ".join(chunks) if chunks else "(empty user message)"


def _describe_assistant_message(message: AssistantMessage) -> str:
    chunks: list[str] = []
    for part in message.parts:
        if isinstance(part, str):
            chunks.append(f"text={_shorten(part)}")
        else:
            chunks.append(f"tool_call({part.tool_name})={_shorten(_stringify(part.args))}")
    return "; ".join(chunks) if chunks else "(empty assistant message)"


def _extract_outline_titles(outline: Any) -> list[str]:
    if not isinstance(outline, dict):
        return []

    items = outline.get("items")
    if not isinstance(items, list):
        return []

    titles: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("section_title") or item.get("slide_title")
        text = str(title).strip()
        if text:
            titles.append(text)
    return titles


def _extract_layout_preview(layouts: Sequence[Any]) -> list[str]:
    preview: list[str] = []
    for layout in layouts[:5]:
        if not isinstance(layout, dict):
            continue
        slide_number = layout.get("slide_number")
        layout_id = layout.get("layout_id") or layout.get("layoutId")
        if slide_number is not None and layout_id:
            preview.append(f"{slide_number}:{layout_id}")
        elif layout_id:
            preview.append(str(layout_id))
        elif slide_number is not None:
            preview.append(str(slide_number))
    return preview


def _summarize_issues(issues: Sequence[Any]) -> str:
    hard = 0
    advisory = 0
    for issue in issues:
        if not isinstance(issue, dict):
            advisory += 1
            continue
        tier = str(issue.get("tier") or "").lower()
        severity = str(issue.get("severity") or "").lower()
        if tier == "hard" or (not tier and severity == "error"):
            hard += 1
        else:
            advisory += 1
    bits: list[str] = []
    if hard:
        bits.append(f"{hard} 个严重")
    if advisory:
        bits.append(f"{advisory} 个建议")
    return "，".join(bits)


def _shorten(value: Any, limit: int = 120) -> str:
    text = _stringify(value).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if is_dataclass(value):
        try:
            return json.dumps(_dataclass_to_dict(value), ensure_ascii=False, sort_keys=True)
        except Exception:
            return repr(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value)


def _dataclass_to_dict(value: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key in getattr(value, "__dataclass_fields__", {}):
        data[key] = getattr(value, key)
    return data


def _join_detail_bits(bits: Sequence[str]) -> str:
    return "，".join(bits)


def _join_preview(items: Sequence[str], limit: int = 5) -> str:
    cleaned = [item for item in items if item]
    if not cleaned:
        return ""
    if len(cleaned) <= limit:
        return ", ".join(cleaned)
    return ", ".join(cleaned[:limit]) + f" 等 {len(cleaned)} 项"


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0

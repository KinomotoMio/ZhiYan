"""State summary and context compaction helpers for agentic generation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
import json

from app.services.document.parser import estimate_tokens
from app.services.generation.agentic.types import AgenticMessage, AssistantMessage, ToolCall, ToolResult, UserMessage
from app.services.pipeline.graph import PipelineState

STATE_SUMMARY_HEADER = "Current pipeline state:"
COMPACTION_SUMMARY_HEADER = "Condensed earlier context:"
DEFAULT_CONTEXT_MAX_TOKENS = 80_000
DEFAULT_KEEP_RECENT = 6
_PREVIEW_LIMIT = 160


def summarize_state(state: PipelineState | None) -> str:
    """Serialize the current pipeline state into a compact model-readable summary."""

    if state is None:
        return "（尚未开始生成）"

    parts: list[str] = []

    if state.document_metadata:
        topic = str(state.topic or state.document_metadata.get("title") or "").strip()
        estimated_tokens = state.document_metadata.get("estimated_tokens")
        heading_count = state.document_metadata.get("heading_count")
        details = []
        if topic:
            details.append(f"主题 {topic}")
        if isinstance(estimated_tokens, int) and estimated_tokens > 0:
            details.append(f"约 {estimated_tokens} tokens")
        if isinstance(heading_count, int) and heading_count > 0:
            details.append(f"{heading_count} 个标题")
        if details:
            parts.append(f"文档已解析：{'，'.join(details)}")

    outline_items = state.outline.get("items", []) if isinstance(state.outline, dict) else []
    if outline_items:
        labels = []
        for item in outline_items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            role = str(item.get("slide_role") or "").strip()
            labels.append(f"{title}({role})" if role else title)
        preview = "；".join(labels[:5])
        line = f"大纲已生成：{len(outline_items)} 页"
        if preview:
            suffix = "；..." if len(labels) > 5 else ""
            line = f"{line} - {preview}{suffix}"
        parts.append(line)

    outline_review = state.document_metadata.get("slidev_outline_review")
    deck_review = state.document_metadata.get("slidev_deck_review")
    review_parts = []
    if isinstance(outline_review, dict):
        review_parts.append(_review_label("大纲审查", outline_review))
    if isinstance(deck_review, dict):
        review_parts.append(_review_label("结构审查", deck_review))
    if review_parts:
        parts.append("；".join(part for part in review_parts if part))

    if state.layout_selections:
        layout_ids = [
            str(item.get("layout_id") or item.get("layoutId") or "").strip()
            for item in state.layout_selections
            if isinstance(item, dict)
        ]
        preview_ids = [layout_id for layout_id in layout_ids if layout_id][:5]
        line = f"布局已选择：{len(state.layout_selections)} 页"
        if preview_ids:
            suffix = ", ..." if len(layout_ids) > 5 else ""
            line = f"{line} - {', '.join(preview_ids)}{suffix}"
        parts.append(line)

    generated_slides = max(len(state.slide_contents), len(state.slides))
    if generated_slides:
        total_slides = max(
            generated_slides,
            len(outline_items),
            len(state.layout_selections),
            int(state.num_pages or 0),
        )
        parts.append(f"幻灯片已生成：{generated_slides}/{total_slides} 页")

    if state.verification_issues:
        severity_counts: dict[str, int] = {}
        for issue in state.verification_issues:
            severity = str(issue.get("severity") or "unknown")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        details = "，".join(f"{severity} {count}" for severity, count in sorted(severity_counts.items()))
        parts.append(f"校验问题：{len(state.verification_issues)} 条（{details}）")

    if state.failed_slide_indices:
        failed = ", ".join(str(index) for index in state.failed_slide_indices[:5])
        suffix = ", ..." if len(state.failed_slide_indices) > 5 else ""
        parts.append(f"待修复页：{failed}{suffix}")

    return "\n".join(parts) if parts else "（尚未开始生成）"


def attach_state_summary(tool_result: ToolResult, state: PipelineState | None) -> ToolResult:
    """Attach a visible state summary to the tool result content."""

    state_summary = summarize_state(state)
    metadata = dict(tool_result.metadata)
    metadata["state_summary"] = state_summary

    content = tool_result.content
    if isinstance(content, str):
        content = _append_state_summary_text(content, state_summary)
    else:
        content = {
            "result": content,
            "state_summary": state_summary,
        }

    return replace(tool_result, content=content, metadata=metadata)


def compact_context(
    messages: Sequence[AgenticMessage],
    *,
    max_tokens: int = DEFAULT_CONTEXT_MAX_TOKENS,
    keep_recent: int = DEFAULT_KEEP_RECENT,
    state_summary: str | None = None,
) -> list[AgenticMessage]:
    """Condense old messages when history grows beyond the target token budget."""

    materialized = list(messages)
    if estimate_message_tokens(materialized) <= max_tokens:
        return materialized

    recent_count = max(keep_recent * 2, 1)
    if len(materialized) <= recent_count + 1:
        return materialized

    old_messages = materialized[:-recent_count]
    recent_messages = materialized[-recent_count:]
    summary_lines = [COMPACTION_SUMMARY_HEADER, f"- condensed {len(old_messages)} earlier messages"]

    current_state = state_summary.strip() if state_summary else ""
    if current_state:
        summary_lines.extend(["", STATE_SUMMARY_HEADER, current_state])

    message_lines = [_summarize_message(message) for message in old_messages]
    if message_lines:
        summary_lines.extend(["", *message_lines])

    instructions = next(
        (message.instructions for message in materialized if isinstance(message, UserMessage) and message.instructions),
        None,
    )
    compacted = UserMessage(parts=["\n".join(summary_lines)], instructions=instructions)
    return [compacted, *recent_messages]


def estimate_message_tokens(messages: Sequence[AgenticMessage]) -> int:
    """Estimate the token footprint of the internal message list."""

    text = "\n".join(_serialize_message(message) for message in messages)
    return estimate_tokens(text)


def _append_state_summary_text(content: str, state_summary: str) -> str:
    text = content.rstrip()
    summary_block = f"{STATE_SUMMARY_HEADER}\n{state_summary}"
    if not text:
        return summary_block
    return f"{text}\n\n{summary_block}"


def _summarize_message(message: AgenticMessage) -> str:
    if isinstance(message, AssistantMessage):
        tool_names = [part.tool_name for part in message.parts if isinstance(part, ToolCall)]
        text_parts = [_preview_text(part) for part in message.parts if isinstance(part, str) and part.strip()]
        details: list[str] = []
        if tool_names:
            details.append(f"tool calls: {', '.join(tool_names)}")
        if text_parts:
            details.append(f"text: {' | '.join(text_parts[:2])}")
        return f"- assistant: {'; '.join(details) or '(no text)'}"

    text_parts = [_preview_text(part) for part in message.parts if isinstance(part, str) and part.strip()]
    tool_parts = []
    for part in message.parts:
        if isinstance(part, ToolResult):
            tool_parts.append(f"{part.tool_name} => {_preview_text(_tool_result_text(part))}")

    details = []
    if text_parts:
        details.append(f"text: {' | '.join(text_parts[:2])}")
    if tool_parts:
        details.append(f"tool results: {'; '.join(tool_parts[:2])}")
    return f"- user: {'; '.join(details) or '(no text)'}"


def _serialize_message(message: AgenticMessage) -> str:
    prefix = "assistant" if isinstance(message, AssistantMessage) else "user"
    parts: list[str] = []
    for part in message.parts:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, ToolCall):
            args = json.dumps(part.args, ensure_ascii=False, sort_keys=True)
            parts.append(f"tool_call {part.tool_name} {args}")
        else:
            parts.append(f"tool_result {part.tool_name} {_tool_result_text(part)}")
    return f"{prefix}: {' | '.join(parts)}"


def _tool_result_text(part: ToolResult) -> str:
    content = part.content
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(content)


def _preview_text(value: str) -> str:
    text = " ".join(value.split())
    if len(text) <= _PREVIEW_LIMIT:
        return text
    return f"{text[:_PREVIEW_LIMIT - 3]}..."


def _review_label(prefix: str, review: dict[str, object]) -> str:
    warnings = review.get("warnings")
    warning_count = len(warnings) if isinstance(warnings, list) else 0
    ok = bool(review.get("ok"))
    suffix = f"（warning {warning_count}）" if warning_count else ""
    return f"{prefix}：{'通过' if ok else '未通过'}{suffix}"

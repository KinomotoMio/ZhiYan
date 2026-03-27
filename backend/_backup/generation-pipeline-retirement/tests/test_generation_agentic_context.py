from __future__ import annotations

from app.models.slide import Slide
from app.services.generation.agentic_legacy.context import attach_state_summary, compact_context, summarize_state
from app.services.generation.agentic_legacy.types import AssistantMessage, ToolCall, ToolResult, UserMessage
from app.services.pipeline.graph import PipelineState


def _slide_payload(slide_id: str, title: str) -> dict:
    return {
        "slideId": slide_id,
        "layoutType": "bullet-with-icons",
        "layoutId": "bullet-with-icons",
        "contentData": {
            "title": title,
            "items": [{"title": "要点", "description": "说明"}],
        },
        "components": [],
    }


def test_summarize_state_returns_default_for_empty_state():
    state = PipelineState(job_id="job-1")

    assert summarize_state(state) == "（尚未开始生成）"


def test_summarize_state_includes_outline_layout_and_slide_progress():
    state = PipelineState(
        job_id="job-1",
        topic="AI 增长策略",
        num_pages=4,
        document_metadata={"estimated_tokens": 920, "heading_count": 3},
        outline={
            "items": [
                {"slide_number": 1, "title": "问题定义", "slide_role": "context"},
                {"slide_number": 2, "title": "市场趋势", "slide_role": "framework"},
                {"slide_number": 3, "title": "执行路径", "slide_role": "recommendation"},
            ]
        },
        layout_selections=[
            {"slide_number": 1, "layout_id": "intro-slide"},
            {"slide_number": 2, "layout_id": "metrics-slide"},
            {"slide_number": 3, "layout_id": "timeline"},
        ],
        slides=[Slide.model_validate(_slide_payload("slide-1", "问题定义"))],
        verification_issues=[{"severity": "warning", "message": "信息略密"}],
        failed_slide_indices=[2],
    )
    state.document_metadata["slidev_outline_review"] = {"ok": True, "warnings": [{"code": "monotony", "message": "warn"}]}
    state.document_metadata["slidev_deck_review"] = {"ok": True, "warnings": []}

    summary = summarize_state(state)

    assert "文档已解析：主题 AI 增长策略，约 920 tokens，3 个标题" in summary
    assert "大纲已生成：3 页 - 问题定义(context)；市场趋势(framework)；执行路径(recommendation)" in summary
    assert "大纲审查：通过（0 hard / 1 warnings）；结构审查：通过（0 hard / 0 warnings）" in summary
    assert "布局已选择：3 页 - intro-slide, metrics-slide, timeline" in summary
    assert "幻灯片已生成：1/4 页" in summary
    assert "校验问题：1 条（warning 1）" in summary
    assert "待修复页：2" in summary


def test_attach_state_summary_wraps_tool_result_content():
    state = PipelineState(outline={"items": [{"slide_number": 1, "title": "问题定义", "slide_role": "context"}]})
    part = ToolResult(tool_name="generate_outline", content={"ok": True}, tool_call_id="call-1")

    enriched = attach_state_summary(part, state)

    assert enriched.metadata["state_summary"] == "大纲已生成：1 页 - 问题定义(context)"
    assert enriched.content == {
        "result": {"ok": True},
        "state_summary": "大纲已生成：1 页 - 问题定义(context)",
    }


def test_compact_context_returns_original_when_under_budget():
    messages = [
        UserMessage(parts=["generate deck"], instructions="keep concise"),
        AssistantMessage(parts=["working on it"]),
    ]

    compacted = compact_context(messages, max_tokens=10_000, keep_recent=2, state_summary="大纲已生成：1 页 - 问题定义")

    assert compacted == messages


def test_compact_context_preserves_recent_messages_and_adds_summary():
    messages = [
        UserMessage(parts=["first request"], instructions="keep concise"),
        AssistantMessage(parts=["first reply"]),
        AssistantMessage(parts=[ToolCall(tool_name="parse_document", args={"id": 1}, tool_call_id="call-1")]),
        UserMessage(parts=[ToolResult(tool_name="parse_document", content="parsed ok", tool_call_id="call-1")]),
        UserMessage(parts=["recent request"]),
        AssistantMessage(parts=["recent reply"]),
    ]

    compacted = compact_context(
        messages,
        max_tokens=1,
        keep_recent=1,
        state_summary="大纲已生成：2 页 - 问题定义；执行路径",
    )

    assert len(compacted) == 3
    assert isinstance(compacted[0], UserMessage)
    assert compacted[0].instructions == "keep concise"
    assert "Condensed earlier context:" in compacted[0].parts[0]
    assert "Current pipeline state:" in compacted[0].parts[0]
    assert "tool calls: parse_document" in compacted[0].parts[0]
    assert compacted[1:] == messages[-2:]

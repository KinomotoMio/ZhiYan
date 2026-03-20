from app.models.slide import Slide
from app.services.generation.agentic.context import compact_context, summarize_state
from app.services.generation.agentic.types import AssistantMessage, ToolCall, UserMessage
from app.services.pipeline.graph import PipelineState


def test_summarize_state_empty():
    assert summarize_state(None) == "（尚未开始生成）"
    assert summarize_state(PipelineState()) == "（尚未开始生成）"


def test_summarize_state_populated():
    state = PipelineState(
        raw_content="原始内容",
        topic="测试主题",
        num_pages=4,
        job_id="job-1",
    )
    state.document_metadata = {
        "char_count": 1280,
        "estimated_tokens": 320,
        "heading_count": 6,
    }
    state.outline = {
        "items": [
            {"title": "开场"},
            {"title": "问题"},
            {"title": "方案"},
        ]
    }
    state.layout_selections = [
        {"slide_number": 1, "layout_id": "cover"},
        {"slide_number": 2, "layout_id": "bullet"},
    ]
    state.slides = [
        Slide(slide_id="slide-1", layout_type="cover", layout_id="cover", content_data={}),
        Slide(slide_id="slide-2", layout_type="bullet", layout_id="bullet", content_data={}),
    ]
    state.verification_issues = [
        {"tier": "hard", "message": "missing title"},
        {"severity": "warning", "message": "tight spacing"},
    ]

    summary = summarize_state(state)

    assert "文档已解析：1280 字符" in summary
    assert "约 320 tokens" in summary
    assert "6 个标题" in summary
    assert "大纲已生成：3 个章节 - 开场, 问题, 方案" in summary
    assert "布局已选择：2 页 - 1:cover, 2:bullet" in summary
    assert "幻灯片已生成：2 页" in summary
    assert "校验问题：1 个严重，1 个建议" in summary


def test_compact_context_no_compaction_path():
    messages = [
        UserMessage(parts=["短消息 1"]),
        AssistantMessage(parts=["短回复 1"]),
        UserMessage(parts=["短消息 2"]),
    ]

    compacted = compact_context(messages, max_tokens=10_000, keep_recent=2)

    assert compacted == messages


def test_compact_context_preserves_recent_messages():
    messages = []
    for idx in range(4):
        messages.append(UserMessage(parts=[f"旧消息 {idx} " + ("x" * 300)]))
        messages.append(AssistantMessage(parts=[f"旧回复 {idx} " + ("y" * 300), ToolCall(tool_name="parse_document", args={})]))

    recent_tail = messages[-2:]

    compacted = compact_context(messages, max_tokens=1, keep_recent=2)

    assert len(compacted) == 3
    assert isinstance(compacted[0], UserMessage)
    assert "旧上下文摘要" in compacted[0].parts[0]
    assert "旧消息 0" in compacted[0].parts[0]
    assert compacted[-2:] == recent_tail

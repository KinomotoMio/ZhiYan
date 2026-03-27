"""Slidev deck editor agent for whole-document revisions."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field


class SlidevDeckEditResult(BaseModel):
    assistant_reply: str
    should_update: bool = True
    markdown: str = ""
    selected_style_id: str | None = Field(None, alias="selectedStyleId")

    model_config = {"populate_by_name": True}


_agent = None


def get_slidev_deck_editor_agent():
    global _agent
    if _agent is None:
        from pydantic_ai import Agent

        from app.core.config import settings
        from app.core.model_resolver import resolve_model

        _agent = Agent(
            model=resolve_model(settings.strong_model),
            output_type=SlidevDeckEditResult,
            instructions=(
                "你是知演（ZhiYan）的 Slidev 改稿助手。\n"
                "Slidev 是 markdown-first 的演示框架，一份 deck 由全局 frontmatter 和多个用 --- 分隔的 slides 组成。\n"
                "你的任务是直接修改整份 Slidev markdown deck，而不是给建议。\n"
                "规则：\n"
                "- 当请求是改稿时，返回完整 deck markdown，不要只返回局部片段。\n"
                "- 保留 slide 顺序，除非用户明确要求增删或调序。\n"
                "- 默认保持当前 selected_style_id；只有用户明确要求改视觉方向时才允许切换。\n"
                "- 输出必须仍然是可被 slidev build 编译的 presentation markdown，而不是文章 markdown。\n"
                "- 如果用户只是提问而不是要求改稿，可以 should_update=false，并在 assistant_reply 中回答。\n"
                "- 回复使用中文。"
            ),
        )
    return _agent


async def edit_slidev_deck(
    *,
    message: str,
    action_hint: str,
    markdown: str,
    current_slide_index: int,
    slide_meta: dict | None,
    selected_style_id: str | None,
    history: list[dict[str, str]] | None = None,
) -> SlidevDeckEditResult:
    current_slide = None
    if isinstance(slide_meta, dict):
        slides = slide_meta.get("slides")
        if isinstance(slides, list) and 0 <= current_slide_index < len(slides):
            current_slide = slides[current_slide_index]

    prompt = (
        f"操作意图: {action_hint}\n"
        f"当前页索引: {current_slide_index}\n"
        f"当前 style preset: {selected_style_id or '未指定'}\n"
        f"当前页信息: {json.dumps(current_slide or {}, ensure_ascii=False)}\n"
        f"全部页面信息: {json.dumps(slide_meta or {}, ensure_ascii=False)}\n\n"
        f"最近对话: {json.dumps(history or [], ensure_ascii=False)}\n\n"
        f"用户消息:\n{message.strip()}\n\n"
        f"当前 Slidev deck:\n{markdown}"
    )
    result = await get_slidev_deck_editor_agent().run(prompt)
    return result.output

"""HTML deck editor agent for whole-document revisions."""

from __future__ import annotations

import json

from pydantic import BaseModel


class HtmlDeckEditResult(BaseModel):
    assistant_reply: str
    should_update: bool = True
    html: str = ""


_agent = None


def get_html_deck_editor_agent():
    global _agent
    if _agent is None:
        from pydantic_ai import Agent

        from app.core.config import settings
        from app.core.model_resolver import resolve_model

        _agent = Agent(
            model=resolve_model(settings.strong_model),
            output_type=HtmlDeckEditResult,
            instructions=(
                "你是知演（ZhiYan）的 HTML 演示改稿助手。\n"
                "你会直接修改一份 Reveal HTML deck，而不是给建议。\n"
                "规则：\n"
                "- 当请求是改稿时，返回完整、可直接播放的 HTML，不要只返回局部片段。\n"
                "- 保留 reveal 结构、保留每个 section 的顺序，除非用户明确要求增删或调序。\n"
                "- 尽量保持 data-slide-id 稳定；每个 section 都必须保留 data-slide-id 和 data-slide-title。\n"
                "- 可以重写页面内部结构、文案、样式，让页面更美观且更符合用户要求。\n"
                "- 如果用户只是提问而不是要求改稿，可以 should_update=false，并在 assistant_reply 中回答。\n"
                "- 回复使用中文。"
            ),
        )
    return _agent


async def edit_html_deck(
    *,
    message: str,
    action_hint: str,
    html_content: str,
    current_slide_index: int,
    slide_meta: dict | None,
    history: list[dict[str, str]] | None = None,
) -> HtmlDeckEditResult:
    current_slide = None
    if isinstance(slide_meta, dict):
        slides = slide_meta.get("slides")
        if isinstance(slides, list) and 0 <= current_slide_index < len(slides):
            current_slide = slides[current_slide_index]

    prompt = (
        f"操作意图: {action_hint}\n"
        f"当前页索引: {current_slide_index}\n"
        f"当前页信息: {json.dumps(current_slide or {}, ensure_ascii=False)}\n"
        f"全部页面信息: {json.dumps(slide_meta or {}, ensure_ascii=False)}\n\n"
        f"最近对话: {json.dumps(history or [], ensure_ascii=False)}\n\n"
        f"用户消息:\n{message.strip()}\n\n"
        f"当前 HTML deck:\n{html_content}"
    )
    result = await get_html_deck_editor_agent().run(prompt)
    return result.output

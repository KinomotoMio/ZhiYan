"""Chat API — SSE 流式对话 + 幻灯片修改"""

import copy
import json
import logging

from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.config import settings
from app.services.agents.html_deck_editor import edit_html_deck
from app.services.html_deck import normalize_html_deck
from app.services.sessions import session_store
from app.services.sessions.workspace import get_workspace_id_from_request

router = APIRouter()
logger = logging.getLogger(__name__)

ActionHint = Literal[
    "refresh_layout",
    "simplify",
    "add_detail",
    "enrich_visual",
    "change_theme",
    "free_text",
]

ACTION_HINT_LABELS: dict[ActionHint, str] = {
    "refresh_layout": "刷新布局",
    "simplify": "内容精简",
    "add_detail": "补充细节",
    "enrich_visual": "丰富视觉表达",
    "change_theme": "调整主题风格",
    "free_text": "自由对话",
}
VISIBLE_CONTENT_ACTIONS: set[ActionHint] = {
    "refresh_layout",
    "simplify",
    "add_detail",
    "enrich_visual",
    "change_theme",
}


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    messages: list[ChatMessage] = []
    session_id: str | None = None
    presentation_context: dict | None = None
    current_slide_index: int = 0
    action_hint: ActionHint = "free_text"


class HtmlDeckContext(BaseModel):
    title: str
    html_content: str
    slide_meta: dict[str, Any]


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    """流式对话 — SSE 响应，支持幻灯片修改"""
    slides: list[dict[str, Any]] = []
    if req.presentation_context:
        raw_slides = req.presentation_context.get("slides", [])
        if isinstance(raw_slides, list):
            slides = copy.deepcopy(raw_slides)

    history = req.messages[-20:] if req.messages else []
    dedup_applied = False
    if (
        history
        and history[-1].role == "user"
        and history[-1].content.strip() == req.message.strip()
    ):
        history = history[:-1]
        dedup_applied = True

    workspace_id = get_workspace_id_from_request(request)
    assistant_chunks: list[str] = []
    strict_tool_mode = req.action_hint != "free_text"
    provider = settings.strong_model.split(":", 1)[0] if settings.strong_model else ""
    html_context = _extract_html_context(req, slides)
    deps = None
    chat_agent = None
    message_history = []
    prompt = ""

    if html_context is None:
        from app.services.agents.chat_agent import ChatDeps, chat_agent as structured_chat_agent
        from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse
        from pydantic_ai.messages import TextPart, UserPromptPart

        deps = ChatDeps(
            slides=slides,
            current_slide_index=req.current_slide_index,
        )
        message_history = []
        for msg in history:
            if msg.role == "user":
                message_history.append(ModelRequest(parts=[UserPromptPart(content=msg.content)]))
            else:
                message_history.append(ModelResponse(parts=[TextPart(content=msg.content)]))
        prompt = _build_prompt(req, slides, force_tool=False)
        chat_agent = structured_chat_agent

    async def _run_once(current_prompt: str, run_deps) -> str:
        result = await chat_agent.run(
            current_prompt,
            deps=run_deps,
            message_history=message_history,
        )
        output = result.output
        if isinstance(output, str):
            return output.strip()
        return str(output).strip()

    async def event_stream():
        nonlocal deps
        no_op = False
        no_op_reason = ""
        assistant_text = ""
        modification_count = 0
        effective_modification_count = 0
        html_update: dict[str, Any] | None = None

        try:
            if html_context is not None:
                result = await edit_html_deck(
                    message=req.message,
                    action_hint=req.action_hint,
                    html_content=html_context.html_content,
                    current_slide_index=req.current_slide_index,
                    slide_meta=html_context.slide_meta,
                    history=[
                        {"role": msg.role, "content": msg.content}
                        for msg in history
                    ],
                )
                assistant_text = result.assistant_reply.strip()
                if assistant_text:
                    assistant_chunks.append(assistant_text)

                if result.should_update and result.html.strip():
                    normalized_html, _meta, normalized_presentation = normalize_html_deck(
                        html=result.html,
                        fallback_title=html_context.title,
                    )
                    html_update = {
                        "type": "html_update",
                        "html_content": normalized_html,
                        "presentation": normalized_presentation,
                        "modifications": [
                            {
                                "action": "update_html_deck",
                                "slide_index": max(0, req.current_slide_index),
                                "mode": "html",
                            }
                        ],
                    }
                    effective_modification_count = len(html_update["modifications"])
                elif strict_tool_mode:
                    no_op = True
                    no_op_reason = _build_no_op_reason(req.action_hint)

                assistant_text = "".join(assistant_chunks).strip()
                if no_op and strict_tool_mode:
                    assistant_text = f"未执行改稿：{no_op_reason}"
                if assistant_text:
                    text_data = json.dumps(
                        {"type": "text", "content": assistant_text},
                        ensure_ascii=False,
                    )
                    yield f"data: {text_data}\n\n"
            elif strict_tool_mode:
                assistant_text = await _run_once(prompt, deps)
                if assistant_text:
                    assistant_chunks.append(assistant_text)

                effective_modification_count = _count_effective_modifications(
                    req.action_hint,
                    deps.modifications if deps is not None else [],
                )
                if effective_modification_count == 0:
                    from app.services.agents.chat_agent import ChatDeps

                    retry_deps = ChatDeps(
                        slides=copy.deepcopy(slides),
                        current_slide_index=req.current_slide_index,
                    )
                    retry_prompt = _build_prompt(req, slides, force_tool=True)
                    retry_text = await _run_once(retry_prompt, retry_deps)
                    if retry_text:
                        assistant_chunks.clear()
                        assistant_chunks.append(retry_text)
                    retry_effective_count = _count_effective_modifications(
                        req.action_hint,
                        retry_deps.modifications,
                    )
                    if retry_effective_count > 0:
                        deps = retry_deps
                        effective_modification_count = retry_effective_count
                    else:
                        no_op = True
                        no_op_reason = _build_no_op_reason(req.action_hint)

                assistant_text = "".join(assistant_chunks).strip()
                if no_op and strict_tool_mode:
                    assistant_text = f"未执行改稿：{no_op_reason}"
                if assistant_text:
                    text_data = json.dumps(
                        {"type": "text", "content": assistant_text},
                        ensure_ascii=False,
                    )
                    yield f"data: {text_data}\n\n"
            else:
                async with chat_agent.run_stream(
                    prompt,
                    deps=deps,
                    message_history=message_history,
                ) as result:
                    async for chunk in result.stream_text(delta=True):
                        assistant_chunks.append(chunk)
                        data = json.dumps(
                            {"type": "text", "content": chunk},
                            ensure_ascii=False,
                        )
                        yield f"data: {data}\n\n"
                assistant_text = "".join(assistant_chunks).strip()
                effective_modification_count = _count_effective_modifications(
                    req.action_hint,
                    deps.modifications if deps is not None else [],
                )

            modification_count = (
                len(html_update.get("modifications") or [])
                if html_update is not None
                else len(deps.modifications if deps is not None else [])
            )
            if html_update is not None:
                yield f"data: {json.dumps(html_update, ensure_ascii=False)}\n\n"
            elif effective_modification_count > 0:
                mod_data = json.dumps(
                    {
                        "type": "slide_update",
                        "slides": deps.slides if deps is not None else [],
                        "modifications": [m.model_dump() for m in deps.modifications] if deps is not None else [],
                    },
                    ensure_ascii=False,
                )
                yield f"data: {mod_data}\n\n"
            elif strict_tool_mode:
                if not no_op:
                    no_op_reason = _build_no_op_reason(req.action_hint)
                no_op_data = json.dumps(
                    {
                        "type": "no_op",
                        "code": "NO_TOOL_MODIFICATION",
                        "reason": no_op_reason,
                    },
                    ensure_ascii=False,
                )
                yield f"data: {no_op_data}\n\n"

            logger.info(
                "chat_request_processed",
                extra={
                    "event": "chat_request_processed",
                    "action_hint": req.action_hint,
                    "history_count": len(history),
                    "dedup_applied": dedup_applied,
                    "modification_count": modification_count,
                    "effective_modification_count": effective_modification_count,
                    "no_op": no_op,
                    "model": settings.strong_model,
                    "provider": provider,
                },
            )

            if req.session_id:
                try:
                    await session_store.add_chat_message(
                        workspace_id=workspace_id,
                        session_id=req.session_id,
                        role="user",
                        content=req.message,
                        model_meta={
                            "phase": "editor",
                            "message_kind": "user_turn",
                            "action_hint": req.action_hint,
                        },
                    )
                    if assistant_text:
                        await session_store.add_chat_message(
                            workspace_id=workspace_id,
                            session_id=req.session_id,
                            role="assistant",
                            content=assistant_text,
                            model_meta={
                                "phase": "editor",
                                "message_kind": "assistant_reply",
                                "action_hint": req.action_hint,
                            },
                        )
                except Exception as e:
                    logger.warning("persist chat message failed: %s", e)

        except Exception as e:
            logger.error("Chat stream error: %s", e)
            data = json.dumps(
                {"type": "error", "content": f"处理消息时出现错误: {e}"},
                ensure_ascii=False,
            )
            yield f"data: {data}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _build_prompt(
    req: ChatRequest,
    slides: list[dict[str, Any]],
    *,
    force_tool: bool,
) -> str:
    context_parts: list[str] = []
    total_slides = len(slides)
    current_layout = ""
    if total_slides > 0:
        context_parts.append(f"演示文稿共 {total_slides} 页")
        idx = req.current_slide_index
        if 0 <= idx < total_slides:
            current_slide = slides[idx]
            current_layout = str(
                current_slide.get("layoutId")
                or current_slide.get("layoutType")
                or ""
            ).strip()
            context_parts.append(_summarize_current_slide(idx, current_slide))

    if req.action_hint != "free_text":
        hint_label = ACTION_HINT_LABELS.get(req.action_hint, req.action_hint)
        context_parts.append(f"操作意图：{hint_label}")
        context_parts.append("这是改稿请求，请优先通过工具直接修改 slides，而不是只给建议。")
        context_parts.append("以当前页面快照为唯一事实来源；历史对话可能包含未应用预览，不能视为已生效改动。")
        if req.action_hint in VISIBLE_CONTENT_ACTIONS:
            context_parts.append(
                "本次必须优先修改页面可见内容（标题/contentData），禁止只修改演讲者注释。"
            )
            if current_layout == "two-column-compare":
                context_parts.append(
                    "当前页是 two-column-compare，补充细节时请优先调用 update_two_column_compare 修改 left/right 要点。"
                )
        if force_tool:
            context_parts.append(
                "强制要求：本轮必须至少调用一次修改工具并产出至少一条修改记录。"
            )
            if req.action_hint in VISIBLE_CONTENT_ACTIONS:
                context_parts.append(
                    "强制要求：必须至少产生一条非演讲者注释修改（例如标题、正文要点、布局字段）。"
                )

    context_parts.append(f"用户消息：{req.message.strip()}")
    return "\n\n".join(context_parts)


def _summarize_current_slide(index: int, slide: dict[str, Any]) -> str:
    layout = slide.get("layoutId") or slide.get("layoutType") or "unknown"
    title = _extract_title(slide)
    summary = _summarize_content_data(slide.get("contentData"))
    return (
        f"用户当前查看第 {index + 1} 页（布局: {layout}，标题: {title or '未命名'}，"
        f"内容摘要: {summary}）"
    )


def _summarize_content_data(content_data: Any) -> str:
    if not isinstance(content_data, dict):
        return "无结构化内容"

    fields: list[str] = []
    for key, value in content_data.items():
        if str(key).startswith("_"):
            continue
        if isinstance(value, list):
            fields.append(f"{key}:{len(value)}项")
        elif isinstance(value, dict):
            sub_keys = list(value.keys())[:3]
            fields.append(f"{key}:对象({','.join(str(k) for k in sub_keys)})")
        elif isinstance(value, str):
            text = value.strip()
            if text:
                fields.append(f"{key}:{text[:24]}")
        elif isinstance(value, (int, float, bool)):
            fields.append(f"{key}:{value}")
        if len(fields) >= 6:
            break

    if not fields:
        return "字段为空"
    return "；".join(fields)


def _extract_title(slide: dict[str, Any]) -> str:
    content_data = slide.get("contentData")
    if isinstance(content_data, dict):
        raw_title = content_data.get("title")
        if isinstance(raw_title, str) and raw_title.strip():
            return raw_title.strip()
    for comp in slide.get("components", []):
        if comp.get("role") == "title":
            return comp.get("content", "")
    return ""


def _count_effective_modifications(action_hint: ActionHint, modifications: list[Any]) -> int:
    if not modifications:
        return 0
    if action_hint not in VISIBLE_CONTENT_ACTIONS:
        return len(modifications)
    return sum(
        1
        for mod in modifications
        if getattr(mod, "action", None) != "update_notes"
    )


def _build_no_op_reason(action_hint: ActionHint) -> str:
    if action_hint in VISIBLE_CONTENT_ACTIONS:
        return "本次未产生页面可见内容改动（仅建议或注释不计入），请指定要修改的标题/要点。"
    return "本次请求未触发可执行修改，请指定更明确的改动目标。"


def _extract_html_context(
    req: ChatRequest,
    slides: list[dict[str, Any]],
) -> HtmlDeckContext | None:
    if not isinstance(req.presentation_context, dict):
        return None
    if str(req.presentation_context.get("output_mode") or "").strip() != "html":
        return None
    html_content = str(req.presentation_context.get("html_content") or "").strip()
    if not html_content:
        return None
    title = str(req.presentation_context.get("title") or "新演示文稿").strip() or "新演示文稿"
    slide_meta = {
        "title": title,
        "slides": [
            {
                "index": index,
                "slide_id": str(slide.get("slideId") or f"slide-{index + 1}"),
                "title": _extract_title(slide) or f"第 {index + 1} 页",
            }
            for index, slide in enumerate(slides)
            if isinstance(slide, dict)
        ],
    }
    return HtmlDeckContext(title=title, html_content=html_content, slide_meta=slide_meta)

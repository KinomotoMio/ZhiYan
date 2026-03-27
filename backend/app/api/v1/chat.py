"""Chat API — SSE 流式对话 + 幻灯片修改"""

import copy
import json
import logging
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.core.config import settings
from app.services.agents.editor_loop import EditorLoopRequest, editor_loop_service
from app.services.sessions import session_store
from app.services.sessions.workspace import get_workspace_id_from_request
from app.services.slidev import get_slidev_preview_root

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


def _resolve_preview_asset(preview_id: str, asset_path: str) -> Path:
    root = get_slidev_preview_root(preview_id)
    candidate = (root / "dist" / asset_path).resolve()
    if candidate != root / "dist" and (root / "dist") not in candidate.parents:
        raise FileNotFoundError(asset_path)
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(asset_path)
    return candidate


@router.get("/slidev-previews/{preview_id}")
async def get_slidev_preview_entry(preview_id: str):
    path = _resolve_preview_asset(preview_id, "index.html")
    return FileResponse(path, media_type="text/html")


@router.get("/slidev-previews/{preview_id}/{asset_path:path}")
async def get_slidev_preview_asset(preview_id: str, asset_path: str):
    path = _resolve_preview_asset(preview_id, asset_path)
    return FileResponse(path)


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
    strict_tool_mode = req.action_hint != "free_text"
    provider = settings.strong_model.split(":", 1)[0] if settings.strong_model else ""
    presentation_context = req.presentation_context if isinstance(req.presentation_context, dict) else {}
    output_mode = str(presentation_context.get("output_mode") or "structured").strip() or "structured"
    html_content = str(presentation_context.get("html_content") or "").strip() or None
    slidev_markdown = str(presentation_context.get("slidev_markdown") or "").strip() or None
    raw_slidev_meta = presentation_context.get("slidev_meta")
    slidev_meta = dict(raw_slidev_meta) if isinstance(raw_slidev_meta, dict) else None
    selected_style_id = str(presentation_context.get("selected_style_id") or "").strip() or None
    presentation_title = str(presentation_context.get("title") or "新演示文稿").strip() or "新演示文稿"

    async def event_stream():
        no_op = False
        no_op_reason = ""
        assistant_text = ""
        modification_count = 0
        effective_modification_count = 0
        slide_update: dict[str, Any] | None = None
        html_update: dict[str, Any] | None = None
        slidev_update: dict[str, Any] | None = None

        try:
            outcome = await editor_loop_service.run(
                EditorLoopRequest(
                    workspace_id=workspace_id,
                    session_id=req.session_id,
                    message=req.message,
                    action_hint=req.action_hint,
                    current_slide_index=req.current_slide_index,
                    presentation_title=presentation_title,
                    slides=slides,
                    output_mode=output_mode,
                    html_content=html_content,
                    slidev_markdown=slidev_markdown,
                    slidev_meta=slidev_meta,
                    selected_style_id=selected_style_id,
                    history=[
                        {"role": msg.role, "content": msg.content}
                        for msg in history
                    ],
                )
            )
            assistant_text = outcome.assistant_reply.strip()
            modification_count = outcome.modification_count
            effective_modification_count = _count_effective_modifications(
                req.action_hint,
                outcome.modifications,
            )
            if output_mode == "html" and outcome.html_content and outcome.normalized_presentation:
                html_update = {
                    "type": "html_update",
                    "html_content": outcome.html_content,
                    "presentation": outcome.normalized_presentation,
                    "modifications": [item.model_dump(mode="json") for item in outcome.modifications],
                }
            elif (
                output_mode == "slidev"
                and outcome.slidev_markdown
                and outcome.slidev_meta
                and outcome.slidev_preview_url
                and outcome.normalized_presentation
            ):
                slidev_update = {
                    "type": "slidev_update",
                    "markdown": outcome.slidev_markdown,
                    "meta": outcome.slidev_meta,
                    "presentation": outcome.normalized_presentation,
                    "selected_style_id": outcome.selected_style_id,
                    "preview_url": outcome.slidev_preview_url,
                    "modifications": [item.model_dump(mode="json") for item in outcome.modifications],
                }
            elif outcome.modifications:
                slide_update = {
                    "type": "slide_update",
                    "slides": outcome.slides,
                    "modifications": [item.model_dump(mode="json") for item in outcome.modifications],
                }

            if strict_tool_mode and effective_modification_count == 0:
                no_op = True
                no_op_reason = _build_no_op_reason(req.action_hint)
                assistant_text = f"未执行改稿：{no_op_reason}"

            for event in outcome.events:
                payload = json.dumps(event, ensure_ascii=False)
                yield f"data: {payload}\n\n"

            if assistant_text:
                text_data = json.dumps(
                    {"type": "text", "content": assistant_text},
                    ensure_ascii=False,
                )
                yield f"data: {text_data}\n\n"
            if html_update is not None and not no_op:
                yield f"data: {json.dumps(html_update, ensure_ascii=False)}\n\n"
            elif slidev_update is not None and not no_op:
                yield f"data: {json.dumps(slidev_update, ensure_ascii=False)}\n\n"
            elif slide_update is not None and effective_modification_count > 0:
                yield f"data: {json.dumps(slide_update, ensure_ascii=False)}\n\n"
            elif strict_tool_mode:
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

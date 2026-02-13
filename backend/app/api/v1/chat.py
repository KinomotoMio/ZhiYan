"""Chat API — SSE 流式对话 + 幻灯片修改"""

import copy
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.sessions import session_store
from app.services.sessions.workspace import get_workspace_id_from_request

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    messages: list[ChatMessage] = []
    session_id: str | None = None
    presentation_context: dict | None = None
    current_slide_index: int = 0


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    """流式对话 — SSE 响应，支持幻灯片修改"""
    from app.services.agents.chat_agent import chat_agent, ChatDeps
    from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse
    from pydantic_ai.messages import UserPromptPart, TextPart

    # 构建 slides 深拷贝（供 tools 修改）
    slides = []
    if req.presentation_context:
        slides = copy.deepcopy(req.presentation_context.get("slides", []))

    deps = ChatDeps(
        slides=slides,
        current_slide_index=req.current_slide_index,
    )

    # 构建带上下文的 user prompt
    context_parts = []
    if req.presentation_context:
        total_slides = len(slides)
        context_parts.append(f"演示文稿共 {total_slides} 页")
        idx = req.current_slide_index
        if 0 <= idx < total_slides:
            current = slides[idx]
            context_parts.append(
                f"用户当前查看第 {idx + 1} 页（布局: {current.get('layoutType', 'unknown')}，"
                f"标题: {_extract_title(current)}）"
            )

    context_parts.append(f"用户消息：{req.message}")
    prompt = "\n\n".join(context_parts)

    # 构建对话历史（最近 20 条）
    message_history: list[ModelMessage] = []
    history = req.messages[-20:] if req.messages else []
    for msg in history:
        if msg.role == "user":
            message_history.append(ModelRequest(parts=[UserPromptPart(content=msg.content)]))
        else:
            message_history.append(ModelResponse(parts=[TextPart(content=msg.content)]))
    workspace_id = get_workspace_id_from_request(request)
    assistant_chunks: list[str] = []

    async def event_stream():
        try:
            async with chat_agent.run_stream(
                prompt,
                deps=deps,
                message_history=message_history,
            ) as result:
                async for chunk in result.stream_text():
                    assistant_chunks.append(chunk)
                    data = json.dumps({"type": "text", "content": chunk}, ensure_ascii=False)
                    yield f"data: {data}\n\n"

            # 流结束后，检查是否有幻灯片修改
            if deps.modifications:
                mod_data = json.dumps({
                    "type": "slide_update",
                    "slides": deps.slides,
                    "modifications": [m.model_dump() for m in deps.modifications],
                }, ensure_ascii=False)
                yield f"data: {mod_data}\n\n"

            if req.session_id:
                try:
                    await session_store.add_chat_message(
                        workspace_id=workspace_id,
                        session_id=req.session_id,
                        role="user",
                        content=req.message,
                    )
                    assistant_text = "".join(assistant_chunks).strip()
                    if assistant_text:
                        await session_store.add_chat_message(
                            workspace_id=workspace_id,
                            session_id=req.session_id,
                            role="assistant",
                            content=assistant_text,
                        )
                except Exception as e:
                    logger.warning("persist chat message failed: %s", e)

        except Exception as e:
            logger.error("Chat stream error: %s", e)
            data = json.dumps({"type": "error", "content": f"处理消息时出现错误: {e}"}, ensure_ascii=False)
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


def _extract_title(slide: dict) -> str:
    for comp in slide.get("components", []):
        if comp.get("role") == "title":
            return comp.get("content", "")
    return ""

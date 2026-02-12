"""Chat API — SSE 流式对话"""

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    presentation_context: dict | None = None
    current_slide_index: int = 0


@router.post("/chat")
async def chat(req: ChatRequest):
    """流式对话 — SSE 响应"""
    from app.services.agents.chat_agent import chat_agent

    # 构建 prompt，注入幻灯片上下文
    context_parts = [f"用户消息：{req.message}"]

    if req.presentation_context:
        slides = req.presentation_context.get("slides", [])
        current_idx = req.current_slide_index
        if 0 <= current_idx < len(slides):
            current = slides[current_idx]
            context_parts.insert(0, (
                f"当前查看的幻灯片（第 {current_idx + 1} 页）：\n"
                f"标题: {_extract_title(current)}\n"
                f"布局: {current.get('layoutType', 'unknown')}\n"
                f"内容摘要: {_extract_body(current)[:200]}"
            ))
        context_parts.insert(0, f"演示文稿共 {len(slides)} 页")

    prompt = "\n\n".join(context_parts)

    async def event_stream():
        try:
            async with chat_agent.run_stream(prompt) as result:
                async for chunk in result.stream_text():
                    data = json.dumps({"type": "text", "content": chunk}, ensure_ascii=False)
                    yield f"data: {data}\n\n"
        except Exception as e:
            logger.error("Chat stream error: %s", e)
            data = json.dumps({"type": "text", "content": f"抱歉，处理消息时出现错误: {e}"}, ensure_ascii=False)
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
    """从 slide dict 中提取标题"""
    for comp in slide.get("components", []):
        if comp.get("role") == "title":
            return comp.get("content", "")
    return ""


def _extract_body(slide: dict) -> str:
    """从 slide dict 中提取正文"""
    for comp in slide.get("components", []):
        if comp.get("role") == "body":
            return comp.get("content", "")
    return ""

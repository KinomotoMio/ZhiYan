"""POST /api/v1/tts — 文本转语音"""

import logging
import httpx

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from app.utils.security import get_safe_httpx_client

router = APIRouter(prefix="/tts", tags=["tts"])
logger = logging.getLogger(__name__)


class TTSRequest(BaseModel):
    text: str
    voice: str | None = None


@router.post("")
async def text_to_speech(req: TTSRequest):
    """调用 OpenAI TTS API 生成语音"""
    from app.core.config import settings

    if not settings.openai_api_key:
        raise HTTPException(status_code=400, detail="未配置 OpenAI API Key，无法使用 TTS 功能")

    if not req.text.strip():
        raise HTTPException(status_code=422, detail="文本内容不能为空")

    # 截断过长文本（OpenAI TTS 限制 4096 字符）
    text = req.text[:4096]
    voice = req.voice or settings.tts_voice

    try:
        async with get_safe_httpx_client(timeout=30) as client:
            resp = await client.post(
                f"{settings.openai_base_url}/audio/speech",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.tts_model,
                    "input": text,
                    "voice": voice,
                },
            )

        if resp.status_code != 200:
            logger.warning("TTS API error: %d %s", resp.status_code, resp.text[:200])
            raise HTTPException(
                status_code=502,
                detail=f"TTS 服务返回错误: {resp.status_code}",
            )

        return Response(
            content=resp.content,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline"},
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="TTS 服务超时")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("TTS failed: %s", e)
        raise HTTPException(status_code=500, detail=f"TTS 生成失败: {e}")

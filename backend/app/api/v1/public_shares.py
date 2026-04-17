"""Public share playback APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services.sessions import session_store

router = APIRouter(prefix="/public/shares", tags=["public-shares"])

_NO_STORE_HEADERS = {"Cache-Control": "no-store"}


class PublicSharePlaybackResponse(BaseModel):
    title: str
    output_mode: str = Field(alias="outputMode")
    presentation: dict[str, Any] | None = None


async def _resolve_shared_session(token: str) -> dict:
    normalized = token.strip()
    if not normalized:
        raise HTTPException(status_code=404, detail="分享链接无效或已失效")

    share = await session_store.get_share_link_by_token(normalized)
    if not share:
        raise HTTPException(status_code=404, detail="分享链接无效或已失效")
    return share


async def _resolve_shared_presentation(token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    share = await _resolve_shared_session(token)
    latest = await session_store.get_latest_presentation(
        str(share["workspace_id"]),
        str(share["session_id"]),
    )
    if not latest:
        raise HTTPException(status_code=404, detail="当前分享暂无可播放内容")
    return share, latest


@router.get("/{token}", response_model=PublicSharePlaybackResponse)
async def get_public_share_playback(token: str):
    _share, latest = await _resolve_shared_presentation(token)
    output_mode = str(latest.get("output_mode") or "slidev")
    presentation = latest.get("presentation")
    response = PublicSharePlaybackResponse(
        title=str((presentation or {}).get("title") or "新演示文稿"),
        outputMode=output_mode,
        presentation=presentation,
    )
    return JSONResponse(
        content=response.model_dump(mode="json", by_alias=True),
        headers=_NO_STORE_HEADERS,
    )

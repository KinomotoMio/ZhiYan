"""Public share playback APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
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


@router.get("/{token}", response_model=PublicSharePlaybackResponse)
async def get_public_share_playback(token: str):
    share = await _resolve_shared_session(token)
    latest = await session_store.get_latest_presentation(
        str(share["workspace_id"]),
        str(share["session_id"]),
    )
    if not latest:
        raise HTTPException(status_code=404, detail="当前分享暂无可播放内容")

    output_mode = str(latest.get("output_mode") or "structured")
    presentation = latest.get("presentation")
    response = PublicSharePlaybackResponse(
        title=str((presentation or {}).get("title") or "新演示文稿"),
        outputMode=output_mode,
        presentation=presentation if output_mode != "html" else None,
    )
    return JSONResponse(
        content=response.model_dump(mode="json", by_alias=True),
        headers=_NO_STORE_HEADERS,
    )


@router.get("/{token}/html")
async def get_public_share_html(token: str):
    share = await _resolve_shared_session(token)
    latest = await session_store.get_latest_presentation(
        str(share["workspace_id"]),
        str(share["session_id"]),
    )
    if not latest:
        raise HTTPException(status_code=404, detail="当前分享暂无可播放内容")
    if str(latest.get("output_mode") or "structured") != "html":
        raise HTTPException(status_code=404, detail="当前分享暂无 HTML 演示稿")

    html_deck = await session_store.get_latest_html_deck(
        str(share["workspace_id"]),
        str(share["session_id"]),
    )
    if not html_deck:
        raise HTTPException(status_code=404, detail="当前分享暂无 HTML 演示稿")

    html, _meta = html_deck
    return PlainTextResponse(
        content=html,
        media_type="text/html",
        headers=_NO_STORE_HEADERS,
    )

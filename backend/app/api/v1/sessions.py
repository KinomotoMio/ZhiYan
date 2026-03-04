"""Session APIs — workspace-scoped session management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.models.session import (
    ChatRecord,
    LatestPresentationWriteRequest,
    SessionDetail,
    SessionSummary,
    SnapshotMeta,
)
from app.models.source import SourceMeta
from app.services.sessions import session_store
from app.services.sessions.workspace import get_workspace_id_from_request

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    title: str = "未命名会话"


class UpdateSessionRequest(BaseModel):
    title: str | None = None
    is_pinned: bool | None = None
    status: str | None = None
    archived: bool | None = None


class SnapshotRequest(BaseModel):
    snapshot_label: str = "手动快照"
    presentation: dict | None = None


class SessionChatWriteRequest(BaseModel):
    role: str
    content: str
    model_meta: dict = Field(default_factory=dict)


def _ensure_session_id(value: str) -> str:
    sid = value.strip()
    if not sid:
        raise HTTPException(status_code=400, detail="缺少 session_id")
    return sid


async def _assert_session_access(workspace_id: str, session_id: str) -> None:
    try:
        await session_store.get_session(workspace_id, session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("", response_model=SessionSummary)
async def create_session(req: CreateSessionRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    await session_store.ensure_workspace(workspace_id)
    session = await session_store.create_session(workspace_id, req.title or "未命名会话")
    return SessionSummary.model_validate(session)


@router.get("", response_model=list[SessionSummary])
async def list_sessions(
    request: Request,
    q: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    workspace_id = get_workspace_id_from_request(request)
    await session_store.ensure_workspace(workspace_id)
    sessions = await session_store.list_sessions(workspace_id, q=q, limit=limit, offset=offset)
    return [SessionSummary.model_validate(item) for item in sessions]


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session_detail(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    try:
        session = await session_store.get_session(workspace_id, sid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await session_store.touch_session(workspace_id, sid)
    sources = await session_store.list_sources(workspace_id, sid)
    chats = await session_store.list_chat_messages(workspace_id, sid)
    latest = await session_store.get_latest_presentation(workspace_id, sid)
    latest_generation_job = await session_store.get_latest_generation_job(workspace_id, sid)
    return SessionDetail(
        session=SessionSummary.model_validate(session),
        sources=[SourceMeta.model_validate(item) for item in sources],
        chat_messages=[ChatRecord.model_validate(item) for item in chats],
        latest_presentation=latest,
        latest_generation_job=latest_generation_job,
    )


@router.patch("/{session_id}", response_model=SessionSummary)
async def patch_session(session_id: str, req: UpdateSessionRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    try:
        session = await session_store.update_session(
            workspace_id,
            sid,
            title=req.title,
            is_pinned=req.is_pinned,
            status=req.status,
            archived=req.archived,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return SessionSummary.model_validate(session)


@router.delete("/{session_id}")
async def delete_session(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await session_store.delete_session(workspace_id, sid)
    return {"ok": True}


@router.get("/{session_id}/sources", response_model=list[SourceMeta])
async def list_session_sources(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    sources = await session_store.list_sources(workspace_id, sid)
    return [SourceMeta.model_validate(item) for item in sources]


@router.get("/{session_id}/sources/{source_id}/content")
async def get_session_source_content(session_id: str, source_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    try:
        content = await session_store.get_source_content(workspace_id, sid, source_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"content": content}


class LinkSourcesRequest(BaseModel):
    source_ids: list[str]


@router.post("/{session_id}/sources/link")
async def link_sources_to_session(session_id: str, req: LinkSourcesRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    for source_id in req.source_ids:
        try:
            await session_store.link_source_to_session(
                session_id=sid,
                source_id=source_id,
                workspace_id=workspace_id,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except PermissionError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
    return {"ok": True}


@router.delete("/{session_id}/sources/{source_id}/link")
async def unlink_source_from_session(session_id: str, source_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    await session_store.unlink_source_from_session(sid, source_id)
    return {"ok": True}


@router.get("/{session_id}/chat", response_model=list[ChatRecord])
async def list_session_chat(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    records = await session_store.list_chat_messages(workspace_id, sid, limit=300)
    return [ChatRecord.model_validate(item) for item in records]


@router.post("/{session_id}/chat", response_model=ChatRecord)
async def add_session_chat(session_id: str, req: SessionChatWriteRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    try:
        await session_store.add_chat_message(
            workspace_id=workspace_id,
            session_id=sid,
            role=req.role,
            content=req.content,
            model_meta=req.model_meta,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    records = await session_store.list_chat_messages(
        workspace_id, sid, limit=1, newest_first=True
    )
    if not records:
        raise HTTPException(status_code=500, detail="消息保存失败")
    return ChatRecord.model_validate(records[0])


@router.get("/{session_id}/presentations/latest")
async def get_latest_presentation(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    latest = await session_store.get_latest_presentation(workspace_id, sid)
    if not latest:
        raise HTTPException(status_code=404, detail="当前会话暂无演示稿")
    return latest


@router.put("/{session_id}/presentations/latest", response_model=SnapshotMeta)
async def save_latest_presentation(
    session_id: str,
    req: LatestPresentationWriteRequest,
    request: Request,
):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    saved = await session_store.save_presentation(
        session_id=sid,
        payload=req.presentation,
        is_snapshot=False,
        snapshot_label=None,
    )
    return SnapshotMeta.model_validate(saved)


@router.post("/{session_id}/snapshots", response_model=SnapshotMeta)
async def create_snapshot(session_id: str, req: SnapshotRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    try:
        snapshot = await session_store.create_snapshot(
            workspace_id=workspace_id,
            session_id=sid,
            snapshot_label=req.snapshot_label,
            payload=req.presentation,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return SnapshotMeta.model_validate(snapshot)

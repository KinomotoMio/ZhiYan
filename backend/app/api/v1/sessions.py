"""Session APIs — workspace-scoped session management."""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from app.models.session import ChatRecord, SessionDetail, SessionSummary, SnapshotMeta
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


class UrlRequest(BaseModel):
    url: str


class TextRequest(BaseModel):
    name: str
    content: str


class SnapshotRequest(BaseModel):
    snapshot_label: str = "手动快照"
    presentation: dict | None = None


class SessionChatWriteRequest(BaseModel):
    role: str
    content: str
    model_meta: dict = Field(default_factory=dict)


def _snippet(text: str, max_len: int = 200) -> str:
    content = text.strip()
    if len(content) <= max_len:
        return content
    return content[:max_len] + "..."


def _sync_parse_file(path: Path) -> str:
    from markitdown import MarkItDown

    from app.services.document.parser import normalize_markdown

    converter = MarkItDown()
    result = converter.convert(str(path))
    return normalize_markdown(result.text_content)


async def _save_and_parse_file(source_id: str, filename: str, file_bytes: bytes) -> tuple[str, str]:
    file_dir = session_store.uploads_dir / source_id
    file_dir.mkdir(parents=True, exist_ok=True)
    file_path = file_dir / filename
    await asyncio.to_thread(file_path.write_bytes, file_bytes)
    content = await asyncio.to_thread(_sync_parse_file, file_path)
    return str(file_path), content


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
    return SessionDetail(
        session=SessionSummary.model_validate(session),
        sources=[SourceMeta.model_validate(item) for item in sources],
        chat_messages=[ChatRecord.model_validate(item) for item in chats],
        latest_presentation=latest,
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


@router.post("/{session_id}/sources/upload", response_model=SourceMeta)
async def upload_source(session_id: str, request: Request, file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    source_id = f"src-{uuid4().hex[:16]}"
    file_bytes = await file.read()
    try:
        storage_path, parsed_content = await _save_and_parse_file(
            source_id=source_id,
            filename=file.filename,
            file_bytes=file_bytes,
        )
        from app.models.source import detect_file_category
        from app.services.document.parser import estimate_tokens

        meta = await session_store.create_source(
            session_id=sid,
            source_type="file",
            name=file.filename,
            file_category=detect_file_category(file.filename).value,
            size=len(file_bytes),
            status="ready",
            preview_snippet=_snippet(parsed_content),
            storage_path=storage_path,
            parsed_content=parsed_content,
            metadata={"estimated_tokens": estimate_tokens(parsed_content)},
            source_id=source_id,
        )
    except Exception as e:
        meta = await session_store.create_source(
            session_id=sid,
            source_type="file",
            name=file.filename,
            file_category=None,
            size=len(file_bytes),
            status="error",
            preview_snippet=None,
            storage_path=None,
            parsed_content=None,
            metadata={},
            error=str(e),
            source_id=source_id,
        )
    return SourceMeta.model_validate(meta)


@router.post("/{session_id}/sources/url", response_model=SourceMeta)
async def add_url_source(session_id: str, req: UrlRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    source_id = f"src-{uuid4().hex[:16]}"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(req.url)
            resp.raise_for_status()
        parsed = urlparse(req.url)
        filename = Path(parsed.path).name or "page.html"
        storage_path, parsed_content = await _save_and_parse_file(
            source_id=source_id,
            filename=filename,
            file_bytes=resp.content,
        )
        from app.services.document.parser import estimate_tokens

        meta = await session_store.create_source(
            session_id=sid,
            source_type="url",
            name=req.url,
            file_category=None,
            size=len(resp.content),
            status="ready",
            preview_snippet=_snippet(parsed_content),
            storage_path=storage_path,
            parsed_content=parsed_content,
            metadata={"estimated_tokens": estimate_tokens(parsed_content)},
            source_id=source_id,
        )
    except Exception as e:
        meta = await session_store.create_source(
            session_id=sid,
            source_type="url",
            name=req.url,
            file_category=None,
            size=None,
            status="error",
            preview_snippet=None,
            storage_path=None,
            parsed_content=None,
            metadata={},
            error=str(e),
            source_id=source_id,
        )
    return SourceMeta.model_validate(meta)


@router.post("/{session_id}/sources/text", response_model=SourceMeta)
async def add_text_source(session_id: str, req: TextRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    from app.services.document.parser import estimate_tokens

    meta = await session_store.create_source(
        session_id=sid,
        source_type="text",
        name=req.name,
        file_category="text",
        size=len(req.content.encode("utf-8")),
        status="ready",
        preview_snippet=_snippet(req.content),
        storage_path=None,
        parsed_content=req.content,
        metadata={"estimated_tokens": estimate_tokens(req.content)},
    )
    return SourceMeta.model_validate(meta)


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


@router.delete("/{session_id}/sources/{source_id}")
async def delete_session_source(session_id: str, source_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    deleted = await session_store.delete_source(workspace_id, sid, source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="来源不存在")
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

"""Workspace-level source (素材库) APIs."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from app.models.source import SourceMeta
from app.services.sessions import session_store
from app.services.sessions.workspace import get_workspace_id_from_request
from app.utils.security import (
    INVALID_UPLOAD_FILENAME_ERROR,
    build_safe_upload_path,
    get_safe_httpx_client,
    sanitize_upload_filename,
)

router = APIRouter(prefix="/workspace/sources", tags=["workspace-sources"])


class UrlRequest(BaseModel):
    url: str


class TextRequest(BaseModel):
    name: str
    content: str


class BulkDeleteRequest(BaseModel):
    source_ids: list[str]


def _snippet(text: str, max_len: int = 200) -> str:
    content = text.strip()
    if len(content) <= max_len:
        return content
    return content[:max_len] + "..."


def _sync_parse_file(path: Path) -> str:
    from app.services.document.parser import (
        create_markitdown_converter,
        normalize_markdown,
    )

    converter = create_markitdown_converter()
    result = converter.convert(str(path))
    return normalize_markdown(result.text_content)


async def _save_and_parse_file(source_id: str, filename: str, file_bytes: bytes) -> tuple[str, str]:
    safe_filename = sanitize_upload_filename(filename)
    file_dir = session_store.uploads_dir / source_id
    file_dir.mkdir(parents=True, exist_ok=True)
    file_path = build_safe_upload_path(file_dir, safe_filename)
    await asyncio.to_thread(file_path.write_bytes, file_bytes)
    content = await asyncio.to_thread(_sync_parse_file, file_path)
    return str(file_path), content


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _hash_text(payload: str) -> str:
    return _hash_bytes(payload.encode("utf-8"))


@router.get("", response_model=list[SourceMeta])
async def list_workspace_sources(
    request: Request,
    q: str = Query(default=""),
    source_type: str | None = Query(default=None, alias="type"),
    status: str | None = Query(default=None),
    sort: str = Query(default="created_desc"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    if sort not in {"created_desc", "created_asc", "name_asc", "name_desc", "linked_desc"}:
        raise HTTPException(status_code=400, detail="无效的 sort 参数")
    workspace_id = get_workspace_id_from_request(request)
    await session_store.ensure_workspace(workspace_id)
    sources = await session_store.list_workspace_sources(
        workspace_id,
        q=q,
        source_type=source_type,
        status=status,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return [SourceMeta.model_validate(item) for item in sources]


@router.post("/upload", response_model=SourceMeta)
async def upload_workspace_source(request: Request, file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    try:
        safe_filename = sanitize_upload_filename(file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=INVALID_UPLOAD_FILENAME_ERROR) from e

    workspace_id = get_workspace_id_from_request(request)
    await session_store.ensure_workspace(workspace_id)
    source_id = f"src-{uuid4().hex[:16]}"
    file_bytes = await file.read()
    content_hash = _hash_bytes(file_bytes)

    deduped = await session_store.get_workspace_source_by_hash(workspace_id, content_hash)
    if deduped:
        deduped["deduped"] = True
        return SourceMeta.model_validate(deduped)

    try:
        storage_path, parsed_content = await _save_and_parse_file(
            source_id=source_id, filename=safe_filename, file_bytes=file_bytes,
        )
        from app.models.source import detect_file_category
        from app.services.document.parser import estimate_tokens

        meta = await session_store.create_workspace_source(
            workspace_id=workspace_id,
            source_type="file",
            name=safe_filename,
            file_category=detect_file_category(safe_filename).value,
            size=len(file_bytes),
            status="ready",
            content_hash=content_hash,
            preview_snippet=_snippet(parsed_content),
            storage_path=storage_path,
            parsed_content=parsed_content,
            metadata={"estimated_tokens": estimate_tokens(parsed_content)},
            source_id=source_id,
        )
    except Exception as e:
        meta = await session_store.create_workspace_source(
            workspace_id=workspace_id,
            source_type="file",
            name=safe_filename,
            file_category=None,
            size=len(file_bytes),
            status="error",
            content_hash=content_hash,
            preview_snippet=None,
            storage_path=None,
            parsed_content=None,
            metadata={},
            error=str(e),
            source_id=source_id,
        )
    return SourceMeta.model_validate(meta)


@router.post("/url", response_model=SourceMeta)
async def add_workspace_url_source(req: UrlRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    await session_store.ensure_workspace(workspace_id)
    source_id = f"src-{uuid4().hex[:16]}"
    try:
        async with get_safe_httpx_client(follow_redirects=True, timeout=30) as client:
            resp = await client.get(req.url)
            resp.raise_for_status()
        content_hash = _hash_bytes(resp.content)
        deduped = await session_store.get_workspace_source_by_hash(workspace_id, content_hash)
        if deduped:
            deduped["deduped"] = True
            return SourceMeta.model_validate(deduped)
        parsed = urlparse(req.url)
        filename = Path(parsed.path).name or "page.html"
        storage_path, parsed_content = await _save_and_parse_file(
            source_id=source_id, filename=filename, file_bytes=resp.content,
        )
        from app.services.document.parser import estimate_tokens

        meta = await session_store.create_workspace_source(
            workspace_id=workspace_id,
            source_type="url",
            name=req.url,
            file_category=None,
            size=len(resp.content),
            status="ready",
            content_hash=content_hash,
            preview_snippet=_snippet(parsed_content),
            storage_path=storage_path,
            parsed_content=parsed_content,
            metadata={"estimated_tokens": estimate_tokens(parsed_content)},
            source_id=source_id,
        )
    except Exception as e:
        meta = await session_store.create_workspace_source(
            workspace_id=workspace_id,
            source_type="url",
            name=req.url,
            file_category=None,
            size=None,
            status="error",
            content_hash=None,
            preview_snippet=None,
            storage_path=None,
            parsed_content=None,
            metadata={},
            error=str(e),
            source_id=source_id,
        )
    return SourceMeta.model_validate(meta)


@router.post("/text", response_model=SourceMeta)
async def add_workspace_text_source(req: TextRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    await session_store.ensure_workspace(workspace_id)
    from app.services.document.parser import estimate_tokens
    content_hash = _hash_text(req.content)

    deduped = await session_store.get_workspace_source_by_hash(workspace_id, content_hash)
    if deduped:
        deduped["deduped"] = True
        return SourceMeta.model_validate(deduped)

    meta = await session_store.create_workspace_source(
        workspace_id=workspace_id,
        source_type="text",
        name=req.name,
        file_category="text",
        size=len(req.content.encode("utf-8")),
        status="ready",
        content_hash=content_hash,
        preview_snippet=_snippet(req.content),
        storage_path=None,
        parsed_content=req.content,
        metadata={"estimated_tokens": estimate_tokens(req.content)},
    )
    return SourceMeta.model_validate(meta)


@router.delete("/{source_id}")
async def delete_workspace_source(source_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    deleted = await session_store.delete_workspace_source(workspace_id, source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="来源不存在")
    return {"ok": True}


@router.post("/bulk-delete")
async def bulk_delete_workspace_sources(req: BulkDeleteRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    await session_store.ensure_workspace(workspace_id)
    result = await session_store.bulk_delete_workspace_sources(workspace_id, req.source_ids)
    return result


@router.get("/{source_id}/content")
async def get_workspace_source_content(source_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    try:
        content = await session_store.get_workspace_source_content(workspace_id, source_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"content": content}

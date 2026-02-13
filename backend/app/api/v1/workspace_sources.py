"""Workspace-level source (素材库) APIs."""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from app.models.source import SourceMeta
from app.services.sessions import session_store
from app.services.sessions.workspace import get_workspace_id_from_request

router = APIRouter(prefix="/workspace/sources", tags=["workspace-sources"])


class UrlRequest(BaseModel):
    url: str


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


@router.get("", response_model=list[SourceMeta])
async def list_workspace_sources(
    request: Request,
    q: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    workspace_id = get_workspace_id_from_request(request)
    await session_store.ensure_workspace(workspace_id)
    sources = await session_store.list_workspace_sources(workspace_id, q=q, limit=limit, offset=offset)
    return [SourceMeta.model_validate(item) for item in sources]


@router.post("/upload", response_model=SourceMeta)
async def upload_workspace_source(request: Request, file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    workspace_id = get_workspace_id_from_request(request)
    await session_store.ensure_workspace(workspace_id)
    source_id = f"src-{uuid4().hex[:16]}"
    file_bytes = await file.read()
    try:
        storage_path, parsed_content = await _save_and_parse_file(
            source_id=source_id, filename=file.filename, file_bytes=file_bytes,
        )
        from app.models.source import detect_file_category
        from app.services.document.parser import estimate_tokens

        meta = await session_store.create_workspace_source(
            workspace_id=workspace_id,
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
        meta = await session_store.create_workspace_source(
            workspace_id=workspace_id,
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


@router.post("/url", response_model=SourceMeta)
async def add_workspace_url_source(req: UrlRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    await session_store.ensure_workspace(workspace_id)
    source_id = f"src-{uuid4().hex[:16]}"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(req.url)
            resp.raise_for_status()
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
            preview_snippet=None,
            storage_path=None,
            parsed_content=None,
            metadata={},
            error=str(e),
            source_id=source_id,
        )
    return SourceMeta.model_validate(meta)


@router.delete("/{source_id}")
async def delete_workspace_source(source_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    deleted = await session_store.delete_workspace_source(workspace_id, source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="来源不存在")
    return {"ok": True}


@router.get("/{source_id}/content")
async def get_workspace_source_content(source_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    try:
        content = await session_store.get_workspace_source_content(workspace_id, source_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"content": content}

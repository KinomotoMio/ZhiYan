"""POST/GET/DELETE /api/v1/sources — 素材来源管理"""

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.models.source import SourceMeta
from app.services.document import source_store

router = APIRouter(prefix="/sources")


class UrlRequest(BaseModel):
    url: str


class TextRequest(BaseModel):
    name: str
    content: str


@router.post("/upload", response_model=SourceMeta)
async def upload_source(file: UploadFile = File(...)):
    """上传文件来源"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    file_bytes = await file.read()
    return await source_store.add_file(file.filename, file_bytes)


@router.post("/url", response_model=SourceMeta)
async def fetch_url_source(req: UrlRequest):
    """抓取 URL 来源"""
    return await source_store.add_url(req.url)


@router.post("/text", response_model=SourceMeta)
async def add_text_source(req: TextRequest):
    """添加纯文本来源"""
    return await source_store.add_text(req.name, req.content)


@router.get("/", response_model=list[SourceMeta])
async def list_sources():
    """列出所有来源"""
    return source_store.list_all()


@router.get("/{source_id}/content")
async def get_source_content(source_id: str):
    """获取来源的完整解析内容"""
    entry = source_store.get(source_id)
    if not entry:
        raise HTTPException(status_code=404, detail="来源不存在")
    return {"content": entry.get("parsed_content", "")}


@router.delete("/{source_id}")
async def delete_source(source_id: str):
    """删除指定来源"""
    if not source_store.remove(source_id):
        raise HTTPException(status_code=404, detail="来源不存在")
    return {"ok": True}

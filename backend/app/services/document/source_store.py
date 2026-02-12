"""来源存储 — 内存 + 临时目录的素材管理"""

import asyncio
import shutil
import tempfile
import uuid
from pathlib import Path

import httpx

from app.models.source import (
    FileCategory,
    SourceMeta,
    SourceStatus,
    SourceType,
    detect_file_category,
)
from app.services.document.parser import parse_document

# 临时上传目录
_UPLOAD_DIR = Path(tempfile.gettempdir()) / "zhiyan_uploads"
_UPLOAD_DIR.mkdir(exist_ok=True)

# 内存存储：source_id → {meta, parsed_content}
_sources: dict[str, dict] = {}


def _snippet(text: str, max_len: int = 200) -> str:
    """截取前 N 个字符作为预览"""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


async def add_file(filename: str, file_bytes: bytes) -> SourceMeta:
    """保存上传文件并解析"""
    source_id = str(uuid.uuid4())
    file_dir = _UPLOAD_DIR / source_id
    file_dir.mkdir(parents=True, exist_ok=True)
    file_path = file_dir / filename

    file_path.write_bytes(file_bytes)

    category = detect_file_category(filename)
    meta = SourceMeta(
        id=source_id,
        name=filename,
        type=SourceType.FILE,
        fileCategory=category,
        size=len(file_bytes),
        status=SourceStatus.PARSING,
    )
    _sources[source_id] = {"meta": meta, "parsed_content": ""}

    # 异步解析
    try:
        content = await asyncio.to_thread(
            lambda: _sync_parse(file_path)
        )
        meta.status = SourceStatus.READY
        meta.preview_snippet = _snippet(content)
        _sources[source_id]["parsed_content"] = content
    except Exception as e:
        meta.status = SourceStatus.ERROR
        meta.error = str(e)

    return meta


def _sync_parse(file_path: Path) -> str:
    """同步调用 MarkItDown 解析"""
    from markitdown import MarkItDown

    converter = MarkItDown()
    result = converter.convert(str(file_path))
    return result.text_content


async def add_url(url: str) -> SourceMeta:
    """抓取 URL 内容并解析"""
    source_id = str(uuid.uuid4())
    meta = SourceMeta(
        id=source_id,
        name=url,
        type=SourceType.URL,
        status=SourceStatus.PARSING,
    )
    _sources[source_id] = {"meta": meta, "parsed_content": ""}

    try:
        # 下载内容
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        # 保存到临时文件后用 MarkItDown 解析
        file_dir = _UPLOAD_DIR / source_id
        file_dir.mkdir(parents=True, exist_ok=True)

        # 从 URL 推断文件名
        from urllib.parse import urlparse

        path = urlparse(url).path
        filename = Path(path).name or "page.html"
        file_path = file_dir / filename

        file_path.write_bytes(resp.content)
        meta.size = len(resp.content)

        content = await asyncio.to_thread(lambda: _sync_parse(file_path))
        meta.status = SourceStatus.READY
        meta.preview_snippet = _snippet(content)
        _sources[source_id]["parsed_content"] = content
    except Exception as e:
        meta.status = SourceStatus.ERROR
        meta.error = str(e)

    return meta


async def add_text(name: str, content: str) -> SourceMeta:
    """直接添加纯文本来源"""
    source_id = str(uuid.uuid4())
    meta = SourceMeta(
        id=source_id,
        name=name,
        type=SourceType.TEXT,
        fileCategory=FileCategory.TEXT,
        size=len(content.encode("utf-8")),
        status=SourceStatus.READY,
        previewSnippet=_snippet(content),
    )
    _sources[source_id] = {"meta": meta, "parsed_content": content}
    return meta


def get(source_id: str) -> dict | None:
    """获取来源完整数据"""
    return _sources.get(source_id)


def list_all() -> list[SourceMeta]:
    """列出所有来源"""
    return [entry["meta"] for entry in _sources.values()]


def remove(source_id: str) -> bool:
    """删除来源及其临时文件"""
    if source_id not in _sources:
        return False
    del _sources[source_id]
    file_dir = _UPLOAD_DIR / source_id
    if file_dir.exists():
        shutil.rmtree(file_dir, ignore_errors=True)
    return True


def get_combined_content(source_ids: list[str]) -> str:
    """拼接指定来源的已解析内容"""
    parts: list[str] = []
    for sid in source_ids:
        entry = _sources.get(sid)
        if entry and entry["parsed_content"]:
            parts.append(entry["parsed_content"])
    return "\n\n---\n\n".join(parts)

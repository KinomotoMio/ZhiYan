"""来源存储 — 内存 + 临时目录的素材管理

支持 3 层文档模型：
  Layer 1: 身份（id, title, source_type, metadata）
  Layer 2: 摘要（description, key_topics, structure_outline）
  Layer 3: 原始内容（raw_content / parsed_content，已自动规范化）
"""

import asyncio
import logging
import shutil
import tempfile
import uuid
from pathlib import Path

from app.models.document import DocumentLayer
from app.models.source import (
    FileCategory,
    SourceMeta,
    SourceStatus,
    SourceType,
    detect_file_category,
)
from app.utils.security import get_safe_httpx_client

logger = logging.getLogger(__name__)

# 临时上传目录
_UPLOAD_DIR = Path(tempfile.gettempdir()) / "zhiyan_uploads"
_UPLOAD_DIR.mkdir(exist_ok=True)

# 内存存储：source_id → {meta, parsed_content, document_layer}
_sources: dict[str, dict] = {}


def _snippet(text: str, max_len: int = 200) -> str:
    """截取前 N 个字符作为预览"""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


async def _generate_meta_background(source_id: str, content: str, file_name: str) -> None:
    """后台生成文档元数据（Layer 1+2），不阻塞上传响应"""
    try:
        from app.services.agents.document_meta_generator import generate_document_meta

        meta_result = await generate_document_meta(content, file_name)
        entry = _sources.get(source_id)
        if entry and entry.get("document_layer"):
            layer: DocumentLayer = entry["document_layer"]
            layer.title = meta_result.title
            layer.description = meta_result.description
            layer.key_topics = meta_result.key_topics
            layer.structure_outline = meta_result.structure_outline
            # 更新 SourceMeta 的 name 为 AI 生成的标题
            if entry["meta"].name == file_name:
                entry["meta"].preview_snippet = _snippet(
                    f"{meta_result.title} — {meta_result.description}"
                )
            logger.info(
                "Document meta generated for %s: title=%s, topics=%s",
                source_id, meta_result.title, meta_result.key_topics,
            )
    except Exception as e:
        logger.warning("Background meta generation failed for %s: %s", source_id, e)


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
    _sources[source_id] = {
        "meta": meta,
        "parsed_content": "",
        "document_layer": None,
    }

    # 异步解析（_sync_parse 内部自动执行正则规范化）
    try:
        content = await asyncio.to_thread(lambda: _sync_parse(file_path))
        meta.status = SourceStatus.READY
        meta.preview_snippet = _snippet(content)
        _sources[source_id]["parsed_content"] = content

        # 创建 DocumentLayer
        from app.services.document.parser import estimate_tokens

        layer = DocumentLayer(
            id=source_id,
            title=filename,
            source_type=category.value if category else "unknown",
            file_name=filename,
            metadata={
                "size": len(file_bytes),
                "estimated_tokens": estimate_tokens(content),
            },
            raw_content=content,
        )
        _sources[source_id]["document_layer"] = layer

        # 后台生成 AI 元数据（不阻塞返回）
        asyncio.create_task(_generate_meta_background(source_id, content, filename))
    except Exception as e:
        meta.status = SourceStatus.ERROR
        meta.error = str(e)

    return meta


def _sync_parse(file_path: Path) -> str:
    """同步调用 MarkItDown 解析 + 正则规范化"""
    from app.services.document.parser import (
        create_markitdown_converter,
        normalize_markdown,
    )

    converter = create_markitdown_converter()
    result = converter.convert(str(file_path))
    return normalize_markdown(result.text_content)


async def add_url(url: str) -> SourceMeta:
    """抓取 URL 内容并解析"""
    source_id = str(uuid.uuid4())
    meta = SourceMeta(
        id=source_id,
        name=url,
        type=SourceType.URL,
        status=SourceStatus.PARSING,
    )
    _sources[source_id] = {
        "meta": meta,
        "parsed_content": "",
        "document_layer": None,
    }

    try:
        async with get_safe_httpx_client(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        file_dir = _UPLOAD_DIR / source_id
        file_dir.mkdir(parents=True, exist_ok=True)

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

        # 创建 DocumentLayer
        from app.services.document.parser import estimate_tokens

        layer = DocumentLayer(
            id=source_id,
            title=url,
            source_type="url",
            file_name=filename,
            metadata={
                "size": len(resp.content),
                "estimated_tokens": estimate_tokens(content),
            },
            raw_content=content,
        )
        _sources[source_id]["document_layer"] = layer

        asyncio.create_task(_generate_meta_background(source_id, content, filename))
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

    from app.services.document.parser import estimate_tokens

    layer = DocumentLayer(
        id=source_id,
        title=name,
        source_type="text",
        file_name=name,
        metadata={
            "size": len(content.encode("utf-8")),
            "estimated_tokens": estimate_tokens(content),
        },
        raw_content=content,
    )
    _sources[source_id] = {
        "meta": meta,
        "parsed_content": content,
        "document_layer": layer,
    }

    asyncio.create_task(_generate_meta_background(source_id, content, name))
    return meta


def get(source_id: str) -> dict | None:
    """获取来源完整数据"""
    return _sources.get(source_id)


def get_document_layer(source_id: str) -> DocumentLayer | None:
    """获取文档 3 层模型"""
    entry = _sources.get(source_id)
    if entry:
        return entry.get("document_layer")
    return None


def get_document_layers(source_ids: list[str]) -> list[DocumentLayer]:
    """批量获取文档 3 层模型"""
    layers = []
    for sid in source_ids:
        layer = get_document_layer(sid)
        if layer:
            layers.append(layer)
    return layers


def get_layer12_summaries(source_ids: list[str]) -> str:
    """获取指定来源的 Layer 1+2 摘要文本（供 Outline Agent 使用）"""
    summaries = []
    for sid in source_ids:
        layer = get_document_layer(sid)
        if layer:
            summaries.append(layer.get_layer12_summary())
    return "\n\n".join(summaries)


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


def cleanup_old_uploads(max_age_hours: int = 24) -> int:
    """删除超过 max_age_hours 的临时上传目录，返回清理数量"""
    import time

    count = 0
    if not _UPLOAD_DIR.exists():
        return count

    now = time.time()
    cutoff = now - max_age_hours * 3600

    for entry in _UPLOAD_DIR.iterdir():
        if entry.is_dir() and entry.stat().st_mtime < cutoff:
            if entry.name in _sources:
                continue
            shutil.rmtree(entry, ignore_errors=True)
            count += 1

    return count


def get_combined_content(source_ids: list[str]) -> str:
    """拼接指定来源的已规范化内容"""
    parts: list[str] = []
    for sid in source_ids:
        entry = _sources.get(sid)
        if entry and entry["parsed_content"]:
            parts.append(entry["parsed_content"])
    return "\n\n---\n\n".join(parts)

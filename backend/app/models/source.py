"""Source 数据模型 — 素材来源管理"""

from enum import Enum

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    FILE = "file"
    URL = "url"
    TEXT = "text"


class SourceStatus(str, Enum):
    UPLOADING = "uploading"
    PARSING = "parsing"
    READY = "ready"
    ERROR = "error"


class FileCategory(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    MARKDOWN = "markdown"
    PPTX = "pptx"
    IMAGE = "image"
    TEXT = "text"
    UNKNOWN = "unknown"


# 扩展名 → FileCategory 映射
EXTENSION_CATEGORY_MAP: dict[str, FileCategory] = {
    ".pdf": FileCategory.PDF,
    ".doc": FileCategory.DOCX,
    ".docx": FileCategory.DOCX,
    ".md": FileCategory.MARKDOWN,
    ".markdown": FileCategory.MARKDOWN,
    ".pptx": FileCategory.PPTX,
    ".ppt": FileCategory.PPTX,
    ".png": FileCategory.IMAGE,
    ".jpg": FileCategory.IMAGE,
    ".jpeg": FileCategory.IMAGE,
    ".gif": FileCategory.IMAGE,
    ".webp": FileCategory.IMAGE,
    ".txt": FileCategory.TEXT,
    ".csv": FileCategory.TEXT,
    ".json": FileCategory.TEXT,
}


def detect_file_category(filename: str) -> FileCategory:
    """根据扩展名判断文件类型"""
    from pathlib import Path

    ext = Path(filename).suffix.lower()
    return EXTENSION_CATEGORY_MAP.get(ext, FileCategory.UNKNOWN)


class SourceMeta(BaseModel):
    """素材来源元数据（返回给前端）"""

    id: str
    name: str
    type: SourceType
    file_category: FileCategory | None = Field(None, alias="fileCategory")
    size: int | None = None
    status: SourceStatus = SourceStatus.UPLOADING
    preview_snippet: str | None = Field(None, alias="previewSnippet")
    error: str | None = None

    model_config = {"populate_by_name": True}

"""文档解析 — MarkItDown 封装 + 正则规范化 + 分块逻辑"""

import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from markitdown import MarkItDown


logger = logging.getLogger(__name__)
_converter: "MarkItDown | None" = None


def _ensure_path_env() -> None:
    if "PATH" in os.environ:
        return

    fallback = os.environ.get("Path", "")
    os.environ["PATH"] = fallback
    logger.warning(
        "PATH missing from process environment; defaulting to %r for MarkItDown",
        fallback,
    )


@lru_cache(maxsize=1)
def _get_markitdown_class():
    _ensure_path_env()

    from markitdown import MarkItDown

    return MarkItDown


def create_markitdown_converter() -> "MarkItDown":
    return _get_markitdown_class()()


def _get_shared_converter() -> "MarkItDown":
    global _converter

    if _converter is None:
        _converter = create_markitdown_converter()

    return _converter


async def parse_document(file_path: str | Path) -> str:
    """将文档转换为 Markdown 文本，自动执行轻量规范化"""
    result = _get_shared_converter().convert(str(file_path))
    return normalize_markdown(result.text_content)


def normalize_markdown(text: str) -> str:
    """轻量正则规范化 MarkItDown 输出，修复常见格式问题（<10ms）

    处理：
    - 移除空图片占位 [image]、![]()
    - 移除孤立页码行（如 - 12 -）
    - 合并重复分隔线 ---
    - 合并段内断行（非句末换行 + 中文/小写字母续行 → 合并）
    - 收拢连续空行为最多两个
    - 去除行尾空白
    """
    # 移除空图片占位
    text = re.sub(r"!\[[^\]]*\]\(\s*\)", "", text)
    text = re.sub(r"^\[image\]\s*$", "", text, flags=re.MULTILINE)

    # 移除孤立页码行（如 "- 12 -"、"— 3 —"、"- Page 5 -"）
    text = re.sub(r"^[-—]\s*(?:Page\s*)?\d+\s*[-—]\s*$", "", text, flags=re.MULTILINE | re.IGNORECASE)

    # 合并重复分隔线（连续多个 --- 合并为一个）
    text = re.sub(r"(?:^-{3,}\s*$\n?){2,}", "---\n", text, flags=re.MULTILINE)

    # 合并段内断行：行尾非句末标点 + 下一行以中文或小写字母开头 → 合并
    text = re.sub(
        r"([^\n.!?。！？\s])\n([a-z\u4e00-\u9fff])",
        r"\1\2",
        text,
    )

    # 去除行尾空白
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)

    # 收拢连续空行为最多两个
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    return text.strip()


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中文约 1.5 字/token，英文约 4 字符/token）"""
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other_chars = len(text) - chinese_chars
    return int(chinese_chars / 1.5 + other_chars / 4)


def split_by_headings(markdown: str) -> list[dict]:
    """按 Markdown 标题分块"""
    chunks: list[dict] = []
    current_heading = ""
    current_content: list[str] = []
    chunk_idx = 0

    for line in markdown.split("\n"):
        if line.startswith("#"):
            if current_content:
                chunks.append({
                    "chunk_id": f"chunk-{chunk_idx}",
                    "heading": current_heading,
                    "content": "\n".join(current_content).strip(),
                    "estimated_tokens": estimate_tokens(
                        "\n".join(current_content)
                    ),
                })
                chunk_idx += 1
            current_heading = line.lstrip("#").strip()
            current_content = [line]
        else:
            current_content.append(line)

    if current_content:
        chunks.append({
            "chunk_id": f"chunk-{chunk_idx}",
            "heading": current_heading,
            "content": "\n".join(current_content).strip(),
            "estimated_tokens": estimate_tokens("\n".join(current_content)),
        })

    return chunks

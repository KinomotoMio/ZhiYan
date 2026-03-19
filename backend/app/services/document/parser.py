"""文档解析 — MarkItDown 封装 + 正则规范化 + 分块逻辑"""

import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from markitdown import MarkItDown


logger = logging.getLogger(__name__)
_converter: "MarkItDown | None" = None

_CHART_KEYWORDS = (
    "图表",
    "趋势",
    "折线",
    "柱状",
    "饼图",
    "雷达",
    "chart",
    "graph",
    "plot",
    "trend",
)
_TABLE_KEYWORDS = ("表格", "矩阵", "参数", "table", "matrix", "tabular")
_TIMELINE_KEYWORDS = (
    "时间线",
    "里程碑",
    "排期",
    "路线图",
    "roadmap",
    "timeline",
    "milestone",
)


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


def extract_structure_signals(markdown: str) -> dict:
    """从 Markdown 文本中提取轻量结构信号摘要（用于下游 prompt / hint 推断）。

    目标：稳定、快速、向后兼容。即便输入不是严格 Markdown，也不应报错。

    Schema:
    - image_count: int
    - image_src_samples: list[str] (<= 3)
    - table_count: int
    - table_header_samples: list[str] (<= 3)
    - chart_keyword_hits: list[str] (<= 6)
    - timeline_date_hits: list[str] (<= 6)
    - timeline_quarter_hits: list[str] (<= 6)
    """

    text = markdown or ""
    lowered = text.lower()

    # Images: markdown image syntax + <img src="...">
    image_srcs: list[str] = []
    for match in re.finditer(r"!\[[^\]]*\]\(([^)\s]+)[^)]*\)", text):
        src = match.group(1).strip()
        if src and src not in image_srcs:
            image_srcs.append(src)
    for match in re.finditer(r"<img[^>]*\ssrc=['\"]([^'\"]+)['\"][^>]*>", text, flags=re.IGNORECASE):
        src = match.group(1).strip()
        if src and src not in image_srcs:
            image_srcs.append(src)

    # Tables: detect markdown table header + separator row.
    table_headers: list[str] = []
    table_count = 0
    table_pattern = re.compile(
        r"(?m)^\s*\|?.*\|.*$\n^\s*\|?\s*:?-{3,}.*\|.*$"
    )
    for match in table_pattern.finditer(text):
        table_count += 1
        header_line = match.group(0).splitlines()[0].strip()
        if header_line and header_line not in table_headers:
            table_headers.append(header_line)

    # Chart keywords: keep distinct hits.
    chart_hits = [kw for kw in _CHART_KEYWORDS if kw.lower() in lowered]
    table_hits = [kw for kw in _TABLE_KEYWORDS if kw.lower() in lowered]
    timeline_hits = [kw for kw in _TIMELINE_KEYWORDS if kw.lower() in lowered]

    # Timeline: extract date-like and quarter-like tokens as structured samples.
    date_hits: list[str] = []
    for match in re.finditer(r"\b(19|20)\d{2}[-/.](0?[1-9]|1[0-2])([-/\.](0?[1-9]|[12]\d|3[01]))?\b", text):
        value = match.group(0)
        if value and value not in date_hits:
            date_hits.append(value)
    for match in re.finditer(r"\b(19|20)\d{2}年(0?[1-9]|1[0-2])月(0?[1-9]|[12]\d|3[01])日?\b", text):
        value = match.group(0)
        if value and value not in date_hits:
            date_hits.append(value)

    quarter_hits: list[str] = []
    for match in re.finditer(r"\b(19|20)\d{2}\s*Q[1-4]\b", text, flags=re.IGNORECASE):
        value = match.group(0).replace(" ", "")
        if value and value not in quarter_hits:
            quarter_hits.append(value)
    for match in re.finditer(r"\bQ[1-4]\b", text, flags=re.IGNORECASE):
        value = match.group(0).upper()
        if value and value not in quarter_hits:
            quarter_hits.append(value)
    for match in re.finditer(r"\b(19|20)\d{2}年第[一二三四1234]季度\b", text):
        value = match.group(0)
        if value and value not in quarter_hits:
            quarter_hits.append(value)

    return {
        "image_count": len(image_srcs),
        "image_src_samples": image_srcs[:3],
        "table_count": table_count,
        "table_header_samples": table_headers[:3],
        "chart_keyword_hits": chart_hits[:6],
        "table_keyword_hits": table_hits[:6],
        "timeline_keyword_hits": timeline_hits[:6],
        "timeline_date_hits": date_hits[:6],
        "timeline_quarter_hits": quarter_hits[:6],
    }


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

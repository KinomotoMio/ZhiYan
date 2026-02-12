"""文档解析 — MarkItDown 封装 + 分块逻辑"""

from pathlib import Path

from markitdown import MarkItDown


_converter = MarkItDown()


async def parse_document(file_path: str | Path) -> str:
    """将文档转换为 Markdown 文本"""
    result = _converter.convert(str(file_path))
    return result.text_content


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

"""Document Cleaner Agent — MarkItDown 输出清洗

修复 PDF/PPTX 等解析后的格式问题：断行、乱码表格、冗余标记。
大文档按顶层标题分段清洗，带并发控制和超时保护。
"""

import asyncio
import logging
import re
import time

logger = logging.getLogger(__name__)

_agent = None


def get_document_cleaner_agent():
    """延迟创建 Agent"""
    global _agent
    if _agent is None:
        from pydantic_ai import Agent

        from app.core.config import settings
        from app.core.model_resolver import resolve_model

        _agent = Agent(
            model=resolve_model(settings.default_model),
            output_type=str,
            retries=2,
            instructions=(
                "你是文档格式修复助手。你的任务是清洗 MarkItDown 工具从 PDF/PPTX/DOCX "
                "等格式转换得到的 Markdown 文本。\n\n"
                "## 清洗规则\n"
                "1. 修复不自然的断行：将同一段落内被错误换行打断的句子合并为连续段落\n"
                "2. 移除解析残留物：空的图片占位 `[image]`、无意义的页码标记、"
                "重复的分隔线 `---` 等\n"
                "3. 修复乱码表格：将格式混乱的表格整理为规范的 Markdown 表格，"
                "或在无法修复时转为要点列表\n"
                "4. 规范标题层级：确保标题使用 `#` 到 `####`，层级连续不跳级\n"
                "5. 保留原始语义：不要改写、总结或删除任何有意义的内容\n"
                "6. 移除冗余空行：连续多个空行合并为一个\n\n"
                "## 输出要求\n"
                "- 直接输出清洗后的 Markdown 文本\n"
                "- 不要添加任何解释、前言或总结\n"
                "- 不要用代码块包裹输出"
            ),
        )
    return _agent


def __getattr__(name):
    if name == "document_cleaner_agent":
        return get_document_cleaner_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


async def _run_with_timeout(agent, prompt: str, timeout: float = 60.0) -> str | None:
    """带超时的 agent.run()，超时或失败返回 None"""
    try:
        result = await asyncio.wait_for(agent.run(prompt), timeout=timeout)
        return result.output
    except asyncio.TimeoutError:
        logger.error("Document cleaner LLM timed out after %.0fs", timeout)
        return None
    except Exception as e:
        logger.error("Document cleaner LLM failed: %s: %s", type(e).__name__, e)
        return None


def _split_by_heading_level(text: str, pattern: str) -> list[str]:
    """按指定标题正则分段"""
    lines = text.split("\n")
    segments: list[str] = []
    current: list[str] = []

    for line in lines:
        if re.match(pattern, line) and current:
            segments.append("\n".join(current))
            current = [line]
        else:
            current.append(line)

    if current:
        segments.append("\n".join(current))

    return segments


def _split_by_top_headings(text: str) -> list[str]:
    """按标题分段，优先 # 级，回退到 ## 级"""
    # 先尝试 # 分割
    segments = _split_by_heading_level(text, r"^# [^#]")
    if len(segments) > 1:
        return segments
    # 回退到 ## 分割
    segments = _split_by_heading_level(text, r"^#{1,2} [^#]")
    if len(segments) > 1:
        return segments
    return [text]


async def clean_document(raw_content: str) -> str:
    """清洗 MarkItDown 输出，返回规范 Markdown。

    大文档（> 8000 估算 token）按标题分段清洗，带 Semaphore(5) 并发控制。
    每段 LLM 调用有 60s 超时，超时回退到原始文本。
    """
    from app.services.document.parser import estimate_tokens

    start_time = time.monotonic()
    token_count = estimate_tokens(raw_content)
    try:
        agent = get_document_cleaner_agent()
    except Exception as e:
        logger.error("Document cleaner agent init failed: %s: %s", type(e).__name__, e)
        return raw_content

    if token_count <= 8000:
        logger.info("Document cleaner: %d tokens, single-pass cleaning", token_count)
        output = await _run_with_timeout(agent, f"请清洗以下文档：\n\n{raw_content}")
        elapsed = time.monotonic() - start_time
        if output is None:
            logger.warning("Document cleaner: single-pass failed/timed out (%.1fs), returning original", elapsed)
            return raw_content
        logger.info("Document cleaner: single-pass done in %.1fs", elapsed)
        return output

    # 大文档分段清洗
    segments = _split_by_top_headings(raw_content)
    if len(segments) <= 1:
        # 无法按标题分割，按字符截断分块（每块 ~12000 字符）
        chunk_size = 12000
        segments = [
            raw_content[i : i + chunk_size]
            for i in range(0, len(raw_content), chunk_size)
        ]
        logger.info(
            "Document cleaner: %d tokens, no headings found, chunked into %d segments by size",
            token_count, len(segments),
        )
    else:
        logger.info(
            "Document cleaner: %d tokens, splitting into %d segments by headings",
            token_count, len(segments),
        )

    semaphore = asyncio.Semaphore(5)
    cleaned_segments: list[str] = [None] * len(segments)  # type: ignore[list-item]

    async def clean_segment(idx: int, segment: str) -> None:
        async with semaphore:
            seg_chars = len(segment)
            logger.info("Cleaning segment %d/%d (%d chars)...", idx + 1, len(segments), seg_chars)
            seg_start = time.monotonic()
            output = await _run_with_timeout(
                agent, f"请清洗以下文档片段：\n\n{segment[:15000]}"
            )
            seg_elapsed = time.monotonic() - seg_start
            if output is None:
                logger.warning(
                    "Segment %d/%d failed/timed out (%.1fs), keeping original",
                    idx + 1, len(segments), seg_elapsed,
                )
                cleaned_segments[idx] = segment
            else:
                logger.info("Segment %d/%d done in %.1fs", idx + 1, len(segments), seg_elapsed)
                cleaned_segments[idx] = output

    await asyncio.gather(
        *(clean_segment(i, seg) for i, seg in enumerate(segments))
    )

    elapsed = time.monotonic() - start_time
    logger.info("Document cleaner: all %d segments done in %.1fs", len(segments), elapsed)
    return "\n\n".join(cleaned_segments)

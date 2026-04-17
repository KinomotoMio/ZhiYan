from __future__ import annotations

import logging

from app.core.config import settings
from app.models.document import DocumentMeta
from app.services.lightweight_llm import generate_structured_output

logger = logging.getLogger(__name__)

_DOCUMENT_META_SYSTEM_PROMPT = (
    "你是文档分析助手。从给定文档内容中提取元数据。\n"
    "要求：\n"
    "- title: 用 10-25 个字概括文档主题，不要直接照抄文件名\n"
    "- description: 100 字以内摘要，覆盖核心价值信息\n"
    "- key_topics: 3-5 个核心话题标签，每个 2-6 个字\n"
    "- structure_outline: 用 1-3 行描述结构，如 引言→方案→结论\n"
    "- 中文为主，专业术语保留英文\n"
    "- 只能基于实际内容，不要编造"
)


async def generate_document_meta(content: str, file_name: str = "") -> DocumentMeta:
    preview = content[:6000] if len(content) > 6000 else content
    prompt = f"文件名: {file_name}\n\n文档内容:\n{preview}"
    model_name = str(settings.fast_model or settings.default_model or "").strip()
    try:
        result, _raw_text, _usage = await generate_structured_output(
            model_name=model_name,
            system_prompt=_DOCUMENT_META_SYSTEM_PROMPT,
            user_prompt=prompt,
            output_model=DocumentMeta,
            temperature=0.0,
        )
        return result
    except Exception as exc:
        logger.warning("Document meta generation failed: %s, using fallback", exc)
        title = file_name or content[:30].strip()
        return DocumentMeta(
            title=title,
            description=content[:100].strip(),
            key_topics=[],
            structure_outline="",
        )

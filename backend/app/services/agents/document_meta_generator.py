"""Document Meta Generator Agent — 生成文档标题、摘要、话题标签

从原始内容中提取有意义的元数据，用于 DocumentLayer 的 Layer 1+2。
使用 fast_model 一次调用完成。
"""

import logging

from app.models.document import DocumentMeta

logger = logging.getLogger(__name__)

_agent = None


def get_document_meta_generator_agent():
    """延迟创建 Agent"""
    global _agent
    if _agent is None:
        from pydantic_ai import Agent

        from app.core.config import settings
        from app.core.model_resolver import resolve_model

        model = resolve_model(settings.fast_model or settings.default_model)
        _agent = Agent(
            model=model,
            output_type=DocumentMeta,
            retries=1,
            instructions=(
                "你是文档分析助手。从给定的文档内容中提取元数据。\n\n"
                "## 规则\n"
                "1. title: 用 10-25 个字概括文档的核心主题（不是文件名，而是内容主题）\n"
                "2. description: 100 字以内的内容摘要，概括文档讨论的主要内容和结论\n"
                "3. key_topics: 3-5 个核心话题标签，每个 2-6 个字\n"
                "4. structure_outline: 用 1-3 行描述文档的结构（如「引言 → 技术方案 → 实验结果 → 结论」）\n\n"
                "## 要求\n"
                "- 基于文档实际内容生成，不要编造\n"
                "- 中文为主，专业术语保留英文\n"
                "- 摘要应覆盖文档的核心价值信息"
            ),
        )
    return _agent


def __getattr__(name):
    if name == "document_meta_generator_agent":
        return get_document_meta_generator_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


async def generate_document_meta(content: str, file_name: str = "") -> DocumentMeta:
    """生成文档元数据

    对于大文档只取前 6000 字符用于生成元数据（足够判断主题和结构）。
    """
    agent = get_document_meta_generator_agent()

    # 截取前部分内容用于分析
    preview = content[:6000] if len(content) > 6000 else content
    prompt = f"文件名: {file_name}\n\n文档内容:\n{preview}"

    try:
        result = await agent.run(prompt)
        return result.output
    except Exception as e:
        logger.warning("Document meta generation failed: %s, using fallback", e)
        # fallback：从内容中提取基本信息
        title = file_name or content[:30].strip()
        return DocumentMeta(
            title=title,
            description=content[:100].strip(),
            key_topics=[],
            structure_outline="",
        )

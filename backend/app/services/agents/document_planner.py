"""Document Planner Agent — 文档元数据 → 分块策略

轻量 context：只看文档结构和元信息，不看全文内容。
"""

from pydantic import BaseModel, Field


class ChunkPlan(BaseModel):
    """分块策略输出"""

    total_sections: int = Field(description="文档总章节数")
    chunks: list["ChunkInfo"] = Field(description="每个块的信息")
    estimated_tokens: int = Field(description="预估总 token 量")
    needs_splitting: bool = Field(description="是否需要分块处理")


class ChunkInfo(BaseModel):
    """单个块的元信息"""

    chunk_id: str
    heading: str = Field(description="块标题 / 章节名")
    start_index: int = Field(description="在原文中的起始字符位置")
    end_index: int = Field(description="在原文中的结束字符位置")
    estimated_tokens: int


_agent = None


def get_document_planner_agent():
    """延迟创建 Agent"""
    global _agent
    if _agent is None:
        from pydantic_ai import Agent

        _agent = Agent(
            model="openai:gpt-4o-mini",
            output_type=ChunkPlan,
            instructions=(
                "你是一个文档分析助手。根据文档的结构信息（标题层级、段落数量、估算字数），"
                "制定一个合理的分块策略。每个块应在 1000-3000 token 之间，"
                "按语义边界（章节/段落）切分，不要在句子中间断开。"
            ),
        )
    return _agent


def __getattr__(name):
    if name == "document_planner_agent":
        return get_document_planner_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

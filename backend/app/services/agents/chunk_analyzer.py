"""Chunk Analyzer Agent — 单块 → 要点摘要

Context 隔离：每个子 Agent 只看自己负责的块 + 全局任务描述。
支持并行调用。
"""

from pydantic import BaseModel, Field


class ChunkAnalysis(BaseModel):
    """单个文档块的分析结果"""

    chunk_id: str
    key_points: list[str] = Field(description="核心要点（3-5 个）")
    suggested_slide_count: int = Field(description="建议生成的幻灯片页数")
    data_elements: list[str] = Field(
        default_factory=list, description="可视化的数据元素（表格、数字等）"
    )
    importance: float = Field(ge=0, le=1, description="内容重要度评分")


_agent = None


def get_chunk_analyzer_agent():
    """延迟创建 Agent — 避免模块加载时检查 API key"""
    global _agent
    if _agent is None:
        from pydantic_ai import Agent

        _agent = Agent(
            model="openai:gpt-4o-mini",
            output_type=ChunkAnalysis,
            instructions=(
                "你是一个内容分析助手。分析给定的文档片段，提取核心要点，"
                "评估其重要性，并建议应该生成多少页幻灯片来展示这些内容。"
                "关注事实和论点，忽略过渡性文字。"
            ),
        )
    return _agent


# 向后兼容的属性访问
def __getattr__(name):
    if name == "chunk_analyzer_agent":
        return get_chunk_analyzer_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

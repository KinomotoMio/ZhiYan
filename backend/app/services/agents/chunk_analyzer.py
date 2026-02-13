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
    importance: float = Field(description="内容重要度评分（0-1）")


_agent = None


def get_chunk_analyzer_agent():
    """延迟创建 Agent — 避免模块加载时检查 API key"""
    global _agent
    if _agent is None:
        from pydantic_ai import Agent
        from app.core.config import settings
        from app.core.model_resolver import resolve_model

        _agent = Agent(
            model=resolve_model(settings.fast_model or settings.default_model),
            output_type=ChunkAnalysis,
            retries=1,  # 从 2 降到 1，减少不必要的 LLM 重试
            instructions=(
                "你是一个内容分析助手。分析给定的文档片段，提取核心要点，"
                "评估其重要性，并建议应该生成多少页幻灯片来展示这些内容。\n"
                "关注事实和论点，忽略过渡性文字。\n\n"
                "## 示例\n\n"
                "### 输入\n"
                "演示文稿主题：AI 在医疗领域的应用\n"
                "文档片段：近年来，人工智能技术在医学影像诊断中取得了突破性进展。"
                "深度学习算法在肺部CT扫描中检测肺结节的准确率已达到97.3%，"
                "超过了放射科医师的平均水平（94.5%）。此外，AI辅助系统将诊断时间"
                "从平均15分钟缩短至30秒。Enlitic、Zebra Medical等公司已获得FDA批准。\n\n"
                "### 期望输出\n"
                "- chunk_id: (保持传入的 ID)\n"
                "- key_points: ['AI 在肺部 CT 诊断中准确率达 97.3%', "
                "'超越放射科医师平均水平(94.5%)', '诊断时间从 15 分钟缩短至 30 秒', "
                "'Enlitic/Zebra Medical 等已获 FDA 批准']\n"
                "- suggested_slide_count: 2\n"
                "- data_elements: ['准确率对比: 97.3% vs 94.5%', '时间对比: 15min vs 30s']\n"
                "- importance: 0.85\n\n"
                "## 要点提取规则\n"
                "- 保留具体数字和百分比\n"
                "- 每个要点一句话，不超过 25 个字\n"
                "- 如有对比数据，标注为 data_elements\n"
                "- importance 评分标准：0.9+ 核心论点，0.7-0.9 重要支撑，0.5-0.7 背景信息，<0.5 过渡内容"
            ),
        )
    return _agent


# 向后兼容的属性访问
def __getattr__(name):
    if name == "chunk_analyzer_agent":
        return get_chunk_analyzer_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

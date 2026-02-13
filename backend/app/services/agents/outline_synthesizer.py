"""Outline Synthesizer Agent — 文档摘要 → 叙事大纲

新版：合并原 PlanChunks + AnalyzeChunks + SynthesizeOutline 三步为一步。
小文档（< 8000 tokens）全文直接喂给 Agent。
大文档使用 Layer 2 摘要 + Layer 3 精选段落。

输出包含 suggested_layout_category 用于后续 LayoutSelection。
"""

from pydantic import BaseModel, Field


class OutlineItem(BaseModel):
    """大纲中的一项"""

    slide_number: int
    title: str = Field(description="幻灯片标题")
    content_brief: str = Field(
        default="",
        description="该页内容方向（100-200 字简述）",
    )
    key_points: list[str] = Field(description="该页的核心要点（3-5 个）")
    source_references: list[str] = Field(
        default_factory=list,
        description="引用的文档段落标识（source_id 或 chunk 引用）",
    )
    suggested_layout_category: str = Field(
        default="bullets",
        description="布局类别建议: metrics / comparison / bullets / chart / timeline / quote / image / intro / section / thankyou",
    )


class PresentationOutline(BaseModel):
    """演示文稿大纲"""

    narrative_arc: str = Field(description="叙事主线描述（一句话）")
    items: list[OutlineItem]


_agent = None


def get_outline_synthesizer_agent():
    """延迟创建 Agent"""
    global _agent
    if _agent is None:
        from pydantic_ai import Agent

        from app.core.config import settings
        from app.core.model_resolver import resolve_model

        _agent = Agent(
            model=resolve_model(settings.strong_model),
            output_type=PresentationOutline,
            instructions=(
                "你是一个演示文稿策划专家。根据提供的文档内容，构建一个连贯的叙事大纲。\n\n"
                "## 叙事结构指南\n"
                "采用「问题→分析→方案→结论」四段式叙事弧：\n"
                "1. **开篇引入**（1-2页）：标题页 + 背景/问题引出\n"
                "2. **现状分析**（占总页数 30%）：数据、案例、痛点\n"
                "3. **解决方案**（占总页数 40%）：核心方法、技术细节、优势\n"
                "4. **总结展望**（1-2页）：核心结论 + 致谢页\n\n"
                "## 布局类别选择\n"
                "为每页设置 suggested_layout_category，帮助后续精确选择布局：\n"
                "- `intro`: 第一页标题页\n"
                "- `section`: 章节过渡页\n"
                "- `bullets`: 一般要点列举\n"
                "- `metrics`: 包含数字/KPI/百分比\n"
                "- `comparison`: 对比/优劣分析\n"
                "- `chart`: 数据图表\n"
                "- `table`: 表格数据\n"
                "- `timeline`: 时间线/里程碑\n"
                "- `quote`: 重要引述/结论\n"
                "- `image`: 需要配图的内容\n"
                "- `challenge`: 问题→方案模式\n"
                "- `thankyou`: 致谢/结束页\n\n"
                "## 内容简述要求\n"
                "content_brief 应具体说明这一页要展示什么内容（100-200字），\n"
                "包括要用到的具体数据、案例或论点。这将作为后续内容生成的指导。\n\n"
                "## 质量要求\n"
                "- 第 1 页必须是 intro 类别\n"
                "- 最后一页必须是 thankyou 类别\n"
                "- 每页只承载一个核心观点\n"
                "- 相关内容按逻辑顺序排列\n"
                "- 避免信息重复\n"
                "- key_points 每条不超过 20 字\n"
                "- narrative_arc 一句话概括叙事主线"
            ),
        )
    return _agent


def __getattr__(name):
    if name == "outline_synthesizer_agent":
        return get_outline_synthesizer_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

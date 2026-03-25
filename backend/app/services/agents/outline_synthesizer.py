"""Outline Synthesizer Agent — 文档摘要 → 叙事大纲

新版：合并原 PlanChunks + AnalyzeChunks + SynthesizeOutline 三步为一步。
小文档（< 8000 tokens）全文直接喂给 Agent。
大文档使用 Layer 2 摘要 + Layer 3 精选段落。

输出包含 suggested_slide_role 用于后续 LayoutSelection。
"""

from pydantic import AliasChoices, BaseModel, Field


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
    content_hints: list[str] = Field(
        default_factory=list,
        description="可选结构提示（如 chart/image/table/timeline），用于帮助布局选择阶段更准确匹配信息结构。",
    )
    suggested_slide_role: str = Field(
        default="narrative",
        validation_alias=AliasChoices("suggested_slide_role", "suggested_layout_category"),
        description=(
            "页面角色建议: cover / agenda / section-divider / narrative / "
            "evidence / comparison / process / highlight / closing"
        ),
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
        from app.services.harness import compose_outline_instructions
        from app.services.pipeline.layout_roles import format_role_contract_for_prompt

        _agent = Agent(
            model=resolve_model(settings.strong_model),
            output_type=PresentationOutline,
            instructions=compose_outline_instructions(
                role_contract=format_role_contract_for_prompt(),
            ),
        )
    return _agent


def __getattr__(name):
    if name == "outline_synthesizer_agent":
        return get_outline_synthesizer_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

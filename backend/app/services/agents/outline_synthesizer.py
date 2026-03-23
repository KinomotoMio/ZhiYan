"""Outline Synthesizer Agent — 文档摘要 → 叙事大纲."""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class OutlineItem(BaseModel):
    """大纲中的一项"""

    model_config = ConfigDict(extra="ignore")

    slide_number: int = Field(
        validation_alias=AliasChoices("slide_number", "page", "page_number")
    )
    title: str = Field(description="幻灯片标题")
    content_brief: str = Field(
        default="",
        validation_alias=AliasChoices("content_brief", "summary"),
        description="该页内容方向（100-200 字简述）",
    )
    key_points: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("key_points", "bullets", "bullet_points"),
        description="该页的核心要点（3-5 个）",
    )
    source_references: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("source_references", "references"),
        description="引用的文档段落标识（source_id 或 chunk 引用）",
    )
    content_hints: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("content_hints", "structure_hints"),
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

    @field_validator("title", "content_brief", "suggested_slide_role", mode="before")
    @classmethod
    def _coerce_text(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    @field_validator("key_points", "source_references", "content_hints", mode="before")
    @classmethod
    def _coerce_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        if isinstance(value, (tuple, set)):
            value = list(value)
        if isinstance(value, list):
            items: list[str] = []
            for item in value:
                if item is None:
                    continue
                text = item.strip() if isinstance(item, str) else str(item).strip()
                if text:
                    items.append(text)
            return items
        text = str(value).strip()
        return [text] if text else []


class PresentationOutline(BaseModel):
    """演示文稿大纲"""

    model_config = ConfigDict(extra="ignore")

    narrative_arc: str = Field(description="叙事主线描述（一句话）")
    items: list[OutlineItem] = Field(
        default_factory=list,
        validation_alias=AliasChoices("items", "slides", "outline_items"),
    )

    @field_validator("narrative_arc", mode="before")
    @classmethod
    def _coerce_narrative_arc(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    @field_validator("items", mode="before")
    @classmethod
    def _coerce_items(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]


_agent = None


def get_outline_synthesizer_agent():
    """延迟创建 Agent"""
    global _agent
    if _agent is None:
        from pydantic_ai import Agent

        from app.core.config import settings
        from app.core.model_resolver import resolve_model
        from app.services.pipeline.layout_roles import format_role_contract_for_prompt

        _agent = Agent(
            model=resolve_model(settings.strong_model),
            output_type=PresentationOutline,
            instructions=(
                "你是一个演示文稿策划专家。根据提供的文档内容，构建一个连贯的叙事大纲。\n\n"
                "## 输出 Contract（必须严格遵守）\n"
                "- 只输出一个 JSON 对象，不要输出解释、Markdown 或代码块\n"
                "- 顶层字段只能包含 `narrative_arc` 和 `items`\n"
                "- `items` 必须是长度等于目标页数的数组\n"
                "- 每个 item 必须包含: `slide_number`, `title`, `content_brief`, `key_points`, `source_references`, `content_hints`, `suggested_slide_role`\n"
                "- `slide_number` 从 1 开始递增且不能重复\n"
                "- `key_points` / `source_references` / `content_hints` 必须是数组，没有内容时返回空数组\n"
                "- 不要输出 schema 之外的新字段\n\n"
                "## 叙事结构指南\n"
                "采用「问题→分析→方案→结论」四段式叙事弧：\n"
                "1. **开篇引入**（1-2页）：标题页 + 背景/问题引出\n"
                "2. **现状分析**（占总页数 30%）：数据、案例、痛点\n"
                "3. **解决方案**（占总页数 40%）：核心方法、技术细节、优势\n"
                "4. **总结展望**（1-2页）：核心结论 + 致谢页\n\n"
                "## 页面角色规划\n"
                "为每页设置 suggested_slide_role，帮助后续先确定页面角色，再选择具体布局：\n"
                f"{format_role_contract_for_prompt()}\n\n"
                "## 可选结构提示字段\n"
                "- 你可以为每页补充可选字段 `content_hints`（可为空数组），用于提示该页的信息结构偏好。\n"
                "- 可选值示例：`chart` / `image` / `table` / `timeline`。\n\n"
                "## 结构规则\n"
                "- 第 1 页必须是 `cover`\n"
                "- 最后一页必须是 `closing`\n"
                "- 当总页数 >= 5 时，前 3 页内应包含 1 页 `agenda`，默认优先第 2 页\n"
                "- `section-divider` 只能出现在 `agenda` 之后、`closing` 之前，且不能连续出现\n"
                "- 若生成了 `agenda` 目录页，`section-divider` 数量应与目录 key_points 数量一致，用于作为每章起始页\n\n"
                "## 内容简述要求\n"
                "content_brief 应具体说明这一页要展示什么内容（100-200字），\n"
                "包括要用到的具体数据、案例或论点。这将作为后续内容生成的指导。\n\n"
                "## 质量要求\n"
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

"""布局注册中心 — layout_id → Pydantic 模型映射。

用于 Pipeline 中的 GenerateSlides 节点，根据 layout_id 动态选择 output_type。
对外正式暴露三层 taxonomy 运行时字段，同时保留 selector 当前使用的旧兼容文本接口。
"""

from __future__ import annotations

from dataclasses import dataclass
from pydantic import BaseModel

from app.services.pipeline.layout_taxonomy import (
    LayoutTemplateNotes,
    LayoutVariantObject,
    get_layout_notes,
    get_layout_taxonomy,
)
from app.services.pipeline.layout_variants import (
    get_layout_variant,
    get_layout_variant_description,
    get_layout_variant_label,
)
from app.services.pipeline.layout_usage import format_usage_tags, get_layout_usage_tags
from app.models.layouts.schemas import (
    BulletIconsOnlyData,
    BulletWithIconsData,
    ChallengeOutcomeData,
    ChartWithBulletsData,
    ImageAndDescriptionData,
    IntroSlideData,
    MetricsSlideData,
    MetricsWithImageData,
    NumberedBulletsData,
    OutlineSlideData,
    QuoteSlideData,
    SectionHeaderData,
    TableInfoData,
    ThankYouData,
    TimelineData,
    TwoColumnCompareData,
)


@dataclass(frozen=True)
class LayoutEntry:
    id: str
    name: str
    description: str
    notes: LayoutTemplateNotes
    group: str
    sub_group: str
    variant: LayoutVariantObject
    usage_tags: tuple[str, ...]
    output_model: type[BaseModel]


def _build_layout_entry(
    *,
    layout_id: str,
    name: str,
    output_model: type[BaseModel],
) -> LayoutEntry:
    taxonomy = get_layout_taxonomy(layout_id)
    notes = get_layout_notes(layout_id)
    if taxonomy is None or notes is None:
        raise KeyError(f"Unknown reviewed taxonomy or notes for layout: {layout_id}")

    return LayoutEntry(
        id=layout_id,
        name=name,
        description=notes.purpose,
        notes=notes,
        group=taxonomy.group,
        sub_group=taxonomy.sub_group,
        variant=taxonomy.variant,
        usage_tags=get_layout_usage_tags(layout_id),
        output_model=output_model,
    )


# 所有可用布局
_LAYOUTS: list[LayoutEntry] = [
    _build_layout_entry(
        layout_id="intro-slide",
        name="标题页",
        output_model=IntroSlideData,
    ),
    _build_layout_entry(
        layout_id="section-header",
        name="章节过渡",
        output_model=SectionHeaderData,
    ),
    _build_layout_entry(
        layout_id="outline-slide",
        name="目录导航页",
        output_model=OutlineSlideData,
    ),
    _build_layout_entry(
        layout_id="bullet-with-icons",
        name="图标要点",
        output_model=BulletWithIconsData,
    ),
    _build_layout_entry(
        layout_id="numbered-bullets",
        name="编号要点",
        output_model=NumberedBulletsData,
    ),
    _build_layout_entry(
        layout_id="metrics-slide",
        name="指标卡片",
        output_model=MetricsSlideData,
    ),
    _build_layout_entry(
        layout_id="metrics-with-image",
        name="指标+配图",
        output_model=MetricsWithImageData,
    ),
    _build_layout_entry(
        layout_id="chart-with-bullets",
        name="图表+要点",
        output_model=ChartWithBulletsData,
    ),
    _build_layout_entry(
        layout_id="table-info",
        name="表格数据",
        output_model=TableInfoData,
    ),
    _build_layout_entry(
        layout_id="two-column-compare",
        name="双栏对比",
        output_model=TwoColumnCompareData,
    ),
    _build_layout_entry(
        layout_id="image-and-description",
        name="图文混排",
        output_model=ImageAndDescriptionData,
    ),
    _build_layout_entry(
        layout_id="timeline",
        name="时间轴",
        output_model=TimelineData,
    ),
    _build_layout_entry(
        layout_id="quote-slide",
        name="引用页",
        output_model=QuoteSlideData,
    ),
    _build_layout_entry(
        layout_id="bullet-icons-only",
        name="纯图标网格",
        output_model=BulletIconsOnlyData,
    ),
    _build_layout_entry(
        layout_id="challenge-outcome",
        name="问题→方案",
        output_model=ChallengeOutcomeData,
    ),
    _build_layout_entry(
        layout_id="thank-you",
        name="致谢页",
        output_model=ThankYouData,
    ),
]

# 索引: layout_id → LayoutEntry
_LAYOUT_MAP: dict[str, LayoutEntry] = {entry.id: entry for entry in _LAYOUTS}


def get_layout(layout_id: str) -> LayoutEntry | None:
    """通过 layout_id 获取布局条目"""
    return _LAYOUT_MAP.get(layout_id)


def get_output_model(layout_id: str) -> type[BaseModel]:
    """获取 layout_id 对应的 Pydantic 输出模型，找不到时回退到 BulletWithIconsData"""
    entry = _LAYOUT_MAP.get(layout_id)
    if entry is None:
        return BulletWithIconsData
    return entry.output_model


def get_all_layouts() -> list[LayoutEntry]:
    """获取所有可用布局"""
    return list(_LAYOUTS)


def get_layout_catalog() -> str:
    """生成供 LLM 参考的布局清单文本（用于 SelectLayouts prompt）"""
    lines: list[str] = []
    for entry in _LAYOUTS:
        legacy_variant = get_layout_variant(entry.id)
        variant_label = get_layout_variant_label(entry.group, legacy_variant)
        lines.append(
            f"- `{entry.id}` ({entry.name}, 角色: {entry.group}, 变体: {variant_label} ({legacy_variant}), "
            f"适用领域: {format_usage_tags(entry.usage_tags)}): "
            f"职责: {entry.notes.purpose} "
            f"结构: {entry.notes.structure_signal} "
            f"设计: {entry.notes.design_signal} "
            f"适用时机: {entry.notes.use_when} "
            f"避免时机: {entry.notes.avoid_when} "
            f"usage 偏向: {entry.notes.usage_bias}"
        )
    return "\n".join(lines)


def get_layout_taxonomy_catalog() -> str:
    """生成以 group / sub_group / layout_id 为主的 selector 候选文本。"""
    lines: list[str] = []
    for entry in _LAYOUTS:
        lines.append(
            f"- `{entry.id}` ({entry.name}, group: {entry.group}, sub_group: {entry.sub_group}, "
            f"usage: {format_usage_tags(entry.usage_tags)}): "
            f"purpose: {entry.notes.purpose} "
            f"structure: {entry.notes.structure_signal} "
            f"design: {entry.notes.design_signal} "
            f"use_when: {entry.notes.use_when} "
            f"avoid_when: {entry.notes.avoid_when} "
            f"usage_bias: {entry.notes.usage_bias}"
        )
    return "\n".join(lines)


def get_layout_variant_catalog() -> str:
    """生成 role -> variant -> layout 的决策清单文本。"""
    grouped_layouts: dict[tuple[str, str], list[LayoutEntry]] = {}
    for entry in _LAYOUTS:
        key = (entry.group, get_layout_variant(entry.id))
        grouped_layouts.setdefault(key, []).append(entry)

    lines: list[str] = []
    for (group, variant), variant_entries in grouped_layouts.items():
        variant_label = get_layout_variant_label(group, variant)
        variant_description = get_layout_variant_description(group, variant)
        layouts_text = ", ".join(
            f"`{candidate.id}`({candidate.name})" for candidate in variant_entries
        )
        lines.append(
            f"- 角色 `{group}` / 变体 `{variant}` ({variant_label}): "
            f"{variant_description} 可用布局: {layouts_text}"
        )

    return "\n".join(lines)


def get_layouts_for_role(role: str) -> list[LayoutEntry]:
    return [entry for entry in _LAYOUTS if entry.group == role]


def get_layouts_for_group_sub_group(group: str, sub_group: str) -> list[LayoutEntry]:
    return [
        entry for entry in _LAYOUTS if entry.group == group and entry.sub_group == sub_group
    ]


def get_layouts_for_role_variant(role: str, variant: str) -> list[LayoutEntry]:
    return [entry for entry in _LAYOUTS if entry.group == role and get_layout_variant(entry.id) == variant]


def get_layout_ids() -> list[str]:
    """获取所有 layout_id 列表"""
    return [entry.id for entry in _LAYOUTS]

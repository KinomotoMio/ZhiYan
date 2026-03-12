"""布局注册中心 — layout_id → Pydantic 模型映射

用于 Pipeline 中的 GenerateSlides 节点，根据 layout_id 动态选择 output_type。
同时提供给 SelectLayouts Agent 的布局清单（id + name + description）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pydantic import BaseModel

from app.services.pipeline.layout_roles import get_layout_role
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
    group: str
    variant: str
    usage_tags: tuple[str, ...]
    output_model: type[BaseModel]


# 所有可用布局
_LAYOUTS: list[LayoutEntry] = [
    LayoutEntry(
        id="intro-slide",
        name="标题页",
        description="演示首页，大标题+副标题+作者信息，适合开场",
        group=get_layout_role("intro-slide"),
        variant=get_layout_variant("intro-slide"),
        usage_tags=get_layout_usage_tags("intro-slide"),
        output_model=IntroSlideData,
    ),
    LayoutEntry(
        id="section-header",
        name="章节过渡",
        description="章节分隔页，大标题+简述，用于主题切换过渡",
        group=get_layout_role("section-header"),
        variant=get_layout_variant("section-header"),
        usage_tags=get_layout_usage_tags("section-header"),
        output_model=SectionHeaderData,
    ),
    LayoutEntry(
        id="outline-slide",
        name="目录导航页",
        description="展示整体汇报框架，通常包含背景、方法、结果、结论等，使用 4-6 个网格卡片呈现章节结构",
        group=get_layout_role("outline-slide"),
        variant=get_layout_variant("outline-slide"),
        usage_tags=get_layout_usage_tags("outline-slide"),
        output_model=OutlineSlideData,
    ),
    LayoutEntry(
        id="bullet-with-icons",
        name="图标要点",
        description="带图标的 3-4 个要点，适合功能介绍、优势列举",
        group=get_layout_role("bullet-with-icons"),
        variant=get_layout_variant("bullet-with-icons"),
        usage_tags=get_layout_usage_tags("bullet-with-icons"),
        output_model=BulletWithIconsData,
    ),
    LayoutEntry(
        id="numbered-bullets",
        name="编号要点",
        description="带编号的步骤列表，适合流程、步骤、方法论",
        group=get_layout_role("numbered-bullets"),
        variant=get_layout_variant("numbered-bullets"),
        usage_tags=get_layout_usage_tags("numbered-bullets"),
        output_model=NumberedBulletsData,
    ),
    LayoutEntry(
        id="metrics-slide",
        name="指标卡片",
        description="展示 2-4 个关键指标/KPI 数字，适合数据概览页",
        group=get_layout_role("metrics-slide"),
        variant=get_layout_variant("metrics-slide"),
        usage_tags=get_layout_usage_tags("metrics-slide"),
        output_model=MetricsSlideData,
    ),
    LayoutEntry(
        id="metrics-with-image",
        name="指标+配图",
        description="指标卡片+右侧图片，适合带视觉的数据展示",
        group=get_layout_role("metrics-with-image"),
        variant=get_layout_variant("metrics-with-image"),
        usage_tags=get_layout_usage_tags("metrics-with-image"),
        output_model=MetricsWithImageData,
    ),
    LayoutEntry(
        id="chart-with-bullets",
        name="图表+要点",
        description="左侧图表右侧要点，适合数据分析+解读",
        group=get_layout_role("chart-with-bullets"),
        variant=get_layout_variant("chart-with-bullets"),
        usage_tags=get_layout_usage_tags("chart-with-bullets"),
        output_model=ChartWithBulletsData,
    ),
    LayoutEntry(
        id="table-info",
        name="表格数据",
        description="结构化表格展示，适合对比、参数、功能矩阵",
        group=get_layout_role("table-info"),
        variant=get_layout_variant("table-info"),
        usage_tags=get_layout_usage_tags("table-info"),
        output_model=TableInfoData,
    ),
    LayoutEntry(
        id="two-column-compare",
        name="双栏对比",
        description="左右两栏对比内容，适合方案比较、优劣分析",
        group=get_layout_role("two-column-compare"),
        variant=get_layout_variant("two-column-compare"),
        usage_tags=get_layout_usage_tags("two-column-compare"),
        output_model=TwoColumnCompareData,
    ),
    LayoutEntry(
        id="image-and-description",
        name="图文混排",
        description="图片+描述文字，适合产品展示、案例说明",
        group=get_layout_role("image-and-description"),
        variant=get_layout_variant("image-and-description"),
        usage_tags=get_layout_usage_tags("image-and-description"),
        output_model=ImageAndDescriptionData,
    ),
    LayoutEntry(
        id="timeline",
        name="时间轴",
        description="时间线/里程碑展示，适合发展历程、项目进度",
        group=get_layout_role("timeline"),
        variant=get_layout_variant("timeline"),
        usage_tags=get_layout_usage_tags("timeline"),
        output_model=TimelineData,
    ),
    LayoutEntry(
        id="quote-slide",
        name="引用页",
        description="重点引述/金句/结论，适合强调核心观点",
        group=get_layout_role("quote-slide"),
        variant=get_layout_variant("quote-slide"),
        usage_tags=get_layout_usage_tags("quote-slide"),
        output_model=QuoteSlideData,
    ),
    LayoutEntry(
        id="bullet-icons-only",
        name="纯图标网格",
        description="4-8 个图标标签的两列能力矩阵，适合技术栈、特性一览",
        group=get_layout_role("bullet-icons-only"),
        variant=get_layout_variant("bullet-icons-only"),
        usage_tags=get_layout_usage_tags("bullet-icons-only"),
        output_model=BulletIconsOnlyData,
    ),
    LayoutEntry(
        id="challenge-outcome",
        name="问题→方案",
        description="挑战和解决方案对比，适合痛点分析、项目成果",
        group=get_layout_role("challenge-outcome"),
        variant=get_layout_variant("challenge-outcome"),
        usage_tags=get_layout_usage_tags("challenge-outcome"),
        output_model=ChallengeOutcomeData,
    ),
    LayoutEntry(
        id="thank-you",
        name="致谢页",
        description="结束页，致谢+联系方式",
        group=get_layout_role("thank-you"),
        variant=get_layout_variant("thank-you"),
        usage_tags=get_layout_usage_tags("thank-you"),
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
        variant_label = get_layout_variant_label(entry.group, entry.variant)
        lines.append(
            f"- `{entry.id}` ({entry.name}, 角色: {entry.group}, 变体: {variant_label} ({entry.variant}), "
            f"适用领域: {format_usage_tags(entry.usage_tags)}): "
            f"{entry.description}"
        )
    return "\n".join(lines)


def get_layout_variant_catalog() -> str:
    """生成 role -> variant -> layout 的决策清单文本。"""
    lines: list[str] = []
    seen_pairs: set[tuple[str, str]] = set()

    for entry in _LAYOUTS:
        key = (entry.group, entry.variant)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)

        variant_entries = [
            candidate
            for candidate in _LAYOUTS
            if candidate.group == entry.group and candidate.variant == entry.variant
        ]
        variant_label = get_layout_variant_label(entry.group, entry.variant)
        variant_description = get_layout_variant_description(entry.group, entry.variant)
        layouts_text = ", ".join(
            f"`{candidate.id}`({candidate.name})" for candidate in variant_entries
        )
        lines.append(
            f"- 角色 `{entry.group}` / 变体 `{entry.variant}` ({variant_label}): "
            f"{variant_description} 可用布局: {layouts_text}"
        )

    return "\n".join(lines)


def get_layouts_for_role(role: str) -> list[LayoutEntry]:
    return [entry for entry in _LAYOUTS if entry.group == role]


def get_layouts_for_role_variant(role: str, variant: str) -> list[LayoutEntry]:
    return [entry for entry in _LAYOUTS if entry.group == role and entry.variant == variant]


def get_layout_ids() -> list[str]:
    """获取所有 layout_id 列表"""
    return [entry.id for entry in _LAYOUTS]

"""布局注册中心 — layout_id → Pydantic 模型映射

用于 Pipeline 中的 GenerateSlides 节点，根据 layout_id 动态选择 output_type。
同时提供给 SelectLayouts Agent 的布局清单（id + name + description）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

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
    output_model: type[BaseModel]


# 所有可用布局
_LAYOUTS: list[LayoutEntry] = [
    LayoutEntry(
        id="intro-slide",
        name="标题页",
        description="演示首页，大标题+副标题+作者信息，适合开场",
        group="general",
        output_model=IntroSlideData,
    ),
    LayoutEntry(
        id="section-header",
        name="章节过渡",
        description="章节分隔页，大标题+简述，用于主题切换过渡",
        group="general",
        output_model=SectionHeaderData,
    ),
    LayoutEntry(
        id="bullet-with-icons",
        name="图标要点",
        description="带图标的 3-4 个要点，适合功能介绍、优势列举",
        group="general",
        output_model=BulletWithIconsData,
    ),
    LayoutEntry(
        id="numbered-bullets",
        name="编号要点",
        description="带编号的步骤列表，适合流程、步骤、方法论",
        group="general",
        output_model=NumberedBulletsData,
    ),
    LayoutEntry(
        id="metrics-slide",
        name="指标卡片",
        description="展示 2-4 个关键指标/KPI 数字，适合数据概览页",
        group="data",
        output_model=MetricsSlideData,
    ),
    LayoutEntry(
        id="metrics-with-image",
        name="指标+配图",
        description="指标卡片+右侧图片，适合带视觉的数据展示",
        group="data",
        output_model=MetricsWithImageData,
    ),
    LayoutEntry(
        id="chart-with-bullets",
        name="图表+要点",
        description="左侧图表右侧要点，适合数据分析+解读",
        group="data",
        output_model=ChartWithBulletsData,
    ),
    LayoutEntry(
        id="table-info",
        name="表格数据",
        description="结构化表格展示，适合对比、参数、功能矩阵",
        group="data",
        output_model=TableInfoData,
    ),
    LayoutEntry(
        id="two-column-compare",
        name="双栏对比",
        description="左右两栏对比内容，适合方案比较、优劣分析",
        group="general",
        output_model=TwoColumnCompareData,
    ),
    LayoutEntry(
        id="image-and-description",
        name="图文混排",
        description="图片+描述文字，适合产品展示、案例说明",
        group="general",
        output_model=ImageAndDescriptionData,
    ),
    LayoutEntry(
        id="timeline",
        name="时间轴",
        description="时间线/里程碑展示，适合发展历程、项目进度",
        group="general",
        output_model=TimelineData,
    ),
    LayoutEntry(
        id="quote-slide",
        name="引用页",
        description="重点引述/金句/结论，适合强调核心观点",
        group="general",
        output_model=QuoteSlideData,
    ),
    LayoutEntry(
        id="bullet-icons-only",
        name="纯图标网格",
        description="4-8 个图标+标签的网格，适合技术栈、特性一览",
        group="general",
        output_model=BulletIconsOnlyData,
    ),
    LayoutEntry(
        id="challenge-outcome",
        name="问题→方案",
        description="挑战和解决方案对比，适合痛点分析、项目成果",
        group="general",
        output_model=ChallengeOutcomeData,
    ),
    LayoutEntry(
        id="thank-you",
        name="致谢页",
        description="结束页，致谢+联系方式",
        group="general",
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
        lines.append(f"- `{entry.id}` ({entry.name}): {entry.description}")
    return "\n".join(lines)


def get_layout_ids() -> list[str]:
    """获取所有 layout_id 列表"""
    return [entry.id for entry in _LAYOUTS]

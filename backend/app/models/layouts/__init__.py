"""Layout content schemas — 每个布局对应一个 Pydantic 数据模型。

这些模型用于约束结构化生成结果，确保输出匹配布局所需的数据形状。
"""

from app.models.layouts.schemas import (
    BulletIconsOnlyData,
    BulletWithIconsData,
    ChallengeOutcomeData,
    ChartWithBulletsData,
    ImageAndDescriptionData,
    IntroSlideData,
    LayoutStatusState,
    MetricsSlideData,
    MetricsWithImageData,
    NumberedBulletsData,
    OutlineRailSlideData,
    OutlineSlideData,
    QuoteSlideData,
    SectionHeaderData,
    TableInfoData,
    ThankYouData,
    TimelineData,
    TwoColumnCompareData,
)

__all__ = [
    "IntroSlideData",
    "SectionHeaderData",
    "OutlineSlideData",
    "OutlineRailSlideData",
    "LayoutStatusState",
    "BulletWithIconsData",
    "NumberedBulletsData",
    "MetricsSlideData",
    "MetricsWithImageData",
    "ChartWithBulletsData",
    "TableInfoData",
    "TwoColumnCompareData",
    "ImageAndDescriptionData",
    "TimelineData",
    "QuoteSlideData",
    "BulletIconsOnlyData",
    "ChallengeOutcomeData",
    "ThankYouData",
]

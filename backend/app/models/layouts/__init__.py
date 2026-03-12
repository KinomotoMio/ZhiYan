"""Layout content schemas — 每个布局的 Pydantic output_type

每个 layout 定义一个 Pydantic 模型，作为 PydanticAI Agent 的 output_type，
确保 LLM 输出严格匹配布局所需的结构化数据。
"""

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

__all__ = [
    "IntroSlideData",
    "SectionHeaderData",
    "OutlineSlideData",
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

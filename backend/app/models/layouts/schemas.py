"""Pydantic schemas for layout content payloads."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class IconRef(BaseModel):
    query: str = Field(description="Icon semantic query, e.g. chart-bar or shield-check")
    resolved_svg: str | None = Field(None, description="Resolved SVG path from assets stage")


class ImageRef(BaseModel):
    source: Literal["ai", "user", "existing"] = Field(
        description="Image source semantics: ai=system generated, user=user supplied, existing=existing asset or URL",
    )
    prompt: str = Field(description="Image prompt or binding instruction")
    url: str | None = Field(None, description="Resolved image URL from assets stage")
    alt: str = Field(default="", description="Alt text for the image")


class ChartData(BaseModel):
    chart_type: str = Field(description="Chart type: bar | line | pie | doughnut | radar")
    labels: list[str] = Field(description="Chart labels")
    datasets: list[dict] = Field(description="Chart datasets")


class IntroSlideData(BaseModel):
    title: str = Field(min_length=2, max_length=40, description="Presentation title")
    subtitle: str = Field(min_length=2, max_length=60, description="Presentation subtitle")
    author: str | None = Field(None, max_length=30, description="Author or team")
    date: str | None = Field(None, max_length=20, description="Date")


class SectionHeaderData(BaseModel):
    title: str = Field(min_length=2, max_length=30, description="Section title")
    subtitle: str | None = Field(None, max_length=60, description="Section subtitle")


class OutlineSectionItem(BaseModel):
    title: str = Field(min_length=2, max_length=20, description="Outline section title")
    description: str | None = Field(None, max_length=36, description="Outline section description")


class OutlineSlideData(BaseModel):
    title: str = Field(min_length=2, max_length=32, description="Outline slide title")
    subtitle: str | None = Field(None, max_length=120, description="Outline slide subtitle")
    sections: list[OutlineSectionItem] = Field(min_length=4, max_length=10, description="Outline sections")


class BulletIconItem(BaseModel):
    icon: IconRef
    title: str = Field(min_length=2, max_length=25, description="Bullet title")
    description: str = Field(max_length=60, description="Bullet description")


class LayoutStatusState(BaseModel):
    title: str = Field(min_length=2, max_length=40, description="Fallback status title")
    message: str = Field(min_length=2, max_length=120, description="Fallback status message")


class BulletWithIconsData(BaseModel):
    title: str = Field(min_length=2, max_length=40, description="Slide title")
    items: list[BulletIconItem] = Field(default_factory=list, max_length=4, description="Bullet items")
    status: LayoutStatusState | None = Field(None, description="Explicit fallback status for unavailable content")

    @model_validator(mode="after")
    def validate_items_or_status(self) -> "BulletWithIconsData":
        has_items = len(self.items) > 0
        if has_items:
            if len(self.items) < 3:
                raise ValueError("bullet-with-icons requires 3-4 items when status is absent")
            if self.status is not None:
                raise ValueError("bullet-with-icons cannot define status when content items are present")
            return self

        if self.status is None:
            raise ValueError("bullet-with-icons requires status when content items are unavailable")
        return self


class NumberedBulletItem(BaseModel):
    title: str = Field(min_length=2, max_length=25, description="Step title")
    description: str = Field(max_length=80, description="Step description")


class NumberedBulletsData(BaseModel):
    title: str = Field(min_length=2, max_length=40, description="Slide title")
    items: list[NumberedBulletItem] = Field(min_length=3, max_length=5, description="Numbered items")


class MetricItem(BaseModel):
    value: str = Field(min_length=1, max_length=15, description="Metric value")
    label: str = Field(min_length=2, max_length=30, description="Metric label")
    description: str | None = Field(None, max_length=60, description="Metric description")
    icon: IconRef | None = None


class MetricsSlideData(BaseModel):
    """Metrics slide with executive summary support."""
    title: str = Field(min_length=2, max_length=40, description="Slide title")
    conclusion: str = Field(min_length=2, max_length=80, description="Executive-summary conclusion")
    conclusionBrief: str = Field(
        min_length=5,
        max_length=180,
        description="Supporting sentence that expands the conclusion",
    )
    metrics: list[MetricItem] = Field(min_length=2, max_length=4, description="Metric cards")


class MetricsWithImageData(BaseModel):
    title: str = Field(min_length=2, max_length=40, description="Slide title")
    metrics: list[MetricItem] = Field(min_length=2, max_length=3, description="Metric cards")
    image: ImageRef = Field(description="Right-side image")


class ChartBulletItem(BaseModel):
    text: str = Field(min_length=5, max_length=60, description="Bullet content")


class ChartWithBulletsData(BaseModel):
    title: str = Field(min_length=2, max_length=40, description="Slide title")
    chart: ChartData = Field(description="Chart data")
    bullets: list[ChartBulletItem] = Field(min_length=2, max_length=4, description="Bullets")


class TableInfoData(BaseModel):
    title: str = Field(min_length=2, max_length=40, description="Slide title")
    headers: list[str] = Field(min_length=2, max_length=6, description="Table headers")
    rows: list[list[str]] = Field(min_length=2, max_length=8, description="Table rows")
    caption: str | None = Field(None, max_length=80, description="Table caption")


class CompareColumn(BaseModel):
    heading: str = Field(min_length=2, max_length=25, description="Column heading")
    items: list[str] = Field(min_length=2, max_length=5, description="Column items")
    icon: IconRef | None = None


class TwoColumnCompareData(BaseModel):
    title: str = Field(min_length=2, max_length=40, description="Slide title")
    left: CompareColumn = Field(description="Left column")
    right: CompareColumn = Field(description="Right column")


class ImageAndDescriptionData(BaseModel):
    title: str = Field(min_length=2, max_length=40, description="Slide title")
    image: ImageRef = Field(description="Illustration image")
    description: str = Field(min_length=20, max_length=200, description="Main description")
    bullets: list[str] | None = Field(None, max_length=3, description="Optional bullets")


class TimelineEvent(BaseModel):
    date: str = Field(min_length=2, max_length=15, description="Timeline date")
    title: str = Field(min_length=2, max_length=30, description="Event title")
    description: str | None = Field(None, max_length=60, description="Event description")


class TimelineData(BaseModel):
    title: str = Field(min_length=2, max_length=40, description="Slide title")
    events: list[TimelineEvent] = Field(min_length=3, max_length=6, description="Timeline events")


class QuoteSlideData(BaseModel):
    quote: str = Field(min_length=10, max_length=150, description="Quote text")
    author: str | None = Field(None, max_length=30, description="Quote author")
    context: str | None = Field(None, max_length=60, description="Quote context")


class IconGridItem(BaseModel):
    icon: IconRef
    label: str = Field(min_length=2, max_length=20, description="Grid label")


class BulletIconsOnlyData(BaseModel):
    title: str = Field(min_length=2, max_length=40, description="Slide title")
    items: list[IconGridItem] = Field(min_length=4, max_length=8, description="Icon grid items")


class ChallengeOutcomeItem(BaseModel):
    challenge: str = Field(min_length=5, max_length=60, description="Challenge")
    outcome: str = Field(min_length=5, max_length=60, description="Outcome")


class ChallengeOutcomeData(BaseModel):
    title: str = Field(min_length=2, max_length=40, description="Slide title")
    items: list[ChallengeOutcomeItem] = Field(min_length=2, max_length=4, description="Challenge/outcome pairs")


class ThankYouData(BaseModel):
    title: str = Field(default="\u8c22\u8c22", min_length=2, max_length=20, description="Thank-you title")
    subtitle: str | None = Field(None, max_length=60, description="Thank-you subtitle")
    contact: str | None = Field(None, max_length=60, description="Contact info")

"""所有布局的 Pydantic 数据模型

每个模型对应一个前端 React 布局组件，LLM 按此 schema 生成结构化内容。
字段约束（min_length/max_length/min_items/max_items）引导 LLM 生成合适长度的内容。
"""

from pydantic import BaseModel, Field


# ---------- 通用子模型 ----------

class IconRef(BaseModel):
    """图标引用 — LLM 输出语义描述，后续 ResolveAssets 替换为实际路径"""
    query: str = Field(description="图标语义描述，如 'chart-bar'、'shield-check'")
    resolved_svg: str | None = Field(None, description="解析后的 SVG 路径（由 ResolveAssets 填充）")


class ImageRef(BaseModel):
    """图片引用 — LLM 输出生成提示，后续 ResolveAssets 替换为实际 URL"""
    prompt: str = Field(description="图片描述/生成提示")
    url: str | None = Field(None, description="解析后的图片 URL（由 ResolveAssets 填充）")
    alt: str = Field(default="", description="图片替代文本")


class ChartData(BaseModel):
    """图表数据"""
    chart_type: str = Field(description="图表类型: bar | line | pie | doughnut | radar")
    labels: list[str] = Field(description="X 轴标签")
    datasets: list[dict] = Field(description="数据集 [{label, data: [...], color?}]")


# ---------- 1. intro-slide ----------

class IntroSlideData(BaseModel):
    """标题页 — 演示首页"""
    title: str = Field(min_length=2, max_length=40, description="演示文稿主标题")
    subtitle: str = Field(min_length=2, max_length=60, description="副标题/简介")
    author: str | None = Field(None, max_length=30, description="作者/团队名")
    date: str | None = Field(None, max_length=20, description="日期")


# ---------- 2. section-header ----------

class SectionHeaderData(BaseModel):
    """章节过渡页"""
    title: str = Field(min_length=2, max_length=30, description="章节标题")
    subtitle: str | None = Field(None, max_length=60, description="章节简述")


# ---------- 3. bullet-with-icons ----------

class BulletIconItem(BaseModel):
    icon: IconRef
    title: str = Field(min_length=2, max_length=25, description="要点标题")
    description: str = Field(max_length=60, description="要点描述")


class BulletWithIconsData(BaseModel):
    """图标要点 — 带图标的 3-4 个要点"""
    title: str = Field(min_length=2, max_length=40, description="页面标题")
    items: list[BulletIconItem] = Field(min_length=3, max_length=4, description="要点列表")


# ---------- 4. numbered-bullets ----------

class NumberedBulletItem(BaseModel):
    title: str = Field(min_length=2, max_length=25, description="步骤标题")
    description: str = Field(max_length=80, description="步骤描述")


class NumberedBulletsData(BaseModel):
    """编号要点 — 步骤/流程"""
    title: str = Field(min_length=2, max_length=40, description="页面标题")
    items: list[NumberedBulletItem] = Field(min_length=3, max_length=5, description="编号步骤")


# ---------- 5. metrics-slide ----------

class MetricItem(BaseModel):
    value: str = Field(min_length=1, max_length=15, description="指标数值，如 '97.3%'")
    label: str = Field(min_length=2, max_length=30, description="指标名称")
    description: str | None = Field(None, max_length=60, description="补充说明")
    icon: IconRef | None = None


class MetricsSlideData(BaseModel):
    """指标卡片 — 2-4 个 KPI 数字"""
    title: str = Field(min_length=2, max_length=40, description="页面标题")
    metrics: list[MetricItem] = Field(min_length=2, max_length=4, description="指标列表")


# ---------- 6. metrics-with-image ----------

class MetricsWithImageData(BaseModel):
    """指标+配图 — 指标卡片 + 右侧图片"""
    title: str = Field(min_length=2, max_length=40, description="页面标题")
    metrics: list[MetricItem] = Field(min_length=2, max_length=3, description="指标列表")
    image: ImageRef = Field(description="右侧配图")


# ---------- 7. chart-with-bullets ----------

class ChartBulletItem(BaseModel):
    text: str = Field(min_length=5, max_length=60, description="要点内容")


class ChartWithBulletsData(BaseModel):
    """图表+要点 — 左图表右要点"""
    title: str = Field(min_length=2, max_length=40, description="页面标题")
    chart: ChartData = Field(description="图表数据")
    bullets: list[ChartBulletItem] = Field(min_length=2, max_length=4, description="要点")


# ---------- 8. table-info ----------

class TableInfoData(BaseModel):
    """表格数据"""
    title: str = Field(min_length=2, max_length=40, description="页面标题")
    headers: list[str] = Field(min_length=2, max_length=6, description="表头列名")
    rows: list[list[str]] = Field(min_length=2, max_length=8, description="数据行")
    caption: str | None = Field(None, max_length=80, description="表格说明")


# ---------- 9. two-column-compare ----------

class CompareColumn(BaseModel):
    heading: str = Field(min_length=2, max_length=25, description="列标题")
    items: list[str] = Field(min_length=2, max_length=5, description="该列的要点")
    icon: IconRef | None = None


class TwoColumnCompareData(BaseModel):
    """双栏对比"""
    title: str = Field(min_length=2, max_length=40, description="页面标题")
    left: CompareColumn = Field(description="左侧内容")
    right: CompareColumn = Field(description="右侧内容")


# ---------- 10. image-and-description ----------

class ImageAndDescriptionData(BaseModel):
    """图文混排 — 图片+描述文字"""
    title: str = Field(min_length=2, max_length=40, description="页面标题")
    image: ImageRef = Field(description="配图")
    description: str = Field(min_length=20, max_length=200, description="描述文字")
    bullets: list[str] | None = Field(None, max_length=3, description="补充要点")


# ---------- 11. timeline ----------

class TimelineEvent(BaseModel):
    date: str = Field(min_length=2, max_length=15, description="时间点，如 '2024 Q1'")
    title: str = Field(min_length=2, max_length=30, description="事件标题")
    description: str | None = Field(None, max_length=60, description="事件描述")


class TimelineData(BaseModel):
    """时间轴 — 里程碑/进展"""
    title: str = Field(min_length=2, max_length=40, description="页面标题")
    events: list[TimelineEvent] = Field(min_length=3, max_length=6, description="时间节点")


# ---------- 12. quote-slide ----------

class QuoteSlideData(BaseModel):
    """引用页 — 重点引述/结论"""
    quote: str = Field(min_length=10, max_length=150, description="引用内容")
    author: str | None = Field(None, max_length=30, description="引用来源/作者")
    context: str | None = Field(None, max_length=60, description="上下文说明")


# ---------- 13. bullet-icons-only ----------

class IconGridItem(BaseModel):
    icon: IconRef
    label: str = Field(min_length=2, max_length=20, description="图标标签")


class BulletIconsOnlyData(BaseModel):
    """纯图标网格 — 特性/优势展示"""
    title: str = Field(min_length=2, max_length=40, description="页面标题")
    items: list[IconGridItem] = Field(min_length=4, max_length=8, description="图标网格项")


# ---------- 14. challenge-outcome ----------

class ChallengeOutcomeItem(BaseModel):
    challenge: str = Field(min_length=5, max_length=60, description="挑战/问题")
    outcome: str = Field(min_length=5, max_length=60, description="方案/结果")


class ChallengeOutcomeData(BaseModel):
    """问题→方案 — 挑战和解决方案对比"""
    title: str = Field(min_length=2, max_length=40, description="页面标题")
    items: list[ChallengeOutcomeItem] = Field(min_length=2, max_length=4, description="挑战-方案对")


# ---------- 15. thank-you ----------

class ThankYouData(BaseModel):
    """致谢页"""
    title: str = Field(default="谢谢", min_length=2, max_length=20, description="致谢标题")
    subtitle: str | None = Field(None, max_length=60, description="副标题/联系方式")
    contact: str | None = Field(None, max_length=60, description="联系信息")

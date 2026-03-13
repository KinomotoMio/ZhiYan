"""甯冨眬娉ㄥ唽涓績 鈥?layout_id 鈫?Pydantic 妯″瀷鏄犲皠銆?

鐢ㄤ簬 Pipeline 涓殑 GenerateSlides 鑺傜偣锛屾牴鎹?layout_id 鍔ㄦ€侀€夋嫨 output_type銆?
瀵瑰姝ｅ紡鏆撮湶涓夊眰 taxonomy 杩愯鏃跺瓧娈碉紝鍚屾椂淇濈暀 selector 褰撳墠浣跨敤鐨勬棫鍏煎鏂囨湰鎺ュ彛銆?
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


# 鎵€鏈夊彲鐢ㄥ竷灞€
_LAYOUTS: list[LayoutEntry] = [
    _build_layout_entry(
        layout_id="intro-slide",
        name="鏍囬椤?,
        output_model=IntroSlideData,
    ),
    _build_layout_entry(
        layout_id="section-header",
        name="绔犺妭杩囨浮",
        output_model=SectionHeaderData,
    ),
    _build_layout_entry(
        layout_id="outline-slide",
        name="鐩綍瀵艰埅椤?,
        output_model=OutlineSlideData,
    ),
    _build_layout_entry(
        layout_id="bullet-with-icons",
        name="鍥炬爣瑕佺偣",
        output_model=BulletWithIconsData,
    ),
    _build_layout_entry(
        layout_id="numbered-bullets",
        name="缂栧彿瑕佺偣",
        output_model=NumberedBulletsData,
    ),
    _build_layout_entry(
        layout_id="metrics-slide",
        name="鎸囨爣鍗＄墖",
        output_model=MetricsSlideData,
    ),
    _build_layout_entry(
        layout_id="metrics-with-image",
        name="鎸囨爣+閰嶅浘",
        output_model=MetricsWithImageData,
    ),
    _build_layout_entry(
        layout_id="chart-with-bullets",
        name="鍥捐〃+瑕佺偣",
        output_model=ChartWithBulletsData,
    ),
    _build_layout_entry(
        layout_id="table-info",
        name="琛ㄦ牸鏁版嵁",
        output_model=TableInfoData,
    ),
    _build_layout_entry(
        layout_id="two-column-compare",
        name="鍙屾爮瀵规瘮",
        output_model=TwoColumnCompareData,
    ),
    _build_layout_entry(
        layout_id="image-and-description",
        name="鍥炬枃娣锋帓",
        output_model=ImageAndDescriptionData,
    ),
    _build_layout_entry(
        layout_id="timeline",
        name="鏃堕棿杞?,
        output_model=TimelineData,
    ),
    _build_layout_entry(
        layout_id="quote-slide",
        name="寮曠敤椤?,
        output_model=QuoteSlideData,
    ),
    _build_layout_entry(
        layout_id="bullet-icons-only",
        name="绾浘鏍囩綉鏍?,
        output_model=BulletIconsOnlyData,
    ),
    _build_layout_entry(
        layout_id="challenge-outcome",
        name="闂鈫掓柟妗?,
        output_model=ChallengeOutcomeData,
    ),
    _build_layout_entry(
        layout_id="thank-you",
        name="鑷磋阿椤?,
        output_model=ThankYouData,
    ),
]

# 绱㈠紩: layout_id 鈫?LayoutEntry
_LAYOUT_MAP: dict[str, LayoutEntry] = {entry.id: entry for entry in _LAYOUTS}


def get_layout(layout_id: str) -> LayoutEntry | None:
    """閫氳繃 layout_id 鑾峰彇甯冨眬鏉＄洰"""
    return _LAYOUT_MAP.get(layout_id)


def get_output_model(layout_id: str) -> type[BaseModel]:
    """鑾峰彇 layout_id 瀵瑰簲鐨?Pydantic 杈撳嚭妯″瀷锛屾壘涓嶅埌鏃跺洖閫€鍒?BulletWithIconsData"""
    entry = _LAYOUT_MAP.get(layout_id)
    if entry is None:
        return BulletWithIconsData
    return entry.output_model


def get_all_layouts() -> list[LayoutEntry]:
    """鑾峰彇鎵€鏈夊彲鐢ㄥ竷灞€"""
    return list(_LAYOUTS)


def get_layout_catalog() -> str:
    """鐢熸垚渚?LLM 鍙傝€冪殑甯冨眬娓呭崟鏂囨湰锛堢敤浜?SelectLayouts prompt锛?""
    lines: list[str] = []
    for entry in _LAYOUTS:
        legacy_variant = get_layout_variant(entry.id)
        variant_label = get_layout_variant_label(entry.group, legacy_variant)
        lines.append(
            f"- `{entry.id}` ({entry.name}, 瑙掕壊: {entry.group}, 鍙樹綋: {variant_label} ({legacy_variant}), "
            f"閫傜敤棰嗗煙: {format_usage_tags(entry.usage_tags)}): "
            f"鑱岃矗: {entry.notes.purpose} "
            f"缁撴瀯: {entry.notes.structure_signal} "
            f"璁捐: {entry.notes.design_signal} "
            f"閫傜敤鏃舵満: {entry.notes.use_when} "
            f"閬垮厤鏃舵満: {entry.notes.avoid_when} "
            f"usage 鍋忓悜: {entry.notes.usage_bias}"
        )
    return "\n".join(lines)


def get_layout_taxonomy_catalog() -> str:
    """鐢熸垚浠?group / sub_group / layout_id 涓轰富鐨?selector 鍊欓€夋枃鏈€?""
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
    """鐢熸垚 role -> variant -> layout 鐨勫喅绛栨竻鍗曟枃鏈€?""
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
            f"- 瑙掕壊 `{group}` / 鍙樹綋 `{variant}` ({variant_label}): "
            f"{variant_description} 鍙敤甯冨眬: {layouts_text}"
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
    """鑾峰彇鎵€鏈?layout_id 鍒楄〃"""
    return [entry.id for entry in _LAYOUTS]
"""Usage metadata and rule-based inference for layout selection."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from app.services.layouts.layout_metadata import get_layout_metadata_entry, load_layout_metadata

USAGE_LABELS: dict[str, str] = dict(load_layout_metadata()["usageLabels"])

USAGE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "academic-report": (
        "答辩",
        "论文",
        "实验",
        "研究",
        "学术",
        "期刊",
        "综述",
        "方法",
        "模型评估",
        "conference paper",
        "research",
        "experiment",
        "thesis",
        "defense",
        "evaluation",
    ),
    "business-report": (
        "商业",
        "汇报",
        "经营",
        "复盘",
        "战略",
        "业绩",
        "kpi",
        "okr",
        "营收",
        "增长",
        "strategy",
        "business review",
        "quarterly review",
        "annual review",
    ),
    "sales-pitch": (
        "销售",
        "提案",
        "客户方案",
        "招投标",
        "商机",
        "售前",
        "解决方案建议书",
        "proposal",
        "pitch",
        "client",
        "rfp",
        "tender",
        "sales deck",
    ),
    "investor-pitch": (
        "融资",
        "路演",
        "投资人",
        "募资",
        "估值",
        "创业",
        "商业模式",
        "investor",
        "fundraise",
        "startup",
        "seed round",
        "series a",
        "pitch deck",
    ),
    "training-workshop": (
        "培训",
        "课程",
        "教学",
        "课件",
        "工作坊",
        "入职",
        "上手指南",
        "workshop",
        "training",
        "lesson",
        "curriculum",
        "onboarding",
        "tutorial",
    ),
    "conference-keynote": (
        "大会",
        "演讲",
        "峰会",
        "论坛",
        "发布会",
        "主旨",
        "分享",
        "keynote",
        "conference",
        "summit",
        "forum",
        "speaker",
        "talk",
    ),
    "project-status": (
        "周报",
        "月报",
        "项目进展",
        "里程碑",
        "状态更新",
        "进度",
        "项目汇报",
        "status update",
        "milestone",
        "roadmap",
        "project update",
        "progress",
    ),
    "product-demo": (
        "产品介绍",
        "产品演示",
        "功能演示",
        "产品发布",
        "方案演示",
        "界面演示",
        "demo",
        "walkthrough",
        "feature showcase",
        "product launch",
        "product overview",
        "release",
    ),
}


def get_usage_label(tag: str) -> str:
    return USAGE_LABELS.get(tag, tag)


def get_layout_usage_tags(layout_id: str) -> tuple[str, ...]:
    entry = get_layout_metadata_entry(layout_id)
    usage = entry.get("usage", [])
    return tuple(str(tag) for tag in usage)


def format_usage_tags(tags: Sequence[str]) -> str:
    if not tags:
        return "未命中"
    return "、".join(get_usage_label(tag) for tag in tags)


def infer_usage_tags(texts: Iterable[str], *, limit: int = 3) -> tuple[str, ...]:
    haystack = " \n ".join(text for text in texts if text).lower()
    if not haystack.strip():
        return ()

    scores: dict[str, int] = {}
    for tag, keywords in USAGE_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            token = keyword.strip().lower()
            if not token:
                continue
            score += haystack.count(token)
        if score > 0:
            scores[tag] = score

    if not scores:
        return ()

    ranked = sorted(
        scores.items(),
        key=lambda item: (-item[1], list(USAGE_LABELS).index(item[0])),
    )
    return tuple(tag for tag, _ in ranked[:limit])


def infer_document_and_slide_usage(
    topic: str,
    content: str,
    outline_items: Sequence[dict[str, Any]],
) -> tuple[tuple[str, ...], dict[int, tuple[str, ...]]]:
    document_usage = infer_usage_tags((topic, content))
    slide_usage: dict[int, tuple[str, ...]] = {}

    for item in outline_items:
        slide_number = item.get("slide_number")
        if not isinstance(slide_number, int):
            continue

        key_points = item.get("key_points", [])
        key_point_text = "\n".join(
            str(point).strip()
            for point in key_points
            if isinstance(point, str) and point.strip()
        )
        tags = infer_usage_tags(
            (
                topic,
                str(item.get("title") or ""),
                str(item.get("content_brief") or ""),
                key_point_text,
            )
        )
        if tags:
            slide_usage[slide_number] = tags

    return document_usage, slide_usage


def rank_layouts_by_usage(
    layout_entries: Sequence[Any],
    usage_tags: Sequence[str],
    *,
    limit: int = 5,
) -> list[Any]:
    if not usage_tags:
        return []

    usage_set = set(usage_tags)
    ranked = sorted(
        (
            (
                len(usage_set.intersection(getattr(entry, "usage_tags", ()))),
                len(getattr(entry, "usage_tags", ())),
                entry,
            )
            for entry in layout_entries
        ),
        key=lambda item: (-item[0], item[1], getattr(item[2], "id", "")),
    )
    matched = [entry for overlap, _, entry in ranked if overlap > 0]
    return matched[:limit]

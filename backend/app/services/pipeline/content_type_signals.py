"""Content-type signal inference for layout sub-group selection.

This module provides two local strategies:
- rules: deterministic keyword/rule scoring
- semantic: lightweight prototype matching (no external dependency)
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

CONTENT_STRATEGY_RULES = "rules"
CONTENT_STRATEGY_SEMANTIC = "semantic"
CONTENT_STRATEGIES = (CONTENT_STRATEGY_RULES, CONTENT_STRATEGY_SEMANTIC)

CONTENT_TYPE_UNKNOWN = "unknown"
_CONTENT_TYPES = ("chart", "table", "timeline", "image", CONTENT_TYPE_UNKNOWN)

_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "chart": (
        "图表",
        "曲线",
        "折线",
        "柱状",
        "趋势",
        "走势",
        "分析",
        "chart",
        "graph",
        "trend",
        "analysis",
        "metric",
    ),
    "table": (
        "表格",
        "矩阵",
        "行列",
        "参数",
        "规格",
        "清单",
        "table",
        "matrix",
        "tabular",
        "parameter",
        "spec",
    ),
    "timeline": (
        "时间线",
        "里程碑",
        "排期",
        "阶段",
        "路线图",
        "roadmap",
        "timeline",
        "milestone",
        "quarter",
        "month",
        "week",
    ),
    "image": (
        "图片",
        "配图",
        "截图",
        "界面",
        "视觉",
        "照片",
        "案例",
        "场景",
        "image",
        "visual",
        "photo",
        "screenshot",
        "showcase",
    ),
}

_TYPE_PROTOTYPES: dict[str, tuple[str, ...]] = {
    "chart": (
        "趋势",
        "指标",
        "同比",
        "环比",
        "曲线",
        "增长",
        "分布",
        "trend",
        "metric",
        "chart",
        "benchmark",
        "analysis",
    ),
    "table": (
        "参数",
        "规格",
        "对照",
        "行列",
        "矩阵",
        "清单",
        "table",
        "tabular",
        "matrix",
        "spec",
        "field",
    ),
    "timeline": (
        "阶段",
        "里程碑",
        "时间",
        "路线图",
        "季度",
        "计划",
        "timeline",
        "milestone",
        "roadmap",
        "schedule",
        "q1",
        "q2",
        "q3",
        "q4",
    ),
    "image": (
        "配图",
        "截图",
        "界面",
        "案例",
        "场景",
        "视觉",
        "image",
        "photo",
        "screenshot",
        "visual",
        "mockup",
        "showcase",
    ),
}

_ROLE_SUB_GROUP_MAP: dict[str, dict[str, str]] = {
    "evidence": {
        "chart": "chart-analysis",
        "table": "table-matrix",
        "image": "visual-evidence",
    },
    "process": {
        "timeline": "timeline-milestone",
    },
    "narrative": {
        "image": "visual-explainer",
    },
}


def _normalize_hints(item: Mapping[str, Any]) -> list[str]:
    raw = item.get("content_hints", [])
    if not isinstance(raw, list):
        return []

    canonical: list[str] = []
    for hint in raw:
        if not isinstance(hint, str):
            continue
        token = hint.strip().lower()
        if not token:
            continue
        if token in {"graph", "plot"}:
            token = "chart"
        elif token in {"tabular", "matrix"}:
            token = "table"
        elif token in {"roadmap", "milestone"}:
            token = "timeline"
        elif token in {"visual", "photo", "screenshot"}:
            token = "image"
        if token in _CONTENT_TYPES and token != CONTENT_TYPE_UNKNOWN and token not in canonical:
            canonical.append(token)
    return canonical


def _item_text(item: Mapping[str, Any]) -> str:
    key_points = item.get("key_points", [])
    key_point_text = "\n".join(
        str(point).strip()
        for point in key_points
        if isinstance(point, str) and point.strip()
    )
    return "\n".join(
        [
            str(item.get("title") or ""),
            str(item.get("content_brief") or ""),
            key_point_text,
        ]
    ).lower()


def _role_to_sub_group(role: str, predicted_type: str) -> str:
    return _ROLE_SUB_GROUP_MAP.get(role, {}).get(predicted_type, "")


def _normalize_structure_signals(structure_signals: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return structure_signals if isinstance(structure_signals, Mapping) else {}


def _normalize_source_hints(source_hints: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return source_hints if isinstance(source_hints, Mapping) else {}


def _result(
    *,
    predicted_type: str,
    confidence: float,
    evidence_tokens: Sequence[str],
    strategy: str,
    role: str,
) -> dict[str, Any]:
    tag = predicted_type if predicted_type in _CONTENT_TYPES else CONTENT_TYPE_UNKNOWN
    return {
        "predicted_type": tag,
        "confidence": round(max(0.0, min(1.0, float(confidence))), 4),
        "evidence_tokens": [str(token) for token in evidence_tokens if str(token).strip()][:6],
        "strategy": strategy,
        "suggested_sub_group": _role_to_sub_group(role, tag),
    }


def infer_rules_signal(
    item: Mapping[str, Any],
    *,
    role: str,
    source_hints: Mapping[str, Any] | None = None,
    structure_signals: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    text = _item_text(item)
    hints = _normalize_hints(item)
    source = _normalize_source_hints(source_hints)
    structure = _normalize_structure_signals(structure_signals)

    # Hard signal from explicit content_hints.
    for hint in hints:
        if _role_to_sub_group(role, hint):
            return _result(
                predicted_type=hint,
                confidence=0.96,
                evidence_tokens=[f"content_hint:{hint}"],
                strategy=CONTENT_STRATEGY_RULES,
                role=role,
            )

    scores: dict[str, float] = defaultdict(float)
    evidence: dict[str, list[str]] = defaultdict(list)

    for content_type, keywords in _TYPE_KEYWORDS.items():
        for keyword in keywords:
            token = keyword.lower()
            if token and token in text:
                scores[content_type] += 0.12
                if token not in evidence[content_type]:
                    evidence[content_type].append(token)

    table_count = int(structure.get("table_count") or 0)
    image_count = int(structure.get("image_count") or 0)
    if table_count > 0:
        scores["table"] += min(0.5, 0.2 + table_count * 0.05)
        evidence["table"].append("structure:table_count")
    if image_count > 0:
        scores["image"] += min(0.45, 0.18 + image_count * 0.05)
        evidence["image"].append("structure:image_count")
    if structure.get("timeline_date_hits") or structure.get("timeline_quarter_hits"):
        scores["timeline"] += 0.35
        evidence["timeline"].append("structure:timeline_hits")
    if structure.get("chart_keyword_hits"):
        scores["chart"] += 0.25
        evidence["chart"].append("structure:chart_keywords")
    if structure.get("table_keyword_hits"):
        scores["table"] += 0.2
        evidence["table"].append("structure:table_keywords")
    if structure.get("timeline_keyword_hits"):
        scores["timeline"] += 0.2
        evidence["timeline"].append("structure:timeline_keywords")

    source_images = int(source.get("images") or 0)
    if source_images > 0:
        scores["image"] += min(0.35, 0.1 + source_images * 0.05)
        evidence["image"].append("source_hints:images")

    if not scores:
        return _result(
            predicted_type=CONTENT_TYPE_UNKNOWN,
            confidence=0.0,
            evidence_tokens=[],
            strategy=CONTENT_STRATEGY_RULES,
            role=role,
        )

    ranked = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    predicted_type, raw_score = ranked[0]
    confidence = min(0.94, 0.35 + raw_score)
    return _result(
        predicted_type=predicted_type,
        confidence=confidence,
        evidence_tokens=evidence.get(predicted_type, []),
        strategy=CONTENT_STRATEGY_RULES,
        role=role,
    )


def infer_semantic_signal(
    item: Mapping[str, Any],
    *,
    role: str,
    source_hints: Mapping[str, Any] | None = None,
    structure_signals: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    text = _item_text(item)
    source = _normalize_source_hints(source_hints)
    structure = _normalize_structure_signals(structure_signals)

    # Inject lightweight pseudo-tokens to incorporate non-text structural signals.
    pseudo_tokens: list[str] = []
    if int(source.get("images") or 0) > 0:
        pseudo_tokens.extend(["image", "visual"])
    if int(structure.get("table_count") or 0) > 0:
        pseudo_tokens.extend(["table", "matrix"])
    if structure.get("timeline_date_hits") or structure.get("timeline_quarter_hits"):
        pseudo_tokens.extend(["timeline", "milestone"])
    pseudo_text = f"{text}\n{' '.join(pseudo_tokens)}"

    best_type = CONTENT_TYPE_UNKNOWN
    best_score = 0.0
    best_hits: list[str] = []

    for content_type, prototypes in _TYPE_PROTOTYPES.items():
        hits = [token for token in prototypes if token in pseudo_text]
        if not hits:
            continue
        score = len(hits) / max(3.0, len(prototypes) * 0.45)
        if score > best_score:
            best_type = content_type
            best_score = score
            best_hits = hits

    if best_type == CONTENT_TYPE_UNKNOWN:
        return _result(
            predicted_type=CONTENT_TYPE_UNKNOWN,
            confidence=0.0,
            evidence_tokens=[],
            strategy=CONTENT_STRATEGY_SEMANTIC,
            role=role,
        )

    confidence = min(0.93, 0.25 + best_score)
    return _result(
        predicted_type=best_type,
        confidence=confidence,
        evidence_tokens=best_hits,
        strategy=CONTENT_STRATEGY_SEMANTIC,
        role=role,
    )


def _apply_confidence_threshold(signal: Mapping[str, Any], threshold: float) -> dict[str, Any]:
    bounded_threshold = max(0.0, min(1.0, float(threshold)))
    predicted = str(signal.get("predicted_type") or CONTENT_TYPE_UNKNOWN)
    confidence = float(signal.get("confidence") or 0.0)
    if predicted == CONTENT_TYPE_UNKNOWN or confidence >= bounded_threshold:
        return dict(signal)

    result = dict(signal)
    result["predicted_type"] = CONTENT_TYPE_UNKNOWN
    result["suggested_sub_group"] = ""
    return result


def infer_content_signals(
    item: Mapping[str, Any],
    *,
    role: str,
    primary_strategy: str,
    shadow_enabled: bool,
    confidence_threshold: float,
    source_hints: Mapping[str, Any] | None = None,
    structure_signals: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    strategy = primary_strategy if primary_strategy in CONTENT_STRATEGIES else CONTENT_STRATEGY_RULES
    rules_signal = infer_rules_signal(
        item,
        role=role,
        source_hints=source_hints,
        structure_signals=structure_signals,
    )
    semantic_signal = infer_semantic_signal(
        item,
        role=role,
        source_hints=source_hints,
        structure_signals=structure_signals,
    )

    by_strategy = {
        CONTENT_STRATEGY_RULES: rules_signal,
        CONTENT_STRATEGY_SEMANTIC: semantic_signal,
    }
    primary_raw = by_strategy[strategy]
    primary = _apply_confidence_threshold(primary_raw, confidence_threshold)

    signal_source = strategy if str(primary.get("predicted_type")) != CONTENT_TYPE_UNKNOWN else "fallback"
    primary["signal_source"] = signal_source

    shadow: dict[str, Any] | None = None
    if shadow_enabled:
        other = (
            CONTENT_STRATEGY_SEMANTIC
            if strategy == CONTENT_STRATEGY_RULES
            else CONTENT_STRATEGY_RULES
        )
        shadow_raw = by_strategy[other]
        shadow = _apply_confidence_threshold(shadow_raw, confidence_threshold)
        shadow["signal_source"] = other if str(shadow.get("predicted_type")) != CONTENT_TYPE_UNKNOWN else "fallback"

    return {
        "primary": primary,
        "shadow": shadow,
    }

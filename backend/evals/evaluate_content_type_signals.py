#!/usr/bin/env python3
"""Offline baseline evaluation for content-type strategies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.pipeline.content_type_signals import (  # noqa: E402
    CONTENT_STRATEGY_RULES,
    CONTENT_STRATEGY_SEMANTIC,
    CONTENT_TYPE_UNKNOWN,
    infer_content_signals,
)

LABELS = ("chart", "table", "timeline", "image", CONTENT_TYPE_UNKNOWN)


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Dataset must be a JSON array.")
    rows: list[dict[str, Any]] = []
    for idx, sample in enumerate(payload, start=1):
        if not isinstance(sample, dict):
            raise ValueError(f"Dataset row {idx} is not an object.")
        expected = str(sample.get("expected_type") or "").strip().lower()
        if expected not in LABELS:
            raise ValueError(f"Dataset row {idx} has invalid expected_type: {expected!r}")
        rows.append(sample)
    return rows


def _predict(
    sample: dict[str, Any],
    *,
    strategy: str,
    threshold: float,
) -> str:
    item = {
        "title": sample.get("title", ""),
        "content_brief": sample.get("content_brief", ""),
        "key_points": sample.get("key_points", []),
        "content_hints": sample.get("content_hints", []),
    }
    role = str(sample.get("role") or "narrative")
    source_hints = sample.get("source_hints")
    structure_signals = sample.get("structure_signals")
    signal_bundle = infer_content_signals(
        item,
        role=role,
        primary_strategy=strategy,
        shadow_enabled=False,
        confidence_threshold=threshold,
        source_hints=source_hints if isinstance(source_hints, dict) else None,
        structure_signals=structure_signals if isinstance(structure_signals, dict) else None,
    )
    primary = signal_bundle.get("primary") or {}
    predicted = str(primary.get("predicted_type") or CONTENT_TYPE_UNKNOWN)
    return predicted if predicted in LABELS else CONTENT_TYPE_UNKNOWN


def _evaluate(rows: list[dict[str, Any]], strategy: str, threshold: float) -> dict[str, Any]:
    matrix: dict[str, dict[str, int]] = {
        gold: {pred: 0 for pred in LABELS} for gold in LABELS
    }
    total = 0
    correct = 0
    for sample in rows:
        gold = str(sample["expected_type"])
        pred = _predict(sample, strategy=strategy, threshold=threshold)
        matrix[gold][pred] += 1
        total += 1
        if gold == pred:
            correct += 1

    per_label: dict[str, dict[str, float]] = {}
    macro_precision = 0.0
    macro_recall = 0.0
    macro_f1 = 0.0

    for label in LABELS:
        tp = matrix[label][label]
        fp = sum(matrix[gold][label] for gold in LABELS if gold != label)
        fn = sum(matrix[label][pred] for pred in LABELS if pred != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
        support = sum(matrix[label].values())
        per_label[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": float(support),
        }
        macro_precision += precision
        macro_recall += recall
        macro_f1 += f1

    label_count = float(len(LABELS))
    return {
        "strategy": strategy,
        "samples": total,
        "top1_accuracy": (correct / total) if total else 0.0,
        "macro_precision": macro_precision / label_count,
        "macro_recall": macro_recall / label_count,
        "macro_f1": macro_f1 / label_count,
        "per_label": per_label,
        "matrix": matrix,
    }


def _format_confusion_matrix(matrix: dict[str, dict[str, int]]) -> str:
    header = ["gold\\pred", *LABELS]
    rows = [header]
    for gold in LABELS:
        rows.append([gold, *(str(matrix[gold][pred]) for pred in LABELS)])
    widths = [max(len(row[col]) for row in rows) for col in range(len(header))]
    lines: list[str] = []
    for row_index, row in enumerate(rows):
        padded = " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(row))
        lines.append(padded)
        if row_index == 0:
            lines.append("-+-".join("-" * width for width in widths))
    return "\n".join(lines)


def _print_result(result: dict[str, Any]) -> None:
    print(f"Strategy: {result['strategy']}")
    print(f"Samples: {result['samples']}")
    print(f"Top1 accuracy: {result['top1_accuracy']:.4f}")
    print(f"Macro precision: {result['macro_precision']:.4f}")
    print(f"Macro recall: {result['macro_recall']:.4f}")
    print(f"Macro F1: {result['macro_f1']:.4f}")
    print("Confusion matrix (rows=gold, cols=pred):")
    print(_format_confusion_matrix(result["matrix"]))
    print("")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).with_name("content_type_baseline_dataset.json"),
        help="Path to JSON dataset file.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.55,
        help="Confidence threshold used in production fallback behavior.",
    )
    args = parser.parse_args()

    rows = _load_dataset(args.dataset)
    print(f"Dataset: {args.dataset} (n={len(rows)})")
    print(f"Threshold: {args.threshold:.2f}")
    print("")

    for strategy in (CONTENT_STRATEGY_RULES, CONTENT_STRATEGY_SEMANTIC):
        result = _evaluate(rows, strategy, args.threshold)
        _print_result(result)


if __name__ == "__main__":
    main()

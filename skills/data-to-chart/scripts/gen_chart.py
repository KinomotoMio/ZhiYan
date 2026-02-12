"""Data to Chart — 数据解析 + 图表配置生成

将 CSV/JSON/Markdown 表格数据转化为图表组件配置。
"""

import csv
import io
import json
import sys
from typing import Any


def parse_csv(text: str) -> list[dict[str, Any]]:
    """解析 CSV 文本为字典列表"""
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def recommend_chart_type(data: list[dict], columns: list[str]) -> str:
    """根据数据特征推荐图表类型"""
    if len(columns) < 2:
        return "bar"

    numeric_cols = []
    for col in columns:
        try:
            [float(row[col]) for row in data[:5]]
            numeric_cols.append(col)
        except (ValueError, KeyError):
            pass

    num_rows = len(data)
    num_numeric = len(numeric_cols)

    if num_numeric >= 2 and num_rows > 10:
        return "scatter"
    if num_rows <= 6 and num_numeric == 1:
        return "pie"
    if num_rows > 10:
        return "line"
    return "bar"


def generate_chart_config(
    data: list[dict], chart_type: str, columns: list[str]
) -> dict[str, Any]:
    """生成图表组件配置"""
    label_col = columns[0]
    value_cols = columns[1:]

    return {
        "chartType": chart_type,
        "labels": [row[label_col] for row in data],
        "datasets": [
            {
                "label": col,
                "data": [_to_number(row.get(col, 0)) for row in data],
            }
            for col in value_cols
        ],
    }


def _to_number(val: Any) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


if __name__ == "__main__":
    input_data = json.load(sys.stdin)
    raw_text = input_data.get("data", "")
    override_type = input_data.get("chartType")

    rows = parse_csv(raw_text)
    if not rows:
        json.dump({"error": "无法解析数据"}, sys.stdout, ensure_ascii=False)
        sys.exit(1)

    cols = list(rows[0].keys())
    chart_type = override_type or recommend_chart_type(rows, cols)
    config = generate_chart_config(rows, chart_type, cols)

    json.dump(config, sys.stdout, ensure_ascii=False, indent=2)

---
name: data-to-chart
description: 分析用户上传的数据文件或粘贴的数据，推荐合适的图表类型，生成图表并插入当前选中的幻灯片。
version: 0.1.0
command: /data-to-chart
---

# Data to Chart

## 功能

将用户提供的数据转化为图表，自动推荐最佳图表类型并插入当前幻灯片。

## 支持的数据格式

- CSV / TSV 文本
- JSON 数组
- 简单表格（Markdown 表格）

## 支持的图表类型

- 柱状图（Bar Chart）
- 折线图（Line Chart）
- 饼图（Pie Chart）
- 散点图（Scatter Plot）

## 工作流程

1. 解析用户提供的数据
2. 分析数据特征（维度数、数值范围、类别数量）
3. 推荐图表类型（可由用户覆盖）
4. 生成图表配置
5. 将图表组件插入当前选中的幻灯片

## Scripts

- `scripts/gen_chart.py` — 数据解析 + 图表配置生成

# Layout Notes 决策记录

## 摘要
本记录用于承接 `#68`，把 template notes 从零散的 layout 级说明文案升级为可直接指导后续实现的聚合合同。

在 `#67`、`#62` 与 `#71` 之后，Zhiyan 已经分别收口了：

- `group`：页面功能定位
- `sub-group`：信息结构细分
- `variant`：设计排版扩散

本记录继续回答最后一层问题：template notes 应该如何消费这些上游语义，并以统一的固定槽位输出给 catalog、registry、model-readable catalog 与后续 notes runtime。

本记录只定义 notes 的语义合同，不直接修改运行时代码。

## 为什么 notes 不能继续停留在 `layoutDescription`
当前系统里的 notes 入口仍主要停留在 layout 级 description：

- `/dev/layout-catalog` 的 Notes 列直接展示 `layoutDescription`
- 前端 registry 暴露 `description`
- 后端 `get_layout_catalog()` 也主要把 `description` 拼给模型

这种做法已经不够承接新的 taxonomy，原因有三点：

1. `layoutDescription` 只能描述“这页长什么样”，无法稳定表达 `group / sub-group / variant` 的边界
2. selector、人工审核和 notes 线路都会需要“适用 / 不适用”信号，而不是只有一句简介
3. 如果 notes 不先被定义成独立合同，后续 runtime 很容易在实现层各自发明字段

因此，template notes 应被视为 taxonomy 的聚合出口，而不是 description 的别名。

## notes 的上游输入
template notes 固定消费以下五类输入：

- `group`
  页面功能定位与边界
- `sub-group`
  页面在同组下采用的结构信号
- `variant`
  设计排版扩散，当前按 `composition / tone / style / density` 四字段对象理解
- `usage`
  已有 usage tag 与使用偏向
- `layoutDescription`
  当前 layout 自身已有的简短说明

其中：

- `group` 决定 notes 的 `purpose`
- `sub-group` 决定 notes 的 `structure_signal`
- `variant` 决定 notes 的 `design_signal`
- `usage` 决定 notes 的 `usage_bias`
- `layoutDescription` 只能作为补充，不得替代前四类上游输入

## 固定槽位合同
本轮固定 6 个 notes 槽位：

| 槽位 | 作用 |
|---|---|
| `purpose` | 描述该模板在 deck 里的页面职责，以及它不负责什么 |
| `structure_signal` | 描述为什么当前结构适合这个模板，重点解释 `sub-group` |
| `design_signal` | 解释 `composition / tone / style / density` 如何影响阅读与表达 |
| `use_when` | 列出优先选择该模板的场景 |
| `avoid_when` | 列出不应选择该模板的场景 |
| `usage_bias` | 说明该模板更偏哪些 usage 类型，以及这种偏向是强还是弱 |

### `purpose`
回答：

- 这页在整份 deck 里应该承担什么职责
- 它不应该被用来替代哪类页面

不回答：

- 具体排版细节
- 适用行业标签

### `structure_signal`
回答：

- 当前模板为什么匹配当前 `sub-group`
- 这类结构最适合承载什么类型的信息

不回答：

- 设计风格
- 具体 usage 倾向

### `design_signal`
回答：

- `composition / tone / style / density` 会如何影响阅读体验
- 这种设计倾向更适合怎样的表达方式

不回答：

- 结构层定义本身
- 页面职责本身

### `use_when`
回答：

- 什么时候应该优先选这个模板
- 选它的典型触发条件是什么

### `avoid_when`
回答：

- 什么时候不应选择这个模板
- 哪些内容特征会让它变成坏匹配

### `usage_bias`
回答：

- 该模板更偏向哪些 usage tag
- 这种偏向是强还是弱

## 槽位书写约束
- 每个槽位使用短句或短段，不写成长篇说明
- `use_when` 和 `avoid_when` 必须同时出现
- `design_signal` 必须直接消费 `variant` 四字段，不重复解释结构层
- `usage_bias` 只写倾向，不替代 usage tag 本身
- notes 不新增第 7 个或更多槽位
- notes 不替代 selector prompt，只提供可消费语义

## notes 不负责什么
以下内容明确不属于 notes：

- selector 逻辑本身
- metadata schema 设计
- registry / catalog / backend 的 runtime 字段落地
- 最终模板文案润色
- 结构层与设计层的命名决策本体

## 对后续 issue 的要求

### 对 `#75`
- `#75` 只能消费本记录定义的 6 槽位合同
- runtime 不得新增新的 notes 槽位
- 若 runtime 需要兼容旧 description，应视为过渡层，而不是合同扩展

### 对 catalog / registry / model-readable catalog
- catalog 可把 notes 作为结构化展示或摘要展示来源
- registry 应暴露 notes，而不是只暴露 description
- model-readable catalog 后续应优先消费结构化 notes，而不是拼接自由文本

## 状态
本记录构成 `#68` 的决策基线。
若后续要增加新的 notes 槽位或改变上游输入关系，应通过新的决策记录推进，而不是在运行时实现中静默修改。

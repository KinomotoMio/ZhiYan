# Layout Variant 决策记录

## 摘要
本记录承接 `#71` 与 `#98`，固定 Zhiyan 模板体系中的 `variant` 对象结构、字段职责和值域边界。

在 `group` 与 `sub-group` 已分别承担“页面功能定位”和“信息结构细分”职责后，
`variant` 只负责同一 `group + sub-group` 下的设计排版扩散。

本记录只回答 `variant` 在 taxonomy 主干中的角色、当前对象结构与现阶段值域基线，不直接修改运行时代码，也不替 `#102` 提前给出“这套模型已最终足够”的结论。

## 为什么 `variant` 仍然需要是对象
`variant` 不再承担结构差异，但仍需要对象化，原因不变：

1. 同一结构下的设计差异本身就是多维的  
   版式骨架、表达气质、视觉语言与信息密度不能稳定压成一个单值字符串。

2. 实现层需要可拆分消费的设计信号  
   metadata、catalog、notes 与 selector 都需要按维度读取设计层信息。

3. 兼容旧接口时更容易明确边界  
   旧的单值 `variant` 只能作为过渡视图，正式语义应继续由对象承载。

## `variant` 的正式对象形态
首批正式结构固定为四个字段：

```ts
type LayoutVariant = {
  composition: VariantComposition;
  tone: VariantTone;
  style: VariantStyle;
  density: VariantDensity;
};
```

这四个字段在首批范围内使用全局统一命名，不允许每个 `group / sub-group` 自行发明新的字段名。

## 四个字段分别负责什么

| 字段 | 回答的问题 | 不负责回答的问题 |
|---|---|---|
| `composition` | 这页采用哪种版式骨架或空间组织方式？ | 页面功能定位、信息结构分类 |
| `tone` | 这页整体给人的气质是什么？ | 信息结构与组件关系 |
| `style` | 这页主要依赖哪种视觉语言？ | 页面职责、内容组织方式 |
| `density` | 这页的信息承载强度有多高？ | 配色方案、具体文案内容 |

进一步约束如下：

- `composition` 可以影响模板选择与排序，但不能替代 `sub-group`
- 若某个历史 `composition` 名称主要承担结构分类职责，应优先把这层差异回收到 `sub-group`
- `tone` 用于区分表达气质，例如正式、强调、庆祝，不用于编码结构
- `style` 用于概括视觉语言，例如卡片化、图标化、数据优先
- `density` 用于表达单位画面内的信息承载强度，统一使用低/中/高三档

## 首批正式值域

### `composition`

| 值 | 含义 |
|---|---|
| `hero-center` | 居中主标题/主视觉的开场式骨架 |
| `card-grid` | 多卡片网格骨架 |
| `section-break` | 大标题主导的章节切换骨架 |
| `icon-columns` | 图标驱动的多列要点骨架 |
| `media-split` | 视觉内容与说明内容左右分栏的骨架 |
| `capability-grid` | 多能力点并列展开的网格骨架 |
| `stat-grid` | 核心指标卡片并列展示的骨架 |
| `analysis-split` | 图表与分析要点并置的骨架 |
| `table-dominant` | 表格占主导的骨架 |
| `dual-columns` | 双栏并列对照的骨架 |
| `step-list` | 顺序步骤清单骨架 |
| `timeline-band` | 时间轴/里程碑带状骨架 |
| `quote-focus` | 单句引述或结论主导的骨架 |
| `closing-hero` | 收尾致谢型的中心主导骨架 |

### `tone`

| 值 | 含义 |
|---|---|
| `formal` | 正式、稳健、适合汇报和说明 |
| `neutral` | 中性、克制、偏方法说明 |
| `assertive` | 强调、推进、结论导向 |
| `approachable` | 亲和、易讲解、偏案例展示 |
| `celebratory` | 收尾、致谢、结束感明确 |

### `style`

| 值 | 含义 |
|---|---|
| `minimal` | 以简洁留白和基础层级为主 |
| `card-based` | 以卡片容器组织信息 |
| `editorial` | 以封面感、图文编排感为主 |
| `icon-led` | 以图标作为主要视觉引导 |
| `data-first` | 以数据/图表/表格为主要视觉主体 |
| `statement` | 以单句观点或引用作为主视觉焦点 |

### `density`

| 值 | 含义 |
|---|---|
| `low` | 单页元素少，强调留白与焦点 |
| `medium` | 单页元素适中，兼顾阅读与呈现 |
| `high` | 单页承载信息更密集，强调覆盖面 |

## 哪些差异进入 `variant`
以下差异进入 `variant`：

- 同一 `group + sub-group` 下的设计骨架细化
- 同一结构下的表达气质差异
- 同一结构下的视觉语言差异
- 同一结构下的信息承载强度差异

以下差异不进入 `variant`：

- 页面功能定位不同
- 信息结构类型不同
- 足以改变模板匹配结果的结构差异
- 一次性文案倾向或业务语气
- 仅存在于 notes 中的使用建议

## `#98` 之后的边界澄清
第二轮 taxonomy 校准后，以下结构差异不再视为 `variant` 主体：

- `evidence`
  - `stat-summary`
  - `visual-evidence`
  - `chart-analysis`
  - `table-matrix`
- `comparison`
  - `side-by-side`
  - `response-mapping`
- `process`
  - `step-flow`
  - `timeline-milestone`

它们已经正式进入 `sub-group`，`variant` 只保留这些结构之内的设计扩散。

## 按 `group / sub-group` 的示例

| `group / sub-group` | 推荐的首批 `variant` 示例 | 说明 |
|---|---|---|
| `cover / default` | `{ composition: hero-center, tone: formal, style: editorial, density: low }` | 封面页优先由开场感和整体气质驱动。 |
| `agenda / default` | `{ composition: card-grid, tone: formal, style: card-based, density: medium }` | 目录页的核心差异主要体现在网格卡片编排。 |
| `section-divider / default` | `{ composition: section-break, tone: assertive, style: minimal, density: low }` | 章节过渡页应强化切换感，而不是增加信息密度。 |
| `narrative / icon-points` | `{ composition: icon-columns, tone: assertive, style: icon-led, density: medium }` | 图标分点结构下的设计层表达。 |
| `narrative / visual-explainer` | `{ composition: media-split, tone: approachable, style: editorial, density: medium }` | 图文说明结构下的设计层表达。 |
| `narrative / capability-grid` | `{ composition: capability-grid, tone: assertive, style: icon-led, density: high }` | 能力网格结构下的设计层表达。 |
| `evidence / stat-summary` | `{ composition: stat-grid, tone: formal, style: data-first, density: medium }` | 指标概览结构下的设计层表达。 |
| `evidence / visual-evidence` | `{ composition: media-split, tone: assertive, style: data-first, density: medium }` | 图像佐证结构下的设计层表达。 |
| `evidence / chart-analysis` | `{ composition: analysis-split, tone: formal, style: data-first, density: high }` | 图表解读结构下的设计层表达。 |
| `evidence / table-matrix` | `{ composition: table-dominant, tone: formal, style: data-first, density: high }` | 表格矩阵结构下的设计层表达。 |
| `comparison / side-by-side` | `{ composition: dual-columns, tone: formal, style: card-based, density: medium }` | 并列对照结构下的设计层表达。 |
| `comparison / response-mapping` | `{ composition: dual-columns, tone: assertive, style: minimal, density: medium }` | 响应映射结构下的设计层表达。 |
| `process / step-flow` | `{ composition: step-list, tone: neutral, style: minimal, density: medium }` | 步骤流程结构下的设计层表达。 |
| `process / timeline-milestone` | `{ composition: timeline-band, tone: formal, style: minimal, density: medium }` | 时间里程碑结构下的设计层表达。 |
| `highlight / default` | `{ composition: quote-focus, tone: assertive, style: statement, density: low }` | 强调页以结论或引用作为单点焦点。 |
| `closing / default` | `{ composition: closing-hero, tone: celebratory, style: minimal, density: low }` | 结尾页强调收束感和结束感。 |

以上示例用于说明当前 built-in template 的设计层基线，不应被理解为同一 `group + sub-group` 下唯一允许存在的正式 `variant`。

## 当前 16 个 built-in template 的 `variant` 基线归属

| `layoutId` | `group` | `sub-group` | `variant` |
|---|---|---|---|
| `intro-slide` | `cover` | `default` | `{ composition: hero-center, tone: formal, style: editorial, density: low }` |
| `outline-slide` | `agenda` | `default` | `{ composition: card-grid, tone: formal, style: card-based, density: medium }` |
| `section-header` | `section-divider` | `default` | `{ composition: section-break, tone: assertive, style: minimal, density: low }` |
| `bullet-with-icons` | `narrative` | `icon-points` | `{ composition: icon-columns, tone: assertive, style: icon-led, density: medium }` |
| `image-and-description` | `narrative` | `visual-explainer` | `{ composition: media-split, tone: approachable, style: editorial, density: medium }` |
| `bullet-icons-only` | `narrative` | `capability-grid` | `{ composition: capability-grid, tone: assertive, style: icon-led, density: high }` |
| `metrics-slide` | `evidence` | `stat-summary` | `{ composition: stat-grid, tone: formal, style: data-first, density: medium }` |
| `metrics-with-image` | `evidence` | `visual-evidence` | `{ composition: media-split, tone: assertive, style: data-first, density: medium }` |
| `chart-with-bullets` | `evidence` | `chart-analysis` | `{ composition: analysis-split, tone: formal, style: data-first, density: high }` |
| `table-info` | `evidence` | `table-matrix` | `{ composition: table-dominant, tone: formal, style: data-first, density: high }` |
| `two-column-compare` | `comparison` | `side-by-side` | `{ composition: dual-columns, tone: formal, style: card-based, density: medium }` |
| `challenge-outcome` | `comparison` | `response-mapping` | `{ composition: dual-columns, tone: assertive, style: minimal, density: medium }` |
| `numbered-bullets` | `process` | `step-flow` | `{ composition: step-list, tone: neutral, style: minimal, density: medium }` |
| `timeline` | `process` | `timeline-milestone` | `{ composition: timeline-band, tone: formal, style: minimal, density: medium }` |
| `quote-slide` | `highlight` | `default` | `{ composition: quote-focus, tone: assertive, style: statement, density: low }` |
| `thank-you` | `closing` | `default` | `{ composition: closing-hero, tone: celebratory, style: minimal, density: low }` |

这些归属用于表达“当前 built-in template 分别落在哪个设计层基线”，
不等于宣称同一 `group + sub-group` 在后续扩模板时只能存在这一种 `variant`。

## 本记录不做什么
- 不修改 `variant` 的对象字段名
- 不为未来模板预先扩展新的值域
- 不修改 selector、catalog 或 registry 的具体实现
- 不重新引入单值 `variant` 作为正式 taxonomy

## 状态
本记录是 `#98` 之后的最新 `variant` 边界基线。
后续若要扩展新的 `variant` 值域，应通过新的决策更新，而不是在实现 PR 中静默新增。
`composition / tone / style / density` 是否足以长期支撑同一 `group + sub-group` 下的多设计风格扩展，继续由 `#102` 评估。

# Layout Variant 决策记录

## 摘要
本记录用于承接 `#71`，把 Zhiyan 模板体系中的 `variant` 从旧的单值标签升级为可直接指导后续实现的对象结构。

在 `#67` 与 `#62` 之后，`group` 与 `sub-group` 已经分别承担“页面功能定位”和“信息结构细分”职责。
本记录继续完成第三层收口：在 `group + sub-group` 已确定后，如何用统一的对象字段表达设计排版扩散。

本记录只回答 `variant` 的规则、字段和值域，不直接修改运行时代码。

## 为什么 `variant` 不能继续停留在单值字符串
旧的单值 `variant` 已经不足以表达当前模板体系中的设计差异，原因有三点：

1. 单值字符串很容易再次混入结构层语义  
   narrative 试点已经证明，像 `icon-points / visual-explainer / capability-grid` 这类名字更接近 `sub-group`，而不是设计扩散。

2. 单值字符串难以稳定承载多个设计维度  
   同一个 `group + sub-group` 下的模板差异，往往同时涉及版式骨架、整体气质、视觉风格和信息密度。继续压成一个名字，会让命名越来越混杂。

3. 后续实现需要可拆分消费的设计信号  
   metadata、catalog、notes 与 selector 后续都需要读取设计层信息。对象结构比单值字符串更适合作为统一上游。

因此，本记录将 `variant` 明确为对象，而不是继续沿用单值枚举。

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
| `composition` | 这页采用哪种版式骨架？ | 页面功能定位、信息结构分类 |
| `tone` | 这页整体给人的气质是什么？ | 信息层级、组件摆放结构 |
| `style` | 这页主要依赖哪种视觉语言？ | 页面职责、内容组织方式 |
| `density` | 这页的信息承载强度有多高？ | 配色方案、具体文案内容 |

进一步约束如下：

- `composition` 可以影响模板选择与排序，但不能替代 `sub-group`
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

- 同一 `group + sub-group` 下，版式骨架不同
- 同一结构下，表达气质明显不同
- 同一结构下，视觉语言存在稳定差异
- 同一结构下，信息承载强度存在稳定差异

以下差异不进入 `variant`：

- 页面功能定位不同
- 信息结构类型不同
- 一次性文案倾向或业务语气
- 仅存在于 notes 中的使用建议
- 不足以复用命名的细碎视觉差异

## 首批按 `group / sub-group` 的示例

| `group / sub-group` | 推荐的首批 `variant` 示例 | 说明 |
|---|---|---|
| `cover / default` | `{ composition: hero-center, tone: formal, style: editorial, density: low }` | 封面页优先由开场感和整体气质驱动。 |
| `agenda / default` | `{ composition: card-grid, tone: formal, style: card-based, density: medium }` | 目录页的核心差异主要体现在网格卡片编排。 |
| `section-divider / default` | `{ composition: section-break, tone: assertive, style: minimal, density: low }` | 章节过渡页应强化切换感，而不是增加信息密度。 |
| `narrative / icon-points` | `{ composition: icon-columns, tone: assertive, style: icon-led, density: medium }` | 结构层已固定为图标分点，设计层再表达图标驱动的排版气质。 |
| `narrative / visual-explainer` | `{ composition: media-split, tone: approachable, style: editorial, density: medium }` | 图文说明结构的主要设计差异来自图文分栏与讲解气质。 |
| `narrative / capability-grid` | `{ composition: capability-grid, tone: assertive, style: icon-led, density: high }` | 能力网格结构适合更高承载度和更强图标化风格。 |
| `evidence / default` | `{ composition: stat-grid, tone: formal, style: data-first, density: medium }` | 证据页的首批变体重点在数据承载方式。 |
| `comparison / default` | `{ composition: dual-columns, tone: formal, style: card-based, density: medium }` | 对比页优先用双栏并列骨架表达取舍关系。 |
| `process / default` | `{ composition: step-list, tone: neutral, style: minimal, density: medium }` | 流程页优先保持步骤可读性和结构清晰。 |
| `highlight / default` | `{ composition: quote-focus, tone: assertive, style: statement, density: low }` | 强调页以结论或引用作为单点焦点。 |
| `closing / default` | `{ composition: closing-hero, tone: celebratory, style: minimal, density: low }` | 结尾页强调收束感和结束感。 |

## 当前 16 个 built-in template 的正式 `variant` 归属

| `layoutId` | `group` | `sub-group` | `variant` |
|---|---|---|---|
| `intro-slide` | `cover` | `default` | `{ composition: hero-center, tone: formal, style: editorial, density: low }` |
| `outline-slide` | `agenda` | `default` | `{ composition: card-grid, tone: formal, style: card-based, density: medium }` |
| `section-header` | `section-divider` | `default` | `{ composition: section-break, tone: assertive, style: minimal, density: low }` |
| `bullet-with-icons` | `narrative` | `icon-points` | `{ composition: icon-columns, tone: assertive, style: icon-led, density: medium }` |
| `image-and-description` | `narrative` | `visual-explainer` | `{ composition: media-split, tone: approachable, style: editorial, density: medium }` |
| `bullet-icons-only` | `narrative` | `capability-grid` | `{ composition: capability-grid, tone: assertive, style: icon-led, density: high }` |
| `metrics-slide` | `evidence` | `default` | `{ composition: stat-grid, tone: formal, style: data-first, density: medium }` |
| `metrics-with-image` | `evidence` | `default` | `{ composition: media-split, tone: assertive, style: data-first, density: medium }` |
| `chart-with-bullets` | `evidence` | `default` | `{ composition: analysis-split, tone: formal, style: data-first, density: high }` |
| `table-info` | `evidence` | `default` | `{ composition: table-dominant, tone: formal, style: data-first, density: high }` |
| `two-column-compare` | `comparison` | `default` | `{ composition: dual-columns, tone: formal, style: card-based, density: medium }` |
| `challenge-outcome` | `comparison` | `default` | `{ composition: dual-columns, tone: assertive, style: minimal, density: medium }` |
| `numbered-bullets` | `process` | `default` | `{ composition: step-list, tone: neutral, style: minimal, density: medium }` |
| `timeline` | `process` | `default` | `{ composition: timeline-band, tone: formal, style: minimal, density: medium }` |
| `quote-slide` | `highlight` | `default` | `{ composition: quote-focus, tone: assertive, style: statement, density: low }` |
| `thank-you` | `closing` | `default` | `{ composition: closing-hero, tone: celebratory, style: minimal, density: low }` |

## 对后续实现 issue 的要求

### 对 `#72` / `#73`
- 共享 metadata、前后端 registry 和 helper 层后续应以对象形式消费 `variant`
- 若运行时需要过渡层，可在实现 issue 中添加兼容映射，但不得重新定义字段名和值域

### 对 `#74`
- `/dev/layout-catalog` 后续应展示四个字段，而不是继续把 `variant` 当单值文本展示

### 对 `#75`
- notes 应消费 `variant` 对象中的四个维度，分别承接适用场景与排除条件

### 对 `#76`
- selector 不应再直接围绕单值 `variant` 做硬匹配，而应把四个字段作为排序与筛选输入

## 本记录不做什么
- 不修改 `shared/layout-metadata.json`
- 不修改前后端 registry
- 不修改 catalog 运行时展示
- 不修改 selector
- 不修改 notes runtime

## 状态
本记录构成 `#71` 的决策基线。
后续如果要扩展新的 `variant` 值域，应通过新的决策更新，而不是在实现 PR 中静默新增。

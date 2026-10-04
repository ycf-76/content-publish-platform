---
node_type: produce
name: comparison_card
category: create
priority: hot
display_name: 对比图/一图流
description: >-
  对比图/一图流：生成A vs B参数对比图、优劣势对比表、产品参数一图流。
  用HTML+CSS渲染成可截图的视觉卡片，适合小红书/微博等平台分享。
  当用户说"做个对比图"、"A vs B"、"参数对比"、"优劣对比"、"一图流"、"哪个好"时使用。
  和chart-visualization的区别：chart做数据图表（柱状图/折线图），comparison-card做对比表/一图流。
trigger_words: ["对比图", "vs", "参数对比", "优劣对比", "一图流", "对比表", "哪个好", "对比一下", "comparison", "compare", "做图文", "图文"]
references:
  - references/palettes.md
  - references/card-recipes.md
  - references/layout-laws.md
  - references/anti-ai-slop.md
prompt_guidance: 解析对比需求→收集整理数据→选布局(table/versus/pros_cons)→生成HTML卡片→视觉优化。输出HTML供前端渲染，不做playwright截图。
---

# 对比图 / 一图流

你是视觉对比设计师。生成A vs B可视化对比卡片，一张截图说清楚差异，适合社媒分享。

> 生成前先读card-design设计系统（锁配色/字体层级/填满画幅/去AI廉价感）。对比图用「对比表」骨架（左右双栏、≥5对比行、行高一致），避免渐变、emoji、底部死空白。

## 输入

| 字段 | 必填 | 说明 |
|------|------|------|
| `items` | 是 | 要对比的2-4个对象（名称） |
| `dimensions` | 否 | 对比维度列表（如价格、性能、功能等）；不指定则自动推断 |
| `data` | 否 | 结构化对比数据（JSON/表格）；不提供则由SKILL调研填充 |
| `layout` | 否 | 布局模式：`table`（默认）/ `versus` / `pros_cons` |
| `size` | 否 | 尺寸预设：`xiaohongshu`(1080x1440) / `weibo`(1080x1080) / `wechat`(1080x1920) / `auto` |
| `style` | 否 | 视觉风格：走card-design风格库（瑞士极简/杂志编辑/高奢黑金…），不指定则按内容品类选一个立场 |
| `winner` | 否 | 是否标注胜出项：`true` / `false`（默认`false`） |

### 布局模式说明

| 模式 | 描述 | 适用场景 |
|------|------|----------|
| `table` | 经典参数对比表，行=维度，列=对象 | 多维度、多参数的产品对比 |
| `versus` | 左右对称VS布局，中间分割线 | 两个对象的直观对比 |
| `pros_cons` | 优劣势分栏，绿色优势/红色劣势 | 单一产品的优劣分析 |

## 执行步骤

### Step 1 — 解析对比需求

1. 确认对比对象（2-4个）
2. 确认对比维度：
   - 用户指定了 → 直接用
   - 用户没指定 → 根据对象类型自动推断常见对比维度（如手机：价格/屏幕/芯片/电池/摄像头）
3. 确认布局模式和尺寸

### Step 2 — 数据收集与整理

如果用户提供了完整数据：
- 直接结构化为对比矩阵

如果用户只给了对象名，没给数据：
- 用WebSearch查询各对象的关键参数
- 交叉验证数据准确性（至少2个来源）
- 标注数据来源

将数据整理为标准矩阵：
```json
{
  "items": ["A", "B"],
  "dimensions": [
    {"name": "价格", "values": ["¥2999", "¥3499"], "winner": "A"},
    {"name": "性能", "values": ["骁龙 8 Gen3", "A17 Pro"], "winner": "B"}
  ]
}
```

### Step 3 — 生成 HTML 卡片

1. 根据`layout`模式选择布局结构
2. 填充数据到模板
3. **应用card-design选定风格的配色/字体**（锁spec，全表一致；不自造配色）
4. 设置卡片尺寸（`size`参数）
5. 如果`winner`为true，用视觉标记（高亮/皇冠图标）标注胜出项

### Step 4 — 视觉优化

- 确保文字不溢出单元格
- 数值类数据右对齐，文本类左对齐
- 胜出项用card-design选定风格的**强调色**高亮，劣势项用中性灰（不写死某个绿）
- 底部加数据来源说明和日期
- 遵守card-design铁律：禁蓝紫科技渐变、禁emoji当图标、填满不留死空白

### Step 5 — 输出（严格遵守）

**必须**用 `<!--card-html-->` 和 `<!--/card-html-->` 标记包裹HTML。
前端通过这两个标记识别卡片内容并渲染为iframe预览。**不用markdown代码块**，直接输出HTML。

<!--card-html-->
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  /* 对比图样式 */
  * { margin: 0; padding: 0; box-sizing: border-box; }
  /* ... 你的样式 ... */
</style>
</head>
<body>
<!-- 对比图内容 -->
</body>
</html>
<!--/card-html-->

**关键规则**：
- **必须**用 `<!--card-html-->...<!--/card-html-->` 包裹
- HTML**必须**是完整文档（含 `<!DOCTYPE html>`、`<html>`、`<head>`、`<body>`）
- **禁止**用 ```html 代码块包裹

## 设计要点

渲染方案：
- **前端渲染**：HTML代码输出到对话，前端WorkPreview组件可直接渲染
- **保留核心**：3种布局模式 + 标准数据矩阵 + winner标注 + card-design风格系统 + 视觉优化规则

## Profile 感知

- **有Profile**：从style.md读取品牌配色，替换模板默认色；从identity.md读取账号名作为水印；从platforms.md读取主力平台，自动匹配尺寸
- **无Profile**：使用默认清新风格配色，无水印，默认小红书尺寸（1080x1440）
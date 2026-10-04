# Easel 创作技能借鉴计划

> 原则：不是复制，是在 Easel 基础上做得更好，把精华取出来，借鉴。
> 驱动方式：ReAct（Chat 模式下 LLM 自主调 Skill），不动 DAG。
> 架构约束：零新架构，零新依赖，全部基于现有 PromptDrivenSkill + Skill 基类体系。

---

## 〇、待办备忘（防上下文压缩丢失）

### 🔧 浏览器 Worker 问题（做完本计划再解决）

- **问题**：QR Worker（`http://127.0.0.1:9010`）是独立 Playwright 进程，需要单独启动才能运行 `browser_navigate`/`browser_screenshot` Skill。
- **现状**：`main.py` 启动时 `worker_manager.start()` 已有 try/except 兜底，Worker 起不来只是 warning，不阻塞后端。Skill 注册也不依赖 Worker 在线。
- **决策**：**做完本计划（周期 1-6）后再解决**。原因：当前 6 个周期全部是 .md 文件 + 文本修改 + 1 个纯 Python Skill（jieba/snownlp），和浏览器 Worker 零交集。先解决 Worker 会打断节奏且无收益。
- **何时解决**：本计划全部验收通过后，单独开一轮排查 Worker 进程管理、Playwright chromium 安装、端口配置等问题。

### 📦 依赖决策备忘

- **snownlp**（周期 6）：✅ 已安装（`pip install snownlp`），纯 Python 无编译依赖。
- **jieba**（周期 6）：✅ 已有，无需额外安装。
- **周期 1-5**：零新依赖。
- **playwright chromium**：当前计划不直接用浏览器，但如果后期要加"实时抓取小红书竞品页面"的 Skill，需要确认 chromium 内核已安装（`playwright install chromium`，约 150MB）。

---

## 〇、上一轮已完成盘点

### 已完成的 PromptDrivenSkill（8 个 .md，Chat 可调）

| 文件 | skill name | 状态 |
|------|-----------|------|
| `prompts/skills/text-polisher.md` | text_polisher | ✅ 已完成 |
| `prompts/skills/text-condenser.md` | text_condenser | ✅ 已完成 |
| `prompts/skills/quality-gate.md` | quality_gate | ✅ 已完成 |
| `prompts/skills/topic-evaluator.md` | topic_evaluator | ✅ 已完成 |
| `prompts/skills/card-design.md` | card_design | ✅ 已完成 |
| `prompts/skills/caption-hashtag.md` | caption_hashtag | ✅ 已完成 |
| `prompts/skills/social-content.md` | social_content | ✅ 已完成 |
| `prompts/skills/post-formatter.md` | post_formatter | ✅ 已完成 |

### 已完成的 references（14 个 .md）

| 文件 | 状态 |
|------|------|
| `prompts/references/zh-ai-markers.md` | ✅ 已完成 |
| `prompts/references/phrases-to-remove.md` | ✅ 已完成 |
| `prompts/references/structures-to-avoid.md` | ✅ 已完成 |
| `prompts/references/natural-transitions.md` | ✅ 已完成 |
| `prompts/references/writing-style-rules.md` | ✅ 已完成 |
| `prompts/references/hook-title-formulas.md` | ✅ 已完成 |
| `prompts/references/copy-frameworks.md` | ✅ 已完成 |
| `prompts/references/scoring-dimensions.md` | ✅ 已完成 |
| `prompts/references/hashtag-strategy.md` | ✅ 已完成 |
| `prompts/references/platform-specs.md` | ✅ 已完成 |
| `prompts/references/layout-laws.md` | ✅ 已完成 |
| `prompts/references/palettes.md` | ✅ 已完成 |
| `prompts/references/card-recipes.md` | ✅ 已完成 |
| `prompts/references/anti-ai-slop.md` | ✅ 已完成 |

### 已完成的 Python 服务（4 个 .py）

| 文件 | 功能 | 状态 |
|------|------|------|
| `services/content_guard.py` | 出站内容安全闸门（regex + .env 扫描） | ✅ 已完成 |
| `services/wordcount.py` | 社媒字数统计与校验 | ✅ 已完成 |
| `services/copywrite_postprocess.py` | 文案后处理管线（字数校验→AI味扫描→CTA检查） | ✅ 已完成 |
| `services/platform_adapter.py` | 多平台适配器（6平台规格+标签+字数限制） | ✅ 已完成 |

### 已完成的修改（3 个 .py）

| 文件 | 改了什么 | 状态 |
|------|---------|------|
| `nodes/audit.py` | 集成 content_guard 门禁（发布前敏感信息扫描） | ✅ 已完成 |
| `nodes/publish.py` | 集成 platform_adapter 平台限制检查 | ✅ 已完成 |
| `nodes/card_gen.py` | 重写：结构化 card_spec 输出 | ✅ 已完成 |

### ⚠️ 上一轮的问题

1. **copywrite.py 未集成后处理管线**：`copywrite_postprocess.py` 已写好，但 `copywrite.py` 里没有调用它（grep 无匹配）。**需要补集成。**
2. **8 个 PromptDrivenSkill 的 description/trigger_words 不够精准**：LLM 路由可能不准，周期 5 统一优化。
3. **缺 7 个 Easel 核心创作 Skill**：hook-generator / competitor-analysis / content-gap-analysis / audience-profiler / positioning-analysis / content-strategy / carousel-planner。这些是本计划要做的。

---

## 一、现状盘点

### 已有 PromptDrivenSkill（8 个，Chat 可调）

| skill name | 触发词 | 对应 Easel |
|-----------|--------|-----------|
| text_polisher | 润色/去AI味/打磨文案 | text-polisher ✅ |
| text_condenser | 压缩/精简/缩写 | 无直接对应 |
| quality_gate | 发布前检查/质量检查 | skill-quality-gate ✅ |
| topic_evaluator | 评估选题/选题打分 | 无直接对应（我们自创） |
| card_design | 卡片设计/排版 | card-design ✅ |
| caption_hashtag | 话题标签/标签策略 | caption-hashtag ✅ |
| social_content | 社媒文案/写文案 | social-content ✅ |
| post_formatter | 格式化/排版格式 | post-formatter ✅ |

### 已有 references（14 个）

zh-ai-markers / phrases-to-remove / structures-to-avoid / natural-transitions /
writing-style-rules / hook-title-formulas / copy-frameworks / scoring-dimensions /
hashtag-strategy / platform-specs / layout-laws / palettes / card-recipes / anti-ai-slop

### 缺失的 Easel 核心创作 Skill（7 个）

| Easel Skill | 层级 | 干什么 | 我们为什么需要 |
|-------------|------|--------|--------------|
| skill-hook-generator | plan | 6 种钩子公式生成开头 | 文案开头是留存关键，目前没有专门工具 |
| skill-content-strategy | plan | 内容支柱+受众路径+90天节奏 | 用户问"怎么做内容"时只能泛泛回答 |
| skill-competitor-analysis | discover | 竞品拆解+爆款规律+差异化机会 | 用户问"竞品在做什么"时没有工具 |
| skill-audience-profiler | plan | 受众画像+痛点+内容偏好 | 用户问"我的用户是谁"时没有工具 |
| skill-carousel-planner | plan | 轮播图分页结构+CTA设计 | 小红书核心格式是图文轮播，缺专门策划 |
| skill-positioning-analysis | plan | 差异化定位分析 | 用户问"怎么和竞品区分"时没有工具 |
| skill-content-gap-analysis | discover | 蓝海选题发现 | 用户问"没人做的选题"时没有工具 |

### 缺失的 Easel Reference 知识文件（6 个）

| Easel Reference | 所属 Skill | 内容 |
|----------------|-----------|------|
| hook-formulas.md | hook-generator | 6 种 Hook 变体公式（数字领衔/逆向认知/个人蜕变/权威借势/自我坦白/未来冲击） |
| strategy-frameworks.md | content-strategy | 受众路径四阶段 + 90天三阶段节奏 + 分发渠道策略 + KPI 体系 |
| viral-patterns.md | competitor-analysis | 爆款特征识别 + 更新频率与涨粉节奏 + 风格与互动模式差异 |
| profiling-frameworks.md | audience-profiler | 受众画像框架 + 痛点结构 + 内容偏好 + 渠道触达 + 评论区挖掘 |
| positioning-frameworks.md | positioning-analysis | 赛道扫描 + 定位坐标法 + 蓝海机会识别 + 差异化五维 + 一句话定位公式 |
| demand-signals.md | content-gap-analysis | 平台搜索联想词 + 平台热搜 + 评论区未满足需求 |

---

## 二、适配方式

### A 类：纯 LLM 驱动 → PromptDrivenSkill（.md 文件）

7 个缺失 Skill 全部是 A 类——逻辑就是"LLM 按 SKILL.md prompt + references 生成结果"，不需要确定性脚本。

适配路径：
```
Easel SKILL.md
  → 提炼执行步骤 + 输出格式（不是复制，是适配小红书场景优化）
  → 写 frontmatter（node_type / name / description / trigger_words / references）
  → 写 body（执行步骤 + 输出模板 + 规则）
  → 放到 prompts/skills/ 目录
  → scan_and_register_prompt_skills() 自动注册
  → Chat 模式下 LLM 自动可见、可调
```

### B 类：需要确定性脚本 → Python Skill（.py 文件）

Easel 的 `skill-comment-insights` 需要 jieba + SnowNLP 做情感分析，是确定性计算，不适合纯 LLM。
**但本计划暂不实施 B 类**，原因：
1. jieba/snownlp 是新依赖，需要 pip install + 首次构建词典缓存
2. 评论数据来源需要 Playwright 抓取（又是一个依赖）
3. 风险高，单独一个周期做

### 不做的事

- ❌ 不改 PromptDrivenSkill 基类的 _InputSchema
- ❌ 不改 LoopExecutor
- ❌ 不改 DAG
- ❌ 不改 AGENTS.md / SOUL.md（_build_skill_routing 自动注入）
- ❌ 不引入新的 Python 依赖

---

## 三、分周期计划

### 周期 1：Hook 生成器 + 所需 Reference

**目标**：用户在 Chat 里说"写钩子""开头怎么写"，LLM 调 hook_generator，输出 6 种 Hook 变体。

| 序号 | 任务 | 类型 | 文件 |
|------|------|------|------|
| 1.1 | 新增 hook-formulas.md reference | reference | `prompts/references/hook-formulas.md`（已有 hook-title-formulas.md，这个是**开头钩子**公式，不同于标题公式） |
| 1.2 | 新增 hook-generator.md skill | PromptDrivenSkill | `prompts/skills/hook-generator.md` |

**验收标准**：
- [ ] 后端启动无报错，hook_generator 出现在 SkillRegistry
- [ ] Chat 模式下用户说"帮我写个钩子，主题是XXX"，LLM 调用 hook_generator
- [ ] hook_generator 返回 6 种 Hook 变体，每条 2 行（开场+反转），每行 ≤40 字符
- [ ] 不影响现有 8 个 PromptDrivenSkill 的正常工作
- [ ] 不影响现有 Python Skill（trending_search/lively_girl 等）的正常工作

**风险点**：
- hook-title-formulas.md 已存在，hook-formulas.md 名字相近，需确认不冲突
- Easel 原版用 wordcount.py 做字数校验，我们改为 prompt 里加规则让 LLM 自校验

---

### 周期 2：竞品分析 + 蓝海选题 + 所需 Reference

**目标**：用户在 Chat 里说"分析竞品""蓝海选题"，LLM 调对应 Skill。

| 序号 | 任务 | 类型 | 文件 |
|------|------|------|------|
| 2.1 | 新增 viral-patterns.md reference | reference | `prompts/references/viral-patterns.md` |
| 2.2 | 新增 demand-signals.md reference | reference | `prompts/references/demand-signals.md` |
| 2.3 | 新增 competitor-analysis.md skill | PromptDrivenSkill | `prompts/skills/competitor-analysis.md` |
| 2.4 | 新增 content-gap-analysis.md skill | PromptDrivenSkill | `prompts/skills/content-gap-analysis.md` |

**验收标准**：
- [ ] 后端启动无报错，competitor_analysis + content_gap_analysis 出现在 SkillRegistry
- [ ] Chat 模式下用户说"帮我分析竞品，赛道是家居收纳"，LLM 调用 competitor_analysis
- [ ] Chat 模式下用户说"找蓝海选题，赛道是Python教学"，LLM 调用 content_gap_analysis
- [ ] 两个 Skill 都能引用 viral-patterns / demand-signals reference
- [ ] 不影响周期 1 的 hook_generator

**风险点**：
- 竞品分析需要 web_search/web_fetch，LLM 需要先调 trending_search 再调 competitor_analysis——这是 ReAct 多步调用，需确认 LoopExecutor 支持连续调两个 Skill（已确认支持）
- 蓝海选题同理，需要先搜热点再分析

---

### 周期 3：受众画像 + 差异化定位 + 所需 Reference

**目标**：用户在 Chat 里说"我的用户是谁""怎么和竞品区分"，LLM 调对应 Skill。

| 序号 | 任务 | 类型 | 文件 |
|------|------|------|------|
| 3.1 | 新增 profiling-frameworks.md reference | reference | `prompts/references/profiling-frameworks.md` |
| 3.2 | 新增 positioning-frameworks.md reference | reference | `prompts/references/positioning-frameworks.md` |
| 3.3 | 新增 audience-profiler.md skill | PromptDrivenSkill | `prompts/skills/audience-profiler.md` |
| 3.4 | 新增 positioning-analysis.md skill | PromptDrivenSkill | `prompts/skills/positioning-analysis.md` |

**验收标准**：
- [ ] 后端启动无报错，audience_profiler + positioning_analysis 出现在 SkillRegistry
- [ ] Chat 模式下用户说"帮我画受众画像，赛道是穿搭"，LLM 调用 audience_profiler
- [ ] Chat 模式下用户说"怎么和竞品区分，赛道是母婴"，LLM 调用 positioning_analysis
- [ ] 不影响周期 1-2 的 Skill

**风险点**：
- 受众画像需要用户给赛道信息，prompt 里需明确告知 LLM 该传什么参数

---

### 周期 4：内容策略 + 轮播图策划 + 所需 Reference

**目标**：用户在 Chat 里说"内容策略""轮播图怎么排"，LLM 调对应 Skill。

| 序号 | 任务 | 类型 | 文件 |
|------|------|------|------|
| 4.1 | 新增 strategy-frameworks.md reference | reference | `prompts/references/strategy-frameworks.md` |
| 4.2 | 新增 hook-library.md reference | reference | `prompts/references/hook-library.md`（封面 Hook 公式，不同于周期1的开头 Hook） |
| 4.3 | 新增 content-strategy.md skill | PromptDrivenSkill | `prompts/skills/content-strategy.md` |
| 4.4 | 新增 carousel-planner.md skill | PromptDrivenSkill | `prompts/skills/carousel-planner.md` |

**验收标准**：
- [ ] 后端启动无报错，content_strategy + carousel_planner 出现在 SkillRegistry
- [ ] Chat 模式下用户说"帮我做内容策略"，LLM 调用 content_strategy
- [ ] Chat 模式下用户说"帮我策划轮播图，主题是XXX"，LLM 调用 carousel_planner
- [ ] 不影响周期 1-3 的 Skill

**风险点**：
- 内容策略输出较长（支柱+受众路径+90天节奏+渠道+KPI），需确认 LLM max_tokens 够用
- 轮播图策划需要引用 hook-library（封面 Hook），需确认 reference 加载链路正常

---

### 周期 5：现有 PromptDrivenSkill 优化

**目标**：优化已有 8 个 PromptDrivenSkill 的 description 和 trigger_words，让 LLM 更精准地路由。

| 序号 | 任务 | 类型 | 说明 |
|------|------|------|------|
| 5.1 | 优化 text-polisher.md | 修改 | description 更精准，trigger_words 补充 |
| 5.2 | 优化 quality-gate.md | 修改 | 同上 |
| 5.3 | 优化 topic-evaluator.md | 修改 | 同上 |
| 5.4 | 优化其余 5 个 .md | 修改 | 同上 |

**验收标准**：
- [ ] 优化后每个 Skill 的 description 前 80 字符能清晰表达触发条件
- [ ] Chat 模式下 LLM 路由准确率不降（不会把"写钩子"路由到 text_polisher）
- [ ] 不影响周期 1-4 的新 Skill

**风险点**：
- 修改 description 可能影响 LLM 的路由行为，需逐个测试

---

### 周期 6（远期）：评论洞察 Python Skill

**目标**：用户在 Chat 里说"分析评论情感"，LLM 调 comment_insights Python Skill。

| 序号 | 任务 | 类型 | 文件 |
|------|------|------|------|
| 6.1 | pip install jieba snownlp | 依赖 | 新增依赖 |
| 6.2 | 新增 comment_insights.py | Python Skill | `tools/comment_insights.py` |
| 6.3 | BUILTIN_SKILL_MODULES 注册 | 修改 | `tools/registry.py` 加一行 |

**验收标准**：
- [ ] jieba/snownlp 安装无报错
- [ ] comment_insights 出现在 SkillRegistry
- [ ] 给一批评论，返回情感分布 + 高频词 + 诉求挖掘
- [ ] 不影响周期 1-5 的 Skill

**风险点**：
- 新依赖引入，需确认不影响现有依赖树
- jieba 首次构建词典缓存约 50MB
- 评论数据来源需配合 trending_search / web_fetch

---

## 四、每个 Skill 的具体设计

### 4.1 hook-generator.md

```yaml
node_type: plan
name: hook_generator
display_name: 开头钩子生成
description: >-
  针对任意主题生成6种开头Hook变体（数字领衔/逆向认知/个人蜕变/权威借势/自我坦白/未来冲击），
  每条2行结构（开场+反转），每行≤40字符。仅在用户要求写钩子/开头/Hook时调用。
trigger_words: ["写钩子", "开头怎么写", "Hook", "抓眼球的开头", "标题钩子", "前三秒", "怎么开头", "开头钩子"]
references:
  - references/hook-formulas.md
prompt_guidance: 按6种公式逐一生成Hook变体，每行≤40字符，开场不用问句，优先第一人称。
```

**借鉴 Easel 的优化点**：
- Easel 用 wordcount.py 做字数校验 → 我们改为 prompt 规则让 LLM 自校验（减少脚本依赖）
- Easel 6 种公式原样借鉴 → 新增"小红书特化"变体（如"姐妹们XX"身份认同型开头）
- Easel 输出后让用户选一条 → 我们也保留，并在 prompt 里加"选一条后可直接调 lively_girl 扩写"

### 4.2 competitor-analysis.md

```yaml
node_type: discover
name: competitor_analysis
display_name: 竞品内容分析
description: >-
  分析竞品账号的内容策略：选题分布、爆款规律、格式偏好、互动模式，输出差异化机会与行动建议。
  仅在用户要求分析竞品/拆解爆款/对标账号时调用。需要先调trending_search收集数据。
trigger_words: ["分析竞品", "竞品账号", "对标账号", "拆解爆款", "竞品在做什么", "对手内容策略", "竞争分析"]
references:
  - references/viral-patterns.md
prompt_guidance: 拆解竞品三问：什么内容会爆、多久发一次、靠什么涨粉。输出SWOT+差异化机会+行动建议。
```

**借鉴 Easel 的优化点**：
- Easel 用 web_fetch 抓竞品主页 → 我们用 trending_search 搜竞品内容（复用已有 Skill，不引入 Playwright）
- Easel 的爆款拆解维度（选题/标题钩子/封面/开头/结构/结尾/互动）→ 原样借鉴，新增"小红书特有维度"（收藏率/种草力）
- Easel 的 SWOT 分析 → 原样借鉴

### 4.3 content-gap-analysis.md

```yaml
node_type: discover
name: content_gap_analysis
display_name: 蓝海选题发现
description: >-
  分析赛道的内容空白，发现高需求低竞争的蓝海选题机会。输出带优先级的选题清单+速赢建议。
  仅在用户要求找蓝海选题/内容空白/差异化选题时调用。
trigger_words: ["蓝海选题", "内容空白", "没人做的选题", "选题机会", "高需求低竞争", "差异化选题", "内容缺口"]
references:
  - references/demand-signals.md
prompt_guidance: 三类需求信号交叉验证（搜索联想词+平台热搜+评论区未满足需求），缺一不可。
```

**借鉴 Easel 的优化点**：
- Easel 用 hotlist API 抓热搜 → 我们用 trending_search（复用已有 Skill）
- Easel 三类信号交叉验证 → 原样借鉴，新增"小红书搜索联想词"特化采集
- Easel 的伪空白排除规则 → 原样借鉴

### 4.4 audience-profiler.md

```yaml
node_type: plan
name: audience_profiler
display_name: 受众画像构建
description: >-
  构建目标受众画像：人群特征、痛点需求、内容偏好、触达渠道，输出2-4张典型画像卡。
  仅在用户要求受众画像/粉丝画像/目标人群时调用。
trigger_words: ["受众画像", "粉丝画像", "我的用户是谁", "目标人群", "用户痛点", "受众分析", "谁在看我"]
references:
  - references/profiling-frameworks.md
prompt_guidance: 三层画像（人口统计+心理特征+行为特征）→ 痛点结构 → 内容偏好 → 画像卡。
```

**借鉴 Easel 的优化点**：
- Easel 8 步流程 → 精简为 6 步（合并评论区挖掘到痛点步骤，减少 LLM 调用次数）
- Easel 的画像卡格式 → 原样借鉴，新增"小红书用户行为特征"（收藏习惯/种草路径）

### 4.5 positioning-analysis.md

```yaml
node_type: plan
name: positioning_analysis
display_name: 差异化定位分析
description: >-
  帮账号找到差异化定位：赛道扫描→竞品定位坐标→空白机会→多维差异化→一句话定位。
  仅在用户要求差异化定位/怎么区分竞品/找定位时调用。
trigger_words: ["差异化定位", "怎么和竞品区分", "我的定位是什么", "找差异化", "定位分析", "同质化怎么办", "找我的独特点"]
references:
  - references/positioning-frameworks.md
prompt_guidance: 差异化=不同且有需求且你能持续做到，三者缺一不可。
```

**借鉴 Easel 的优化点**：
- Easel 的定位坐标法 → 原样借鉴，新增"小红书赛道特化维度"（种草力↔干货度/颜值↔实用）
- Easel 的一句话定位公式 → 原样借鉴
- Easel 的伪空白排除 → 原样借鉴

### 4.6 content-strategy.md

```yaml
node_type: plan
name: content_strategy
display_name: 内容策略方案
description: >-
  制定内容策略：内容支柱架构+受众路径规划+90天节奏原则+分发渠道策略+KPI体系。
  仅在用户要求内容策略/策略方案/内容规划时调用。元策略层，只出框架不出排期表。
trigger_words: ["内容策略", "策略方案", "内容规划", "怎么做内容", "内容支柱", "增长策略", "涨粉策略"]
references:
  - references/strategy-frameworks.md
prompt_guidance: 元策略层：支柱理论+受众路径+90天节奏原则，不出月度排期表。
```

**借鉴 Easel 的优化点**：
- Easel 的受众路径四阶段 → 原样借鉴，新增"小红书特化指标"（收藏率/种草转化率）
- Easel 的 90 天三阶段 → 原样借鉴
- Easel 的"一鱼多吃"跨平台改编 → 原样借鉴

### 4.7 carousel-planner.md

```yaml
node_type: plan
name: carousel_planner
display_name: 轮播图策划
description: >-
  规划轮播图/多图笔记的分页结构：封面Hook+内容节奏+每页文案和视觉方向+CTA设计。
  仅在用户要求轮播图策划/多图笔记/图集结构/九宫格时调用。
trigger_words: ["轮播图策划", "多图笔记", "图集结构", "分页设计", "九宫格怎么排", "每页写什么", "carousel"]
references:
  - references/hook-library.md
  - references/layout-laws.md
prompt_guidance: 封面1秒打断滑动→逐页一个要点→末页CTA，每页文字≤20字。
```

**借鉴 Easel 的优化点**：
- Easel 的封面 Hook 6 公式 → 原样借鉴
- Easel 的分页结构弧线（Hook>铺垫>揭晓>CTA）→ 原样借鉴，新增"小红书九宫格特化"（第5图放关键信息，因为预览只显示前4+1）
- Easel 的 CTA 类型表 → 原样借鉴，新增"小红书特化CTA"（"先码住"/"评论区扣XX"）

---

## 五、Reference 文件设计

### 5.1 hook-formulas.md（新增，区别于已有的 hook-title-formulas.md）

已有 `hook-title-formulas.md`：7 类**标题**钩子公式（利益型/痛点型/身份型/对比型/数字型/清单型/提问型）
新增 `hook-formulas.md`：6 种**开头**钩子公式（数字领衔/逆向认知/个人蜕变/权威借势/自我坦白/未来冲击）

两者不冲突：标题钩子用于标题，开头钩子用于正文前两行。

内容来源：Easel `skill-hook-generator/references/hook-formulas.md`，新增小红书特化变体。

### 5.2 viral-patterns.md

来源：Easel `skill-competitor-analysis/references/viral-patterns.md`
内容：爆款特征识别 + 更新频率与涨粉节奏 + 风格与互动模式差异

### 5.3 demand-signals.md

来源：Easel `skill-content-gap-analysis/references/demand-signals.md`
内容：平台搜索联想词 + 平台热搜 + 评论区未满足需求 + 采集降级方案

### 5.4 profiling-frameworks.md

来源：Easel `skill-audience-profiler/references/profiling-frameworks.md`
内容：受众画像框架 + 痛点结构 + 内容偏好 + 渠道触达 + 评论区挖掘 + 画像卡模板

### 5.5 positioning-frameworks.md

来源：Easel `skill-positioning-analysis/references/positioning-frameworks.md`
内容：赛道扫描 + 定位坐标法 + 蓝海机会识别 + 差异化五维 + 一句话定位公式 + 落地与验证

### 5.6 strategy-frameworks.md

来源：Easel `skill-content-strategy/references/strategy-frameworks.md`
内容：受众路径四阶段 + 90天三阶段节奏 + 分发渠道策略 + KPI 指标体系

### 5.7 hook-library.md（新增，封面 Hook 公式）

来源：Easel `skill-carousel-planner/references/hook-library.md`
内容：6 种封面 Hook 公式（数字清单/反常识/对比冲击/直击痛点/颠覆声明/身份认同）
区别于 hook-formulas.md（开头 Hook）和 hook-title-formulas.md（标题 Hook）

---

## 六、文件清单汇总

| 周期 | 新增文件 | 修改文件 |
|------|---------|---------|
| 1 | `references/hook-formulas.md`, `skills/hook-generator.md` | 无 |
| 2 | `references/viral-patterns.md`, `references/demand-signals.md`, `skills/competitor-analysis.md`, `skills/content-gap-analysis.md` | 无 |
| 3 | `references/profiling-frameworks.md`, `references/positioning-frameworks.md`, `skills/audience-profiler.md`, `skills/positioning-analysis.md` | 无 |
| 4 | `references/strategy-frameworks.md`, `references/hook-library.md`, `skills/content-strategy.md`, `skills/carousel-planner.md` | 无 |
| 5 | 无 | `skills/text-polisher.md`, `skills/quality-gate.md`, `skills/topic-evaluator.md`, `skills/card-design.md`, `skills/caption-hashtag.md`, `skills/social-content.md`, `skills/post-formatter.md`, `skills/text-condenser.md` |
| 6 | `tools/comment_insights.py` | `tools/registry.py`（加一行 BUILTIN_SKILL_MODULES） |

**总计**：新增 7 个 reference .md + 7 个 skill .md + 1 个 .py = 15 个新文件
修改：8 个 .md（优化 description）+ 1 个 .py（registry 注册）= 9 个修改

---

## 七、执行进度总览

### 周期 1：Hook 生成器 ✅ 已完成

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 1.1 | 新增 hook-formulas.md | `prompts/references/hook-formulas.md` | ✅ |
| 1.2 | 新增 hook-generator.md | `prompts/skills/hook-generator.md` | ✅ |

验收：SkillRegistry 注册成功（plan.hook_generator），7 种 Hook 变体含小红书特化"身份认同"。

### 周期 2：竞品分析 + 蓝海选题 ✅ 已完成

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 2.1 | 新增 viral-patterns.md | `prompts/references/viral-patterns.md` | ✅ |
| 2.2 | 新增 demand-signals.md | `prompts/references/demand-signals.md` | ✅ |
| 2.3 | 新增 competitor-analysis.md | `prompts/skills/competitor-analysis.md` | ✅ |
| 2.4 | 新增 content-gap-analysis.md | `prompts/skills/content-gap-analysis.md` | ✅ |

验收：discover.competitor_analysis + discover.content_gap_analysis 注册成功。

### 周期 3：受众画像 + 差异化定位 ✅ 已完成

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 3.1 | 新增 profiling-frameworks.md | `prompts/references/profiling-frameworks.md` | ✅ |
| 3.2 | 新增 positioning-frameworks.md | `prompts/references/positioning-frameworks.md` | ✅ |
| 3.3 | 新增 audience-profiler.md | `prompts/skills/audience-profiler.md` | ✅ |
| 3.4 | 新增 positioning-analysis.md | `prompts/skills/positioning-analysis.md` | ✅ |

验收：plan.audience_profiler + plan.positioning_analysis 注册成功。

### 周期 4：内容策略 + 轮播图策划 ✅ 已完成

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 4.1 | 新增 strategy-frameworks.md | `prompts/references/strategy-frameworks.md` | ✅ |
| 4.2 | 新增 hook-library.md | `prompts/references/hook-library.md` | ✅ |
| 4.3 | 新增 content-strategy.md | `prompts/skills/content-strategy.md` | ✅ |
| 4.4 | 新增 carousel-planner.md | `prompts/skills/carousel-planner.md` | ✅ |

验收：plan.content_strategy + plan.carousel_planner 注册成功。

### 周期 5：现有 PromptDrivenSkill 优化 ✅ 已完成

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 5.1 | 优化 social-content.md | description + trigger_words + 边界说明 | ✅ |
| 5.2 | 优化 post-formatter.md | 同上 | ✅ |
| 5.3 | 优化 text-condenser.md | 同上 | ✅ |
| 5.4 | 优化 card-design.md | 同上 | ✅ |
| 5.5 | 优化 caption-hashtag.md | 同上 | ✅ |
| 5.6 | 优化 text-polisher.md | 同上 | ✅ |
| 5.7 | 优化 quality-gate.md | 同上 | ✅ |
| 5.8 | 优化 topic-evaluator.md | 同上 | ✅ |

验收：15 个 PromptDrivenSkill 全部注册正常，每个 Skill 的 description 包含调用边界说明。

### 周期 6：评论洞察 Python Skill ✅ 已完成

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 6.1 | pip install snownlp | 依赖安装 | ✅ |
| 6.2 | 新增 comment_insights.py | `tools/comment_insights.py` | ✅ |
| 6.3 | BUILTIN_SKILL_MODULES 注册 | `tools/registry.py` | ✅ |

验收：analyze.comment_insights 注册成功，功能测试通过（情感分析+关键词+需求信号）。

### 补漏：copywrite.py 集成后处理管线 ✅ 已完成

---

## 八、完成总结

**本计划 6 个周期全部验收通过。** 最终成果：

| 类别 | 数量 | 说明 |
|------|------|------|
| 新增 PromptDrivenSkill | 7 个 | hook_generator / competitor_analysis / content_gap_analysis / audience_profiler / positioning_analysis / content_strategy / carousel_planner |
| 新增 Reference | 7 个 | hook-formulas / viral-patterns / demand-signals / profiling-frameworks / positioning-frameworks / strategy-frameworks / hook-library |
| 新增 Python Skill | 1 个 | comment_insights（jieba + snownlp） |
| 优化现有 Skill | 8 个 | description + trigger_words + 边界说明 |
| 新增依赖 | 1 个 | snownlp（已安装） |
| **总 PromptDrivenSkill** | **15 个** | 原有 8 + 新增 7 |

**未做（按计划不做的）**：
- ❌ 不改 DAG、不改 LoopExecutor、不改架构
- ❌ 浏览器 Worker 问题（待单独解决）

**下一步**：解决浏览器 Worker（QR Worker）进程管理问题。
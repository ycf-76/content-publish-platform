# 项目 Skills 与执行层映射分析报告

> 分析时间：2026-10-10
> 结论先行：**"用不了的 skills" 绝大多数不是坏了，而是根本不存在对应的执行层；视频/语音尤其如此。**

---

## 一、先纠正一个关键认知：项目里有两套完全不同的 "skill"

你以为的"skills"其实是两个机制，依赖的执行层天差地别：

| 类型 | 位置 | 数量 | 执行层是什么 | 能不能跑 |
|------|------|------|--------------|----------|
| **提示词型 Skill**（`PromptDrivenSkill`） | `backend/app/agents/prompts/skills/*.md` | **65 个** | 仅 LLM 本身（`model_router`）+ 可选的 references 文本 | 只要 LLM 通，**永远能跑**（只产出文本/HTML） |
| **代码型 Skill**（`Skill` 子类） | `backend/app/tools/*.py`（`BUILTIN_SKILL_MODULES`） | **14 个** | 各自依赖外部服务/二进制/密钥 | 依赖不到位就报"未配置/不可用" |

你列表里看到的 `video_script`（视频脚本生成）、`voice_builder`（声音画像）、`card_design`、`poster_hero`、`mindmap` 等**全是第 1 类**——它们是 `.md` 提示词，本质是"教 LLM 怎么写"。

**所以 `video_script` "用不了"是个误解：它本来就不渲染视频，它只写脚本文本。** 真正缺的是把脚本变成视频/语音的执行层（见第五节）。

---

## 二、执行层全景图

```
                         ┌─────────────────────────────────────────┐
   用户意图 ──►  SkillRouter 路由（trigger_words + 分类热加载）
                         └─────────────────────────────────────────┘
                                      │
              ┌───────────────────────┴────────────────────────┐
              ▼                                                 ▼
   提示词型 Skill (.md)                              代码型 Skill (.py)
   execute() = 读 md 当 prompt → 调 LLM → 返回文本       execute() = 真正干实事
   执行层 = LLM (model_router)                         执行层 = 下方各自的外部依赖
   （卡片类还会回调 card_image_gen 生图）               （API key / 浏览器 / 二进制 / 模型）
```

**关键结论**：65 个提示词型 skill 的"执行层"只有 LLM 一个，项目已经具备；14 个代码型 skill 才是真正需要"执行层 infrastructure"的地方，而其中视频/语音这条线**从代码层面就断了**。

---

## 三、14 个代码型 Skill 的执行层依赖清单（这才是真正要补的）

| 模块 | node_type | 真实执行层依赖 | 现状 |
|------|-----------|----------------|------|
| `copywrite_builder` | copywrite | LLM（文案生成） | ✅ 可用 |
| `trending_search` | search | 外部搜索源：`serper`(需 `SERPER_API_KEY`)、youtube/reddit/hotboard/devto/github（httpx + 各 API key）；XHS 走 Playwright+登录态 | ⚠️ 缺 key 则降级/失败 |
| `vl_analyze` | analyze | 视觉模型（Qwen-VL / 多模态，通常 `DASHSCOPE_API_KEY`） | ⚠️ 缺 key 不可用 |
| `xhs_search` | search | `mcp_manager` 插件 client + Playwright 兜底，需小红书登录态 `storage_states/*.json` | ⚠️ 登录态过期即失效 |
| `dev_tools` | dev | 沙箱 shell，白名单：`git/ls/cat/ffmpeg/ffprobe/piper/curl/...` | ✅ 可用（**唯一能碰 ffmpeg/piper 的入口**） |
| `file_tools` | file | 本地文件系统 | ✅ 可用 |
| `wechat_send_text_skill` | wechat | 微信 RPA（`rpa/wechat_ilink_client.py` / `wechat_bot_engine.py`）+ 登录态 | ⚠️ 需 RPA 登录态 |
| `wechat_send_file_skill` | wechat | 同上 | ⚠️ 需 RPA 登录态 |
| `feishu_file_ops_skill` | feishu | 飞书 API（需 `app_id`/`app_secret`） | ⚠️ 缺凭证不可用 |
| `feishu_wiki_doc_skill` | feishu | 飞书 API（同上） | ⚠️ 缺凭证不可用 |
| `prompt_skills` | （加载器） | 无外部依赖 | ✅ 可用 |
| `card_compose` | produce | LLM + 本地 HTML 排版 | ✅ 可用 |
| `card_image_gen` | produce | **WanxAdapter / 通义万相，需 `DASHSCOPE_API_KEY`**（代码见 `tools/card_image_gen.py:51`） | ⚠️ 缺 key 报"未配置" |
| `comment_insights` | attribute | 小红书评论抓取，Playwright + 登录态 | ⚠️ 登录态过期即失效 |

**注**：`comment-insights.md`（提示词型）与 `comment_insights.py`（代码型）同名同 node_type，运行时后者会覆盖前者——属于命名冲突小坑，不展开。

---

## 四、65 个提示词型 Skill：它们"需要"的执行层其实只有 LLM

按 `node_type` 分布（全为 `PromptDrivenSkill`，执行层=LLM）：

| node_type | 数量 | 这类 skill 做什么 | 备注 |
|-----------|------|-------------------|------|
| `produce` | 23 | 卡片/海报文案、脚本、思维导图、长文、信息图、视频脚本/策略等 | 卡片类可回调 `card_image_gen` 生图（需 dashscope key） |
| `plan` | 17 | 选题/定位/人设/声音画像/内容日历/直播等规划 | 纯规划文本 |
| `discover` | 9 | 热点/竞品/新闻/选题缺口/跨平台差异等发现 | 部分要真实数据，但 .md 本身不抓数据，只教 LLM 用 `trending_search` 等工具 |
| `attribute` | 7 | 评论洞察/数据追踪/打分/复盘 | 纯分析文本 |
| `publish` | 6 | 人设校验/SEO/风险扫描/社区运营/发布清单 | 纯文本 |
| `quality_gate` | 1 | 质量门禁 | 纯文本 |
| `caption_hashtag` | 1 | 标题+话题 | 纯文本 |
| `polish` | 1 | 文本润色 | 纯文本 |
| `topic_evaluator` | 1 | 选题评估 | 纯文本 |

**这 65 个"不需要"任何额外执行层**——只要你的 LLM（model_router）通，它们就能产出文本/HTML。它们"看起来用不了"通常是因为：① 期望它们干实事（比如以为 `video_script` 出视频），② 或它们依赖的真实数据工具（搜索/抓取）因为缺 key/登录态而失败，于是 LLM 拿不到数据。

---

## 五、视频 / 语音为什么"用不了" —— 根因（重点）

### 5.1 视频脚本 ≠ 视频
- `video_script.md` (`node_type: produce`)：`execute()` 只生成**文本脚本**写到 `outputs/`，并引用 `skills/shared/scripts/wordcount.py` 做字数检查。**不渲染视频。**
- `voice_builder.md` (`node_type: plan`)：生成 `about-me.md` + `voice.md` 文本。**不合成语音。**

### 5.2 把"脚本 → 视频"真正需要的执行层（三层栈），项目现状

| 执行层 | 作用 | 项目现状 |
|--------|------|----------|
| **① TTS 语音合成** | 口播文案 → 音频 | `piper` 仅在 `dev_tools` 白名单里作为**手动 shell 命令**存在，**未封装成可自动调用的 Skill**，且无语音模型文件/音色库 |
| **② 画面/图像生成** | 脚本画面 → 图/视频帧 | 卡片图走 `card_image_gen`(Wanx/dashscope key)；**图生视频模型（即梦/可灵等）未接入** |
| **③ 视频合成引擎** | 音频+画面+字幕 → mp4 | `ffmpeg` 同样只在 `dev_tools` 白名单里；**整个 backend 没有 `video_compose`/`openmontage`/`moviepy` 模块被接成 Skill**（全仓 grep 仅在 `dev_tools.py` 见到 ffmpeg 字样） |

**根因**：缺少一个把 ①②③ 串起来的 **`produce` 视频代码型 Skill（或编排流）**。当前 `produce` 节点下的视频相关 skill 全是 `.md` 文本型，没有下游执行编排；且 piper 语音模型、视频合成引擎都未就绪。这与工作记忆记载的"视频制作 pipeline 断链"一致。

---

## 六、哪些"用不了"只是缺密钥/登录态（代码在，配一下就有）

不是代码缺失，是环境没配齐：

1. **生图/视觉** (`card_image_gen`, `vl_analyze`) → 配 `DASHSCOPE_API_KEY`（通义万相/Qwen-VL）
2. **全网搜索** (`trending_search` serper 源) → 配 `SERPER_API_KEY`
3. **小红书搜索/评论** (`xhs_search`, `comment_insights`) → 刷新 `storage_states/*.json` 登录态（cookie 绑设备指纹，旧 cookie 失效）
4. **飞书** (`feishu_*`) → 配飞书 `app_id`/`app_secret`
5. **微信** (`wechat_*`) → 起 RPA 登录态（`rpa/wechat_ilink_client.py`）

---

## 七、给你的行动建议（分阶段）

**阶段 0 — 认知对齐（现在就能做）**
- 把 65 个 `.md` skill 当作"LLM 提示词库"，它们本来就能产出文本/HTML，不要再期待它们出视频/音频/真图。
- 真正要"执行层"的只有上面 14 个代码型 skill。

**阶段 1 — 补配置（低成本，立刻解锁一批）**
- 配 `DASHSCOPE_API_KEY` → 解锁生图 + 视觉理解
- 配 `SERPER_API_KEY` → 解锁全网搜索
- 刷新小红书/微信登录态 → 解锁搜索与发布链路

**阶段 2 — 补视频/语音执行层（这是你"视频用不了"的真正缺口）**
需要新建/接通：
1. 一个 TTS 封装 Skill（piper 或 edge-tts/cosyvoice，需语音模型文件）
2. 图生视频接入（即梦/可灵等，需 API key）
3. 一个 `produce` 视频合成 Skill（ffmpeg 轨道编排 + 字幕烧录），把 ①语音 ②画面 ③ffmpeg 串成一条流水线
4. 让 `video_script` 这类提示词 skill 的产出能喂给上面的视频 Skill（目前两者没有接线）

**阶段 3 — 清理**
- 处理 `comment-insights` 同名冲突（md 与 py 覆盖）
- 删除/归档你既不打算配 key、也不打算接执行层的第三方 skill，避免"看起来很多、实际用不了"的库存错觉

---

## 附：一句话总结
> 你"继承的 skills"里，65 个提示词型是纯 LLM、已经能跑；14 个代码型才需要执行层，其中视频/语音这条线**从代码到依赖都断着**——缺的是 TTS 封装 + 图生视频 + ffmpeg 合成编排这三层，而不是 skill 本身坏了。

---

## 八、capability_tier 标记方案（已落地）

### 8.1 四级分类

| tier | 含义 | 当前环境可用？ | 数量 |
|------|------|---------------|------|
| `text_only` | 纯 LLM 文本出力 | ✅ 永远可用 | 52 |
| `html_card` | LLM 出 HTML，需前端 iframe 渲染 | ✅ 前端已有 `ChatCardDraft.vue` | 10 |
| `image_render` | 需后端图片处理（Pillow 等脚本） | ❌ `shared/scripts/` 不存在 | 2 |
| `external_service` | 需外部 API/服务（AntV/TTS/视频等） | ❌ 未接入 | 2 |

### 8.2 注入位置

- **frontmatter**：每个 `.md` 文件新增 `capability_tier: xxx` 字段
- **类属性**：`prompt_skills.py` 的 `_create_skill_class()` 中注入 `_DynamicSkill.capability_tier`
- **默认值**：未声明 tier 的 Skill 默认为 `text_only`（向后兼容）

### 8.3 SkillRouter 过滤

- `SkillRouter.__init__(enabled_tiers=None)`：默认不过滤（全量注入）
- 传入 `enabled_tiers={"text_only", "html_card"}` 后，`image_render` 和 `external_service` 的 Skill 被过滤掉，记录在 `RoutingResult.restricted_skills`
- 路由表中 `image_render` / `external_service` 的 Skill 标注 ⚠️[需图片处理] / ⚠️[需外部服务]，LLM 路由时优先选可用 Skill

### 8.4 实际分布

```
text_only (52): copywriting, xhs_note_creator, social_content, quality_gate, risk_scanner,
  persona_check, trending_topics, competitor_analysis, content_gap_analysis, algorithm_updates,
  news_intelligence, cross_platform_diff, content_strategy, content_calendar, campaign_planner,
  content_matrix, collab_proposal, brand_onboarding, hook_generator, caption_hashtag,
  text_polisher, text_condenser, style_transfer, article_outline, video_script, video_strategy,
  livestream, profile_builder, profile_manager, audience_profiler, positioning_analysis,
  strategy_advisor, post_scorer, seo_quality, publish_checklist, community_ops,
  content_repurposing, publish_analytics, novel_writer, paper_explainer, voice_builder,
  topic_evaluator, account_diagnosis, event_calendar, rss_aggregator, ugc_discovery,
  social_performance_review, data_tracker, content_postmortem, comment_insights,
  trend_rider, carousel_planner

html_card (10): card_xiaohongshu, card_design, card_quote, comparison_card, poster_hero,
  infographic, mindmap, post_formatter, gzh_design, ecom_details_image

image_render (2): meme_generator, doc_convert

external_service (2): chart_visualization, data_report
```

---

## 九、降级输出策略

核心思路：**缺执行层的 Skill 不是"用不了"，而是"产出物降级"**。中间的结构化输出本身就是有价值的交付物。

| Skill | 完整产出（需执行层） | 降级产出（当前可用） | 降级产物价值 |
|-------|---------------------|---------------------|-------------|
| `video_script` | 视频 mp4 | 结构化分镜脚本 + 封面 HTML 预览 | ⭐⭐⭐ 脚本本身就是交付物，用户拿去剪映合成 |
| `voice_builder` | 语音音频 | 话术文本 + 语调/节奏标注 | ⭐⭐⭐ 话术本身就是交付物，用户自己录制 |
| `meme_generator` | 表情包图片 | 上方/下方文字描述 + HTML 预览 | ⭐⭐ 用户可用任意工具加字 |
| `infographic` | AntV 高级图表 | 纯 HTML+CSS 信息图 | ⭐⭐⭐ 已能出可用信息图，只是缺 AntV 高级图表类型 |
| `chart_visualization` | AntV 远程渲染图表 | 文字描述 + 数据表 | ⭐ 用户手动用 Excel/ECharts 做 |
| `data_report` | 完整可视化报告 | 文字分析 + 数据表 + HTML 摘要 | ⭐⭐ 分析结论本身就是交付物 |
| `livestream` | 直播推流 | 完整话术脚本 + 流程时间表 | ⭐⭐⭐ 话术本身就是交付物 |

### 降级输出实现方式

在 `PromptDrivenSkill.execute()` 中，LLM 生成的文本/HTML 已经是降级产物——**不需要额外代码**。关键是在 Skill 的 SKILL.md 正文和 `prompt_guidance` 中明确告知 LLM：

> "当环境不支持 [完整渲染] 时，输出结构化 [文本/HTML] 格式，用户可自行用 [工具名] 完成最终渲染。"

例如 `video_script.md` 的 prompt_guidance 可以追加：
```
注意：本 Skill 产出视频脚本文本，不渲染视频。用户可拿脚本到剪映/PR 合成视频。
```

这比硬编码降级逻辑更灵活——LLM 自己知道怎么在能力边界内给出最大价值。

---

## 十、补执行层的 ROI 排序（更新版）

| 优先级 | 补什么 | 成本 | 解锁 Skill | 用户价值 |
|--------|--------|------|-----------|---------|
| **P0** | 配 `DASHSCOPE_API_KEY` | 0 代码 | card_image_gen, vl_analyze | 生图+视觉理解 |
| **P1** | 配 `SERPER_API_KEY` | 0 代码 | trending_search (serper源) | 全网搜索 |
| **P2** | `shared/scripts/meme_ops.py` | 半天 | meme_generator | 表情包是社媒刚需 |
| **P3** | AntV/ECharts 前端组件 | 1-2天 | chart_visualization, data_report | 数据可视化 |
| **P4** | mermaid 前端组件 | 半天 | mindmap (高级模式) | 思维导图 |
| **P5** | HTML→PNG 导出 (Puppeteer) | 1天 | 所有 html_card 可导出 | 卡片发布 |
| **P6** | TTS 适配器 (edge-tts 免费) | 1天 | voice_builder→音频 | 语音合成 |
| **P7** | TTS 适配器 (CosyVoice 高质) | 1-2天 | voice_builder→高质量音频 | 专业语音 |
| **P8** | 视频渲染管线 (ffmpeg) | 1-2周 | video_script→视频 | 视频制作 |
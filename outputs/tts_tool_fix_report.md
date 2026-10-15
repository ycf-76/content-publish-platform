# TTS「Agent 查无此能力」修复记录

日期：2026-10-10
症状：Agent 回复"没有语音合成能力"，但代码里明明有 `tts_edge` 这个 Skill。

## 根因：两个问题叠加

| # | 根因 | 说明 |
|---|------|------|
| 1 | **缺依赖** | venv 没装 `edge_tts` → `app/skills/produce/tts.py` import 失败 → `@register` 没执行 → `tts_edge` 压根没进 SkillRegistry |
| 2 | **白名单漏配（主因）** | `app/agents/registry.py` 的 `CREATION_TYPE_SKILLS` 是硬编码白名单。请求只要带 `creation_type`（**前端每次都传**），Agent 工具表就只保留白名单内的 Skill。`tts_edge` 没写进任何创作类型 → 被静默丢弃 |

关键点：**#1 修好后 #2 仍然会让 TTS 不可见**。只装包不够。

## 改动

| 改动 | 文件 |
|------|------|
| 安装 `edge_tts==7.2.8` 到 `backend/.venv` | 环境 |
| 新增 `ALWAYS_LOAD_CAPABILITY_SKILLS` 常驻能力清单（`tts_edge`/`url_collect`/`meme_render`/`wechat_send_*`/`feishu_*`） | `backend/app/agents/registry.py` |
| `_resolve_creation_type_skills()` 合并常驻清单 | `backend/app/agents/registry.py` |
| 新增 `_audit_skill_coverage()`：启动/首次建 harness 时告警所有「已注册但白名单覆盖不到」的 Skill，防止再次踩坑 | `backend/app/agents/registry.py` |

## 验证结果

端到端跑 `LoopExecutor._build_tools_schema()`（绕过 `__init__` 避免拉 LLM），逐个创作类型检查 Agent 真实工具表：

| 场景 | skills → tools | tts_edge |
|------|---------------|----------|
| 全量（不带 creation_type） | 90 → 65（触发截断） | ✅ |
| image_text | 57 → 57 | ✅ |
| voiceover | 49 → 49 | ✅ |
| short_video | 48 → 48 | ✅ |
| ai_edit | 48 → 48 | ✅ |
| long_article | 52 → 52 | ✅ |
| live_clip | 45 → 45 | ✅ |

**反证**（把常驻清单清空还原修复前）：`voiceover`/`short_video`/`image_text` 全部 ❌ 看不到 `tts_edge`。

**实际产物**：`TTSSkill().execute()` 产出 `backend/outputs/tts_output.mp3`，40752 字节，播放正常。

## 顺带发现：35 个 Skill 白名单覆盖不到

审计告警列出这些已注册 Skill 不在任何 creation_type 白名单里：

`video_script`、`video_strategy`、`chart_visualization`、`mindmap`、`novel_writer`、
`paper_explainer`、`doc_convert`、`data_report`、`gzh_design`、`ecom_details_image`、
`meme_generator`、`vl_analyze`、`account_diagnosis`、`article_outline`、`audience_profiler`、
`brand_onboarding`、`campaign_planner`、`collab_proposal`、`content_calendar`、`content_strategy`、
`livestream`、`profile_builder`、`profile_manager`、`trend_rider`、`algorithm_updates`、
`cross_platform_diff`、`event_calendar`、`news_intelligence`、`rss_aggregator`、`ugc_discovery`、
`post_scorer`、`publish_analytics`、`social_performance_review`、`community_ops`、`seo_quality`

→ 带 creation_type 的请求里 Agent 全部看不到它们。**这大概率就是"继承了很多 skills 都用不了"的另一半根因**（另一半是缺执行层，见 `skills_execution_layer_analysis.md`）。

待大哥拍板：是要把 `CREATION_TYPE_SKILLS` 的覆盖面重做（按 node_type 全量放行），还是干脆弱化白名单（反正全量 90 也就截到 65）。

## 其他

- **piper TTS 本机不可用**：espeak-ng-data 路径硬编码到 `D:/a/piper1-gpl/...`，文件缺失，产出 0 字节 wav。别再试，走 edge-tts。
- 后端已重启（端口 8000），日志 `✅ Skill warmup` + `Application startup complete`。

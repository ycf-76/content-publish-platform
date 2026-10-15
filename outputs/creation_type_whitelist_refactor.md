# CREATION_TYPE_SKILLS 白名单重构：从过滤器改为排序器

日期：2026-10-11
背景：排查 TTS「Agent 查无此能力」时发现，白名单硬过滤导致 35 个已注册技能静默消失。

## 白名单是什么

`backend/app/agents/registry.py` 里的 `CREATION_TYPE_SKILLS` 字典，按创作类型手工罗列技能名：

```python
"voiceover": {
    "produce": ["copywriting", "social_content", "style_transfer"],
    "plan":    ["content_matrix", "hook_generator", "voice_builder"],
    "search":  ["trending_search", "xhs_search", ...],
}
```

前端每次请求带 `creation_type`，`_build_skills()` 查表后**只放行名字在集合里的技能**。
设计初衷是"按需加载、少塞工具"，实际成了漏斗杀手：**手工维护，漏配即静默消失**。

数据：白名单覆盖 **55** 个名字（全部真实存在，无拼写错误），注册表里有 **90** 个 → 差 35 个孤儿。

## 方案选型

| 方案 | 做法 | 评价 |
|------|------|------|
| A 补全白名单 | 把 35 个孤儿逐个分配进 6 个创作类型 | 雷还在：新增技能仍会漏配；且需逐个判断语义，我不了解每个技能的定位 |
| **B 白名单降级为排序器（采纳）** | 不再过滤，只把命中的排前面 | 注册即可见，杜绝静默消失；保留"任务相关技能优先"的语义 |
| C 直接废弃白名单 | 全量加载，纯按 priority 截断 | 简单，但当前任务相关的 cold 技能可能被无关 hot 技能挤掉 |

**拍板 B**，并附带修好失效的 triggered 保命机制。

## 改动

| 改动 | 文件 |
|------|------|
| `_build_skills()` 白名单由过滤改为排序（命中排前），删掉旧的 `_hot_create_names` 补丁 | `backend/app/agents/registry.py` |
| `_audit_skill_coverage()` 语义更新：漏配只告警"丧失排序优先级"，另加**反向审计**「白名单写了但注册表没有的名字」 | `backend/app/agents/registry.py` |
| 路由前移到 `_build_tools_schema()` 之前，让 trigger_words 命中的技能真正进入 triggered 优先队列 | `backend/app/engine/harness/executor/loop.py` |

### 顺手修掉的隐藏 bug：triggered 队列是死代码

`execute()` 里 `_build_tools_schema()` 在 L362 就跑完并缓存，而路由（算 trigger_words 命中）在 L1188 才执行。
结果 `_build_tools_schema` 读到的 `_routing_result` 永远是 `None` → triggered 队列永远为空
→ **用户点名要的冷门技能在 65 上限截断时照样被砍，trigger_words 形同虚设**。

修法：在 `execute()` 里、建表之前先跑一次 `select_skills()`。

## 验证

| 场景 | skills | tools | tts_edge | video_script | mindmap |
|------|--------|-------|----------|--------------|---------|
| 全量 | 90 | 65 | ✅ | ✅ | ✅ |
| image_text | 90 | 65 | ✅ | ✅ | ✅ |
| voiceover | 90 | 65 | ✅ | ✅ | ✅ |
| short_video | 90 | 65 | ✅ | ✅ | ✅ |
| ai_edit | 90 | 65 | ✅ | ✅ | ✅ |
| long_article | 90 | 65 | ✅ | ✅ | ✅ |
| live_clip | 90 | 65 | ✅ | ✅ | ✅ |

- **白名单命中存活率（voiceover）**：17/17 = 100%，排序确实能在截断时保命
- **triggered 保命（修前 → 修后）**：
  - 用户说「帮我做个表情包」→ `meme_render` ❌ → ✅
  - 用户说「帮我把这个文档转成PDF」→ `doc_convert` ❌ → ✅

## 代价（需要知道）

工具数从每个请求约 49 个涨到 **65 个**（截断上限），单次请求 prompt token 增加约 1600。
换来的是 35 个技能从"永久不可见"变"可用"。如果嫌贵，可以把 `_MAX_TOOLS_FOR_LLM` 调回更小值，
但有了 triggered 保命机制，用户点名要的技能不会被砍，缩小上限是安全的。

## 遗留

35 个孤儿现在能加载，但没有任何创作类型给它们排序优先级。若要让它们在对应场景优先，
仍需补进 `CREATION_TYPE_SKILLS`——但这次补错了也不会消失，只是优先级低。

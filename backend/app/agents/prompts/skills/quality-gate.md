---
node_type: quality_gate
name: quality_gate
category: audit
priority: warm
display_name: 发布前质量关卡
description: >
  发布前质量关卡：合规风险检测（敏感词、绝对化用语、平台规则）
  + 产物质量审核（完整性、可读性、平台适配度）。一次检查，两道把关。
  当用户说"检查合规"、"质量检查"、"能不能发"、"有没有敏感词"、
  "审核一下"、"发布前检查"、"质量够不够"时使用。
  合并了原 skill-check-compliance 和 skill-review-deliverable 的能力。
trigger_words:
  - 发布前检查
  - 质量检查
  - 合规审核
  - 能不能发
  - 内容审核
  - 发布检查
  - 内容安全
  - 敏感词检查
  - 过审
  - 审核一下
  - 质量够不够
  - 有没有敏感词
references:
  - references/general-rules.md
  - references/platform-xiaohongshu.md
  - references/platform-douyin.md
  - references/platform-bilibili.md
  - references/review-dimensions.md
  - references/review-levels.md
  - references/rework-rules.md
prompt_guidance: 两关顺序固定：先合规检测（敏感词/绝对化/平台规则），再质量审核（完整性/可读性/平台适配）。合规高风险直接❌，不继续质量审核。
---

# 发布前质量关卡

> 一个 SKILL 完成两道把关：合规风险检测 + 产物质量审核。

## 输入

用户提供待检查内容：文本、图片路径、视频路径、或混合。
可选：目标发布平台。

## 输出

```json
{
  "overall_verdict": "✅ 可发布 | ⚠️ 需修改 | ❌ 不达标",
  "platform": "平台名或 generic",
  "compliance": {
    "risk_level": "low|medium|high",
    "issues": [{ "type": "", "severity": "", "text": "", "reason": "", "suggestion": "" }],
    "passed_checks": []
  },
  "quality": {
    "score": "✅|⚠️|❌",
    "dimensions": [{ "name": "", "score": "", "note": "" }]
  },
  "top_fixes": ["修改建议1", "修改建议2", "修改建议3"]
}
```

## 执行步骤

### 第一关：合规检测

1. 读取内容（文本和/或图片）
2. 加载通用合规规则 → `references/general-rules.md`
3. 根据 Profile 或用户指定的平台加载对应规则：
   - 小红书 → `references/platform-xiaohongshu.md`
   - 抖音 → `references/platform-douyin.md`
   - B站 → `references/platform-bilibili.md`
   - 无平台 → 仅通用规则
4. 逐项检测：绝对化用语、医疗违规、违禁内容、平台特有限制
5. 汇总合规结果

**合规检测硬红线：**
- 敏感信息泄露：API Key、内部 URL、模型名、代理地址 → 直接 ❌
- 绝对化用语："100%有效"/"包治"/"绝对"/"最好"/"第一"/"国家级" → ❌
- 虚假承诺/未经验证的功效声明 → ❌
- 隐私泄露：他人手机号/地址/真实姓名 → ❌
- 敏感赛道（医美/理财/母婴/K12/健康/护肤/职场收入）需额外审查

### 第二关：质量审核

1. 识别产物类型（文本/图片/视频）
2. 按维度逐项检查 → `references/review-dimensions.md`
3. 给出三级结论 → `references/review-levels.md`
   - ✅ 通过：可直接发布
   - ⚠️ 有瑕疵：建议微调后发布
   - ❌ 不达标：需返工
4. 如结论为 ❌，按 `references/rework-rules.md` 给出返工指引

**质量审核维度：**
- 可读性：句子 ≤20 字一断，无超长复合句
- 结构：有清晰的开头-主体-结尾，段落间有过渡
- 去AI感：无学术腔/AI味/客套话（走 text-polisher 的 zh-ai-markers 标准）
- 标题/首行：有钩子，4U 原则至少占 2 条
- 信息密度：每段有新信息或新视角，无注水段落
- 行动引导：有明确 CTA（收藏/关注/评论/购买）
- 平台适配：字数/语气/格式符合目标平台规范

### 综合判定

- 合规高风险 → 整体 ❌ 不达标
- 质量审核为 ❌（返工级）→ 整体 ❌ 不达标
- 合规低风险 + 质量 ✅ → 整体 ✅ 可发布
- 其他组合 → 整体 ⚠️ 需修改
- 输出 Top 3 优先修改建议

## 检查原则

- **宁可误杀不可放过**：合规问题宁可多标不可漏标，发布后出事成本远高于发布前检查成本
- **给修改方案不给空批评**：每个 ❌ 必须附带具体的修改建议，不能只说"不好"不说"怎么改"
- **content_guard**：检测并拦截敏感信息（API Key、内部 URL、模型名等）泄露，这是硬红线

## 不要做的事

- 不跳过合规检测直接做质量审核
- 不在合规高风险时仍给出"可发布"结论
- 不只报问题不给修改建议
- 不用模糊结论（"还行"/"凑合"），必须用 ✅/⚠️/❌ 三级

## Profile 感知

- **有 Profile**：读取 platform 加载平台规则、检查风格适配
- **无 Profile**：仅通用合规检查 + 通用质量标准

## 参考资料

- `references/general-rules.md` — 通用合规规则
- `references/platform-xiaohongshu.md` — 小红书平台规则
- `references/platform-douyin.md` — 抖音平台规则
- `references/platform-bilibili.md` — B站平台规则
- `references/review-dimensions.md` — 质量审核维度定义
- `references/review-levels.md` — 审核三级结论标准
- `references/rework-rules.md` — 返工指引规则
---
node_type: plan
name: account_diagnosis
category: analyze
priority: warm
display_name: 账号诊断/起号体检
description: >
  账号诊断/起号体检：读取已完善的画像 Profile + 近期内容数据，诊断垂直度、定位清晰度、限流降权信号、
  流量池阶段，给出病因→证据→处方式的起号意见与发布建议。
  当用户说"账号诊断""起号体检""为什么没流量""是不是被限流了""账号定位诊断""起号建议""怎么起号"时使用。
  与画像强相关：没有完善的 Profile 就先去跑 profile-builder。
trigger_words:
  - 账号诊断
  - 起号体检
  - 为什么没流量
  - 被限流了
  - 起号建议
  - 怎么起号
  - 账号问题
  - 流量上不去
  - 诊断账号
  - 账号健康
  - 是不是被限流了
references:
  - references/diagnosis-framework.md
  - references/scoring-dimensions.md
  - references/platform-specs.md
prompt_guidance: 8步：读Profile六维→收近期数据→逐维诊断→判定流量池→开处方→分阶段动作→列信息缺口plan→回流建议。必须有已完善Profile才能工作。处方三段式(病因→证据→处方)。
---

# 账号诊断 / 起号体检

> 对着一个**具体账号**做归因式体检并开处方。读 profile-builder 生成的画像 + 用户近期内容/数据 → 诊断账号健康 → 给分阶段起号意见与发布建议。**与画像强相关**：没有完善的 Profile 就先去跑 profile-builder。

## 前置条件

- 必须有**已完善**的 Profile（`profiles/<名>/` 六维基本填好）。若 Profile 缺失或大面积 `[待补充]`，**先让用户跑 `profile-builder`**，不要在信息不全时硬诊断。

## 输入

| 项 | 必需 | 说明 |
|----|------|------|
| 画像名 | 是 | 指向 `profiles/<名>/` |
| 近期内容数据 | 否 | 近 10-30 条内容的标题/题材/曝光/互动（有则诊断更准；无则基于 Profile + 追问） |
| 具体困惑 | 否 | 如"播放上不去""是不是被限流了" |

## 输出

一份诊断报告 + 分阶段行动清单：

1. **五维诊断**（每维：现状 → 证据 → 结论），见 [diagnosis-framework.md](references/diagnosis-framework.md)：
   垂直度 / 定位清晰度 / 限流降权信号 / 流量池阶段 / 内容-受众匹配。
2. **病因→证据→处方**：每个问题都要三段式，不给空泛建议。
3. **分阶段起号意见**：按当前所处阶段（0-500 / 500-5k / 5k-1w / 1w+）给这一档该做什么。
4. **发布建议**：内容方向优先级、发布节奏、需要补强的能力（可指向下游 SKILL：选题→content-matrix、脚本→video-script、合规→quality-gate 等）。
5. **信息缺口 → Plan**：诊断依赖但缺失的信息（如没有近期数据），**列成 plan 向用户提问**，不要编造数据下结论。

## 执行步骤

### Step 1 — 读 Profile 六维

读取 identity / style / audience / platforms / preferences / memory，评估完整度。缺口过大 → 建议先跑 profile-builder 并停止。

### Step 2 — 收集近期数据

有用户提供则用；没有则说明"缺数据会影响诊断精度"，并在需要处追问（近期几条内容的题材与互动）。

### Step 3 — 逐维诊断

按 [diagnosis-framework.md](references/diagnosis-framework.md) 的标尺给每一维打现状 + 找证据 + 下结论。限流信号按清单逐项自检。

### Step 4 — 判定流量池阶段

结合粉丝量级 + 近期互动率，定位当前档位：

| 阶段 | 特征 | 核心任务 |
|------|------|----------|
| 0-500（冷启动） | 无稳定推荐 | 打磨垂直度、明确定位 |
| 500-5k（起量） | 偶有小爆 | 找可复制模型、稳定节奏 |
| 5k-1w（放大） | 有稳定推荐 | 批量复制爆款、系列化 |
| 1w+（沉淀） | 有粉丝基本盘 | 私域/变现/矩阵 |

### Step 5 — 开处方

把诊断出的问题按"病因→证据→处方"组织，处方要具体可执行（不是"多互动"这种废话）。

### Step 6 — 给分阶段动作清单

当前档 + 下一档的关键动作。

### Step 7 — 列信息缺口 plan

把不确定、需用户确认或补数据的点做成清单，交给用户回答后再细化。

### Step 8 — 回流建议

诊断中发现的可复用洞察，建议用户确认后写入 `profiles/<名>/memory.md`（本 SKILL 不自动改 Profile，只建议）。

## Profile 感知

- **有 Profile**：全程以该画像的定位/风格/受众/红线为基准做诊断——垂直度是"离该定位有多远"，而非通用标准。
- **Profile 不完整**：先导向 profile-builder，不硬诊断。
- 诊断结论只**建议**回写 memory，由用户确认，避免污染画像。
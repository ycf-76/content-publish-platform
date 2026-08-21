# Skills 可插拔架构设计

## 一、核心思想

Skills 是对 LLM 输出的**后处理管道**。LLM 正常输出，Skill 在流式结束后对文本做二次加工。

```
用户消息 → LLM 正常输出 → Skill 管道 → 渲染
                              ↓
                     [划重点] [润色] [精简] ...
                     用户按需启用，可叠加
```

**为什么不靠提示词？**
- 提示词约束会干扰 LLM 输出质量
- 模型对自定义语法的遵从度不稳定
- Skill 是确定性代码，100% 可控、零延迟、零 API 调用

---

## 二、Skill 接口定义

```typescript
interface Skill {
  /** 唯一标识 */
  id: string
  /** 显示名称 */
  label: string
  /** 菜单图标 SVG path */
  icon: string
  /** Skill 分类，用于菜单分组 */
  category: 'analysis' | 'style' | 'format' | 'custom'
  /** 简短描述 */
  description: string
  /** 是否可与其他 Skill 叠加 */
  composable: boolean
  /** 后处理函数：输入原文，输出加工后文本 */
  process(text: string): string
}
```

### 关键设计决策

| 决策 | 原因 |
|---|---|
| `process` 是纯函数 | 无副作用、可测试、可缓存 |
| `composable` 标记 | 有些 Skill 可以叠加（划重点+润色），有些互斥（精简+扩写） |
| `category` 分组 | 菜单按分类展示，用户快速找到 |
| Skill 不感知渲染 | 只管文本变换，`==text==` → `<mark>` 由渲染层负责 |

---

## 三、Skill 管道执行

```typescript
function applySkills(text: string, activeSkillIds: Set<string>): string {
  let result = text
  for (const skill of skillRegistry) {
    if (activeSkillIds.has(skill.id)) {
      result = skill.process(result)
    }
  }
  return result
}
```

- 执行顺序 = 注册顺序（先注册先执行）
- 每个 Skill 拿到的是上一个 Skill 的输出
- 管道在 `finishReason === 'stop'` 时触发一次

---

## 四、已实现 Skills

### 4.1 划重点 Skill（highlight）

**ID**: `highlight`
**Category**: `analysis`
**Composable**: `true`

**规则引擎**：

| 规则 | 匹配模式 | 示例 |
|---|---|---|
| 粗体标记 | `**text**` → `==text==` | **核心优势** → ==核心优势== |
| 数字结论 | 含百分数/倍数/排名的短句 | 增长了 30% → ==增长了 30%== |
| 因果句 | "因此/所以/关键在于/核心是" 引导的短句 | 因此效率提升 → ==因此效率提升== |
| 总结句 | "总之/综上/总的来说" 引导的短句 | 总之方案可行 → ==总之方案可行== |
| 优美表达 | 四字成语/对仗句 | 行云流水 → ==行云流水== |

**保护机制**：
- 不标记代码块内的文本
- 不标记已有 `==` 标记的文本
- 每段最多标记 3 处，避免过度标记
- 标记长度限制：2-20 字

---

## 五、目录结构

```
frontend/src/components/chat/skills/
├── skill-types.ts          # Skill 接口定义
├── skill-registry.ts       # Skill 注册表 + 管道执行
└── skills/
    ├── highlight-skill.ts   # 划重点 Skill
    ├── polish-skill.ts      # （后续）润色 Skill
    └── concise-skill.ts     # （后续）精简 Skill
```

---

## 六、扩展指南

### 添加新 Skill

1. 在 `skills/` 目录下创建 `xxx-skill.ts`
2. 实现 `Skill` 接口
3. 在 `skill-registry.ts` 中注册
4. 菜单自动出现新选项，无需改模板

```typescript
// skills/my-skill.ts
import type { Skill } from '../skill-types'

export const mySkill: Skill = {
  id: 'my-skill',
  label: '我的 Skill',
  icon: 'M4 6h16',
  category: 'custom',
  description: '自定义 Skill',
  composable: true,
  process(text: string): string {
    // 你的变换逻辑
    return text
  },
}
```

```typescript
// skill-registry.ts
import { mySkill } from './skills/my-skill'

export const skillRegistry: Skill[] = [
  highlightSkill,
  mySkill,  // 加这一行
]
```

### 未来扩展方向

| 方向 | 说明 |
|---|---|
| **Skill 市场** | 用户上传/下载自定义 Skill |
| **Skill 配置** | 部分 Skill 暴露参数（如划重点的密度） |
| **Skill 预览** | 启用前可预览效果 |
| **异步 Skill** | 调用小模型做标注，process 返回 Promise |
| **Skill 组合预设** | 一键启用多个 Skill 的组合 |
# 划重点功能设计文档

## 1. 背景与问题

### 之前尝试过的方案及失败原因

| 方案 | 做法 | 失败原因 |
|---|---|---|
| 前端 Skill 正则后处理 | 在渲染时用正则匹配关键词，插入 `==...==` 标记 | 正则是关键词匹配，不是语义理解。"拉满"、"救命"被标了，"降噪深度 35dB" 没被标。区分度差 |
| System Prompt 让模型自己划 | 在 system prompt 里加划重点规则 | 干扰模型创作自由度，标记一致性和质量不可控 |
| 硬编码到 markdown-renderer | 在渲染函数里做正则替换 | 同样的正则问题，换个位置还是不行 |

**根本矛盾**：划重点需要理解"这段话在说什么、什么信息密度最高"，这是语义理解，正则做不了。

### 核心洞察

- 划重点的本质是 **信息密度排序**：从一段话中挑出信息密度最高的片段
- 正则只能做 **关键词匹配**，无法判断信息密度
- 只有 LLM 能做语义理解，但不应干扰主模型的创作

## 2. 新方案：后端 Highlight Agent

### 架构

```
用户提问 → 主模型生成回复 → 后端收到完整回复
                                      ↓
                              Highlight Agent（独立 LLM 调用）
                              输入：主模型回复原文
                              输出：带 ==...== 标记的文本
                                      ↓
                              前端渲染（markdown-it 解析 ==...== → <mark>）
```

### 设计原则

1. **主模型不受影响**：Highlight Agent 是独立调用，不修改主模型的 system prompt
2. **语义理解**：LLM 理解上下文，能判断什么是真正重要的
3. **可配置**：标记密度、风格、颜色都可以通过 prompt 控制
4. **渐进式**：流式阶段先显示原文，完成后异步替换为标记版本

## 3. 实现步骤

### Step 1：前端 — 恢复 `==...==` 解析和 `<mark>` 样式

**文件**：`frontend/src/components/chat/markdown-renderer.ts`

- 重新添加 markdown-it inline rule：`==text==` → `<mark>text</mark>`
- 这是纯渲染层，不涉及任何逻辑

**文件**：`frontend/src/components/chat/ChatView.vue`

- 重新添加 `<mark>` 的 CSS 样式（手绘马克笔效果）
- 添加暗色模式适配

### Step 2：后端 — 新增 Highlight Agent API

**文件**：`backend/app/api/routers/chat.py`

新增 `/api/chat/highlight` 端点：

```python
@router.post("/highlight")
async def highlight_text(request: HighlightRequest):
    """
    接收一段文本，返回带 ==...== 标记的版本。
    使用轻量模型（如 DeepSeek-V3）做单次调用。
    """
```

**请求体**：
```json
{
  "text": "主模型的完整回复文本",
  "density": "medium"  // low | medium | high
}
```

**响应体**：
```json
{
  "highlighted_text": "带 ==...== 标记的文本"
}
```

### Step 3：后端 — Highlight Agent 的 Prompt

```python
HIGHLIGHT_PROMPT = """你是一个划重点助手。阅读下面的文本，用 ==双等号== 包裹最值得注意的关键内容。

标记规则：
- 只标记信息密度最高的片段，整段文本标记不超过 5 处
- 优先标记：关键数据/指标、核心结论、因果关系、对比差异
- 不标记：标题、列表标记、语气词、普通描述、过渡句
- 每处标记 4-20 字，不要跨句子标记
- 输出必须与原文完全一致，只添加 == 标记，不增删改任何文字

文本：
{text}"""
```

### Step 4：后端 — 在聊天流程中集成

**文件**：`backend/app/api/routers/chat.py`

在流式响应完成后，异步调用 Highlight Agent：

```python
# 流式响应结束后
if finish_reason == "stop":
    # 异步调用 highlight agent，不阻塞主流程
    highlighted = await highlight_agent(full_text)
    # 通过 SSE 推送标记版本
    yield {"event": "highlight", "data": highlighted}
```

### Step 5：前端 — 接收 highlight 事件并替换

**文件**：`frontend/src/components/chat/ChatView.vue`

在 SSE 事件处理中添加 `highlight` 事件监听：

```typescript
if (event.event === 'highlight') {
  // 用标记版本替换原文，触发重渲染
  msg.content = event.data
}
```

## 4. 数据流

```
1. 用户发送消息
2. 后端调用主模型，流式返回回复 → 前端实时显示
3. 主模型回复完成（finish_reason: stop）
4. 后端调用 Highlight Agent（单次调用，约 1-2 秒）
5. 后端通过 SSE 推送 highlight 事件
6. 前端收到 highlight 事件，替换消息内容
7. markdown-it 解析 ==...== → <mark>
8. CSS 渲染手绘马克笔效果
```

## 5. 性能与成本

| 指标 | 估算 |
|---|---|
| 额外延迟 | 1-2 秒（异步，不阻塞主流程） |
| 额外 token 消耗 | 约为原文长度的 1.5x（输入 + 输出） |
| 模型选择 | 可用便宜快速模型（DeepSeek-V3 / GPT-4o-mini） |
| 用户感知 | 先看到原文，1-2 秒后重点被标记（渐进增强） |

## 6. 降级策略

- Highlight Agent 调用失败 → 保持原文，不标记
- Highlight Agent 超时（>5秒） → 取消，保持原文
- Highlight Agent 返回格式异常 → 校验后丢弃，保持原文
- 用户可关闭划重点功能 → 前端开关控制

## 7. 未来优化

- 缓存：相同文本不重复调用 Highlight Agent
- 批量：多条消息合并一次调用
- 本地模型：用小模型本地推理，零成本零延迟
- 用户自定义：允许用户手动调整标记
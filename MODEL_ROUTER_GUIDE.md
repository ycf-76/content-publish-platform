# 🤖 智能模型路由系统使用指南

## 📖 目录

1. [系统概述](#系统概述)
2. [核心能力](#核心能力)
3. [快速开始](#快速开始)
4. [使用场景](#使用场景)
5. [高级功能](#高级功能)
6. [与沙箱集成](#与沙箱集成)
7. [最佳实践](#最佳实践)
8. [故障排查](#故障排查)

---

## 系统概述

### 什么是 ModelRouter？

`ModelRouter` 是一个**智能模型路由器**，提供统一的LLM调用接口，支持：

- ✅ **自动模型选择** - 根据任务类型自动选择最优模型
- ✅ **动态模型切换** - 运行时/对话式模式中切换模型
- ✅ **智能降级** - 主模型失败时自动切换到备用模型
- ✅ **成本优化** - 在预算约束下选择性价比最高的方案
- ✅ **多提供商支持** - DeepSeek/OpenAI/Claude/Qwen/Wanx等

### 支持的模型矩阵

| 层级 | 模型 | 提供商 | 适用场景 | 成本(次) |
|------|------|--------|---------|----------|
| **Premium** | GPT-4o | OpenAI | 复杂分析、图片理解 | ¥0.135 |
| **Premium** | Claude 3.5 Sonnet | Anthropic | 长文案、深度写作 | ¥0.075 |
| **Standard** | DeepSeek V3 | DeepSeek | 文案生成、通用对话 | ¥0.0015 |
| **Standard** | Qwen Max | 阿里巴巴 | 中文场景、内容创作 | ¥0.003 |
| **Budget** | Qwen Turbo | 阿里巴巴 | 快速摘要、简单翻译 | ¥0.0006 |
| **Fallback** | Pollinations | 免费服务 | 图片生成(备选) | ¥0 |

---

## 核心能力

### 1️⃣ 自动智能路由

```python
from app.core.sandbox.model_router import (
    ModelRouter,
    ChatRequest,
    TaskType,
)

router = ModelRouter()

# 场景1: 文案生成 → 自动选DeepSeek (性价比最优)
result = await router.chat(ChatRequest(
    messages=[{"role": "user", "content": "写一篇小红书文案"}],
    task_type=TaskType.COPYWRITE,
))

print(result.model_used)      # "deepseek-chat"
print(result.content)         # 生成的文案
print(result.cost)            # ¥0.0015


# 场景2: 复杂分析 → 自动选Claude (质量最高)
result = await router.chat(ChatRequest(
    messages=[{"role": "user", "content": "深度分析这个竞品策略"}],
    task_type=TaskType.ANALYZE,
    require_high_quality=True,  # 要求高质量
))

print(result.model_used)      # "claude-3-5-sonnet-20241022"


# 场景3: 预算受限 → 自动选最便宜的可用模型
result = await router.chat(ChatRequest(
    messages=[{"role": "user", "content": "简单翻译"}],
    budget=0.001,             # 只有1厘钱预算
))

print(result.model_used)      # "qwen-turbo" 或 "pollinations-free"
```

### 2️⃣ 动态模型切换（对话式）

适用于需要用户确认或选择的场景：

```python
async def interactive_copywrite(topic: str):
    router = ModelRouter()
    
    # 使用交互模式
    async for event in router.chat_interactive(
        request=ChatRequest(
            messages=[{"role": "user", "content": f"写关于{topic}的文案"}],
            task_type=TaskType.COPYWRITE,
        ),
        allow_user_switch=True,  # 允许用户手动切换
    ):
        if event.event_type == "switch_required":
            # 💡 系统检测到有更好的模型选择
            print("发现更优模型:")
            for model in event.suggested_models:
                print(f"  • {model['display_name']}: {', '.join(model['reasons'])}")
            
            # 展示UI让用户选择
            user_choice = await show_model_picker_ui(event.suggested_models)
            
            if user_choice:
                # 用户选择了新模型，后续会使用新模型执行
                pass
        
        elif isinstance(event, ChatResponse) and event.success:
            print(f"✅ 完成! 使用模型: {event.model_used}")
            print(f"   内容: {event.content}")
            return event.content
```

**前端集成示例 (Vue)**:

```vue
<template>
  <div class="model-switch-dialog" v-if="showSwitchDialog">
    <h3>🔄 发现更优模型</h3>
    
    <div class="current-model">
      当前: {{ currentModel.display_name }}
      <span class="tier-badge">{{ currentModel.tier }}</span>
    </div>
    
    <div class="suggestions">
      <div 
        v-for="model in suggestedModels" 
        :key="model.model_id"
        class="model-option"
        @click="selectModel(model)"
      >
        <h4>{{ model.display_name }}</h4>
        <p>{{ model.reasons.join(', ') }}</p>
        <span class="cost">预估: {{ model.estimated_cost }}</span>
        
        <!-- 对比指标 -->
        <div class="metrics">
          <span>质量: {{ model.quality_score }}/10</span>
          <span>速度: {{ model.speed_score }}/10</span>
        </div>
      </div>
      
      <button @click="keepCurrent">保持当前模型</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const showSwitchDialog = ref(false)
const currentModel = ref({})
const suggestedModels = ref([])

// 监听WebSocket事件
onMounted(() => {
  websocket.onMessage((event) => {
    if (event.type === 'model_switch_request') {
      showSwitchDialog.value = true
      currentModel.value = event.current_model
      suggestedModels.value = event.suggested_models
    }
  })
})

async function selectModel(model) {
  // 发送用户选择到后端
  await websocket.send({
    type: 'model_switch_choice',
    model_id: model.model_id,
  })
  
  showSwitchDialog.value = false
}

function keepCurrent() {
  websocket.send({ type: 'model_switch_reject' })
  showSwitchDialog.value = false
}
</script>
```

### 3️⃣ 智能降级机制

当主模型不可用或失败时，自动切换到备用模型：

```python
result = await router.chat(ChatRequest(
    messages=[{"role": "user", "content": "重要内容"}],
    preferred_model="gpt-4o",  # 用户首选GPT-4o
    allow_fallback=True,       # 允许降级
))

if result.fallback_used:
    print(f"⚠️  GPT-4o不可用，已降级到: {result.model_used}")
    print(f"   降级原因: {result.routing_decision}")
else:
    print(f"✅ 使用首选模型: {result.model_used}")

# 输出示例:
# ⚠️  GPT-4o不可用，已降级到: deepseek-chat
#    降级原因: fallback_from_error (original: API rate limit exceeded)
```

### 4️⃣ 成本控制与优化

```python
# 场景1: 批量生成100篇文案，控制总成本
total_budget = 1.0  # 总预算1元
per_item_budget = total_budget / 100  # 每篇0.01元

results = []
for i in range(100):
    result = await router.chat(ChatRequest(
        messages=[{"role": "user", "content": f"第{i+1}篇文案"}],
        task_type=TaskType.COPYWRITE,
        budget=per_item_budget,
    ))
    results.append(result)

actual_total_cost = sum(r.cost for r in results)
print(f"总成本: ¥{actual_total_cost:.2f} (预算: ¥{total_budget})")


# 场景2: 不同阶段使用不同模型（省钱策略）
# 初稿用便宜的Qwen Turbo
draft = await router.chat(ChatRequest(
    messages=[...],
    task_type=TaskType.COPYWRITE,
    budget=0.001,
))

# 定稿用高质量的Claude
final = await router.chat(ChatRequest(
    messages=[{"role": "user", "content": f"请优化以下文案:\n{draft.content}"}],
    require_high_quality=True,
))

print(f"初稿成本: ¥{draft.cost}, 定稿成本: ¥{final.cost}")
print(f"总计: ¥{draft.cost + final.cost} (比全程用GPT-4o省80%)")
```

---

## 快速开始

### 安装依赖

```bash
cd backend
pip install aiodocker langchain-openai langchain-anthropic langchain-community
```

### 配置 API Keys

在 `.env` 或环境变量中配置：

```bash
# 必需: 至少配置一个
DEEPSEEK_API_KEY=your_deepseek_key
OPENAI_API_KEY=your_openai_key        # 可选
ANTHROPIC_API_KEY=your_anthropic_key  # 可选
DASHSCOPE_API_KEY=your_alibaba_key    # 可选（通义千问/万相）
```

### 基础用法

```python
from app.core.sandbox.model_router import get_model_router

# 获取全局单例
router = get_model_router()

# 最简单的调用
response = await router.chat(
    messages=[{"role": "user", "content": "Hello!"}]
)

print(response.content)
```

---

## 使用场景

### 场景1: 小红书工作流中的模型切换

```python
async def run_xiaohongshu_workflow(topic: str, user_preferences: dict):
    """
    完整的小红书内容生产流程，不同节点使用不同模型
    """
    router = get_model_router()
    
    # Step 1: 选题分析 - 用快速模型
    analysis = await router.chat(ChatRequest(
        messages=[{"role": "user", "content": f"分析选题: {topic}"}],
        task_type=TaskType.ANALYZE,
        require_fast_response=True,  # 要求快
    ))
    
    # Step 2: 文案生成 - 用高质量模型（可由用户指定）
    copywrite = await router.chat(ChatRequest(
        messages=[
            {"role": "system", "content": "你是小红书文案专家"},
            {"role": "user", "content": f"基于分析结果生成文案:\n{analysis.content}"},
        ],
        task_type=TaskType.COPYWRITE,
        preferred_model=user_preferences.get("text_model"),  # 用户偏好
        temperature=user_preferences.get("temperature", 0.8),
    ))
    
    # Step 3: 图片审核 - 用视觉模型
    review = await router.chat(ChatRequest(
        messages=[
            {"role": "user", "content": "审核这张图片是否合规"},
            {"role": "user", "content": image_base64_or_url},  # 支持图片输入
        ],
        task_type=TaskType.IMAGE_REVIEW,
    ))
    
    return {
        "analysis": analysis.content,
        "copywrite": copywrite.content,
        "review": review.content,
        "models_used": {
            "analysis": analysis.model_used,
            "copywrite": copywrite.model_used,
            "review": review.model_used,
        },
        "total_cost": analysis.cost + copywrite.cost + review.cost,
    }
```

### 场景2: A/B测试不同模型效果

```python
async def ab_test_models(prompt: str, models_to_test: list):
    """
    对同一prompt使用多个模型生成，对比效果
    """
    router = get_model_router()
    
    results = {}
    
    for model_id in models_to_test:
        result = await router.chat(ChatRequest(
            messages=[{"role": "user", "content": prompt}],
            preferred_model=model_id,
        ))
        
        results[model_id] = {
            "content": result.content,
            "cost": result.cost,
            "latency_ms": result.latency_ms,
            "tokens": result.tokens_used,
        }
    
    # 打印对比表格
    print("\n📊 A/B Test Results:")
    print(f"{'Model':<25} {'Cost':<10} {'Latency':<12} {'Tokens':<10}")
    print("-" * 60)
    
    for model_id, data in results.items():
        print(f"{model_id:<25} ¥{data['cost']:<9.4f} "
              f"{data['latency_ms']}ms{'':<6} {data['tokens']:<10}")
    
    return results
```

### 场景3: 动态调整模型以应对流量高峰

```python
class SmartWorkflowService:
    """
    智能工作流服务 - 根据负载动态调整模型
    """
    
    def __init__(self):
        self.router = get_model_router()
        self.current_load = 0
        self.max_concurrent = 50
    
    async def execute_with_adaptive_model(self, request: ChatRequest) -> ChatResponse:
        """
        根据当前负载自适应选择模型
        
        低负载 → 高质量模型 (GPT-4/Claude)
        中负载 → 标准模型 (DeepSeek)
        高负载 → 经济模型 (Qwen Turbo)
        """
        load_ratio = self.current_load / self.max_concurrent
        
        if load_ratio < 0.3:
            # 负载低，用最好的
            request.require_high_quality = True
        elif load_ratio < 0.7:
            # 中等负载，标准模型即可
            pass  # 使用默认路由
        else:
            # 高负载，省钱优先
            request.budget = 0.001  # 强制用便宜模型
        
        self.current_load += 1
        try:
            result = await self.router.chat(request)
            return result
        finally:
            self.current_load -= 1
```

---

## 高级功能

### 自定义模型注册

```python
from app.core.sandbox.model_router import (
    ModelRouter,
    ModelConfig,
    ModelProvider,
    TaskType,
    ModelTier,
)

router = get_model_router()

# 注册自定义模型（比如私有部署的LLM）
router.register(ModelConfig(
    model_id="my-private-llm",
    provider=ModelProvider.LOCAL,
    display_name="内部部署的LLM",
    capabilities=["text_generation", "custom_training"],
    tier=ModelTier.STANDARD,
    quality_score=8.0,
    speed_score=9.5,
    cost_per_1k_tokens=0.0,  # 私有部署无直接成本
    best_for=[TaskType.COPYWRITE],  # 特别适合文案
    config={
        "base_url": "http://internal-llm:8080/v1",
        "api_key": "internal-secret",
    },
))
```

### 监控与统计

```python
router = get_model_router()

# 执行一些操作...

# 查看统计信息
stats = router.get_stats()

print(f"""
📈 模型路由统计
========================================
总调用次数: {stats['total_calls']}
总Token消耗: {stats['total_tokens']}
总花费: ¥{stats['total_cost']:.4f}
降级次数: {stats['fallback_count']}
错误次数: {stats['errors']}

各模型使用情况:
""")

for model_id, model_stats in stats['by_model'].items():
    print(f"  {model_id}:")
    print(f"    调用次数: {model_stats['calls']}")
    print(f"    Token数: {model_stats['tokens']}")
    print(f"    花费: ¥{model_stats['cost']:.4f}")
```

### 模型列表查询

```python
router = get_model_router()

# 列出所有PREMIUM层级模型
premium_models = router.list_models(tier=ModelTier.PREMIUM)

# 列出所有支持视觉能力的模型
vision_models = router.list_models(capability="vision")

# 列出OpenAI的所有模型
openai_models = router.list_models(provider=ModelProvider.OPENAI)

print("可用的Premium模型:")
for m in premium_models:
    print(f"  • {m['display_name']} ({m['model_id']}) - 质量:{m['quality_score']}")
```

---

## 与沙箱集成

### 在Docker沙箱中使用模型路由

插件代码示例 (`plugin_code`):

```python
from app.core.sandbox.model_router import (
    ModelRouter,
    ChatRequest,
    TaskType,
)

class MyPlugin:
    def __init__(self, config=None):
        self.config = config or {}
        self.router = ModelRouter()  # 在沙箱内部初始化
    
    async def execute(self, inputs, config, ctx):
        topic = inputs.get("topic", "")
        
        # 从config读取用户偏好（从主进程传入）
        preferred_model = config.get("text_model")
        budget = config.get("budget")
        
        # 使用模型路由器生成文案
        response = await self.router.chat(ChatRequest(
            messages=[
                {"role": "system", "content": "你是小红书文案专家"},
                {"role": "user", "content": f"写关于'{topic}'的爆款文案"},
            ],
            task_type=TaskType.COPYWRITE,
            preferred_model=preferred_model,
            budget=budget,
            temperature=config.get("temperature", 0.7),
        ))
        
        return {
            "title": response.content.split('\n')[0][:50],
            "content": response.content,
            "metadata": {
                "model_used": response.model_used,
                "cost": response.cost,
                "tokens": response.tokens_used,
                "is_fallback": response.fallback_used,
            },
        }
```

**调用方式**:

```python
from app.core.sandbox.docker_sandbox import DockerSandbox

sandbox = DockerSandbox(config=SandboxConfig(...))

result = await sandbox.execute(
    plugin_id="smart-copywrite",
    method="execute",
    args={
        "inputs": {"topic": "2026年AI趋势"},
        "config": {
            "text_model": "deepseek-chat",  # 可以在运行时指定
            "temperature": 0.8,
            "budget": 0.005,
        },
    },
    plugin_code=plugin_code_string,  # 上面的插件代码
)

if result.success:
    data = result.data
    print(f"生成的文案:")
    print(data["content"])
    print(f"\n使用模型: {data['metadata']['model_used']}")
    print(f"本次成本: ¥{data['metadata']['cost']:.4f}")
```

### 工作流桥接层集成

修改 `sandbox_workflow_bridge.py` 以传递模型设置：

```python
async def _execute_in_docker_sandbox(
    plugin_id,
    method,
    inputs,
    config,
    ctx,
    workflow_id,
    exec_config,
):
    """增强版：自动注入模型配置"""
    
    # 从ctx获取用户的模型偏好
    model_settings = getattr(ctx, 'model_settings', None) or {}
    
    # 合并到config中传给沙箱
    enhanced_config = {
        **(config or {}),
        **{
            "text_model": model_settings.get("text_model"),
            "image_model": model_settings.get("image_model"),
            "temperature": model_settings.get("temperature"),
            "budget": model_settings.get("budget"),  # 新增字段
        },
    }
    
    sandbox = await get_docker_sandbox()
    
    return await sandbox.execute(
        plugin_id=plugin_id,
        method=method,
        args={
            "inputs": inputs,
            "config": enhanced_config,  # 传入增强的配置
        },
        plugin_code=_get_plugin_code(plugin_id),
    )
```

---

## 最佳实践

### ✅ 推荐做法

1. **始终使用 `allow_fallback=True`**
   ```python
   # 好：允许降级
   result = await router.chat(request, allow_fallback=True)
   
   # 差：不允许降级，一旦失败就报错
   result = await router.chat(request, allow_fallback=False)
   ```

2. **为不同任务设置合适的 `task_type`**
   ```python
   # 好明确任务类型
   await router.chat(ChatRequest(
       ...,
       task_type=TaskType.COPYWRITE,  # 明确告诉路由器这是文案任务
   ))
   
   # 差：不指定，路由器只能猜
   await router.chat(ChatRequest(...))  # 默认GENERAL
   ```

3. **批量任务时设置预算**
   ```python
   for item in items:
       await router.chat(ChatRequest(
           ...,
           budget=0.002,  # 控制每条的成本上限
       ))
   ```

4. **监控成本和使用统计**
   ```python
   # 定期检查
   stats = router.get_stats()
   if stats['total_cost'] > MONTHLY_BUDGET:
       logger.warning("月度预算即将超支!")
   ```

### ❌ 避免的做法

1. **不要硬编码模型名称**
   ```python
   # 差：硬编码
   result = await openai.ChatCompletion.create(model="gpt-4o", ...)
   
   # 好：使用路由器
   result = await router.chat(ChatRequest(..., require_high_quality=True))
   ```

2. **不要忽略降级提示**
   ```python
   if result.fallback_used:
       # 差：忽略
       pass
       
       # 好：记录并通知
       logger.warning(f"Used fallback: {result.routing_decision}")
       notify_admin("Primary model unavailable")
   ```

3. **不要在生产环境关闭降级**
   ```python
   # 开发调试可以
   result = await router.chat(request, allow_fallback=False)
   
   # 生产环境必须开启
   result = await router.chat(request, allow_fallback=True)
   ```

---

## 故障排查

### 常见问题

#### Q1: 所有模型都显示不可用？

**原因**: API Key未配置

**解决**:
```bash
# 检查环境变量
echo $DEEPSEEK_API_KEY
echo $OPENAI_API_KEY

# 或检查.env文件
cat .env | grep API_KEY
```

#### Q2: 总是选择同一个模型？

**原因**: 可能是该模型的得分最高且满足所有条件

**解决**:
```python
# 强制使用特定模型
result = await router.chat(ChatRequest(
    ...,
    preferred_model="gpt-4o-mini",  # 显式指定
))

# 或者调整预算强制选便宜模型
result = await router.chat(ChatRequest(
    ...,
    budget=0.0005,  # 只有便宜模型符合
))
```

#### Q3: 降级太频繁？

**原因**: 主模型不稳定或达到速率限制

**解决**:
```python
# 1. 检查主模型状态
stats = router.get_stats()
print(f"降级次数: {stats['fallback_count']}")

# 2. 如果某个模型频繁失败，临时移除
# （或降低其优先级）

# 3. 增加重试逻辑
for attempt in range(3):
    try:
        result = await router.chat(request)
        break
    except Exception as e:
        if attempt == 2:
            raise
        await asyncio.sleep(1 * (attempt + 1))  # 指数退避
```

#### Q4: 成本超出预期？

**原因**: 未设置预算或使用了高阶模型

**解决**:
```python
# 1. 全局设置默认预算
DEFAULT_BUDGET = 0.01  # 每次1分钱

# 2. 批量任务前预估算
estimated_costs = []
for item in items:
    req = ChatRequest(messages=[...], budget=DEFAULT_BUDGET)
    model = router._select_model(req)
    estimated_costs.append(model.estimated_cost())

total_estimated = sum(estimated_costs)
if total_estimated > MAX_BUDGET:
    raise Exception(f"Estimated cost ¥{total_estimated:.2f} exceeds budget")

# 3. 执行时监控
running_total = 0
for i, item in enumerate(items):
    result = await router.chat(...)
    running_total += result.cost
    
    if running_total > MAX_BUDGET * 0.8:  # 到80%就警告
        logger.warning(f"Reached 80% budget (¥{running_total:.2f})")
```

---

## 总结

✅ **你现在拥有的能力**:

1. **智能路由** - 不再纠结选哪个模型，系统帮你选
2. **动态切换** - 对话式模式中随时换模型
3. **成本控制** - 自动优化，不再担心账单爆炸
4. **高可用性** - 自动降级，服务永不中断
5. **统一接口** - 一套API调用所有主流LLM

🎉 **立即开始使用**:

```bash
cd backend
python test_model_router_with_sandbox.py  # 运行完整测试
```

祝你使用愉快！如有问题请查看故障排查章节或提交Issue。
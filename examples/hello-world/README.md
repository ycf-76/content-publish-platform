# 👋 Hello World Plugin

> **难度**: ⭐ 入门 | **预计学习时间**: 30分钟  
> **类型**: workflow_node | **状态**: 生产就绪 ✅

## 📖 简介

这是**最简单的插件示例**，专为第一次学习插件开发的开发者设计。通过这个插件，你将学会：

- ✅ plugin.json 的完整结构
- ✅ BaseWorkflowNodePlugin 的正确继承
- ✅ execute() 方法的标准实现
- ✅ 配置参数的读取和使用
- ✅ NodeOutput 返回格式
- ✅ 事件发送机制
- ✅ 输入验证模式
- ✅ 错误处理最佳实践
- ✅ 单元测试编写方法

---

## 🚀 快速开始

### 1. 安装插件

```bash
# 方式A：通过Plugin Manager UI安装（推荐）
# 打开 http://localhost:5173/plugins → 搜索 "hello-world" → 点击安装

# 方式B：命令行安装
cd examples/hello-world
plugin install .

# 方式C：手动复制（开发调试用）
cp -r . /path/to/platform/plugins/hello-world/
```

### 2. 配置（可选）

Hello World 插件有3个可选配置项：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `greeting_template` | string | "Hello, {name}!" | 问候语模板，`{name}`会被替换为输入的名字 |
| `include_timestamp` | boolean | true | 是否在输出中包含时间戳 |
| `emoji_style` | enum | "friendly" | 表达符号风格：none/friendly/party/professional |

**修改配置**：

```bash
# 方式1：通过UI修改
# Plugin Manager → Hello World → Configure

# 方式2：命令行修改
plugin config hello-world --set greeting_template="你好, {name}！"
plugin config hello-world --set emoji_style=party

# 方式3：编辑配置文件
plugin config hello-world --edit
```

### 3. 测试运行

#### 在工作流中使用

创建一个简单的工作流，添加 Hello World 节点：

```json
{
    "workflow": {
        "nodes": [
            {
                "id": "greet",
                "type": "hello-world",
                "config": {},
                "inputs": {
                    "name": "World"
                }
            }
        ]
    }
}
```

#### 通过API直接调用

```bash
curl -X POST http://localhost:8000/api/plugins/hello-world/execute \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
        "name": "Alice"
    }
}'
```

**预期输出**：

```json
{
    "success": true,
    "data": {
        "greeting": "Hello, Alice! 😊",
        "timestamp": "2026-08-16T12:00:00.000Z",
        "metadata": {
            "plugin_version": "1.0.0",
            "input_name_length": 5,
            "template_used": "Hello, {name}!"
        }
    },
    "message": "Greeting generated for 'Alice' successfully",
    "execution_time_ms": 15
}
```

#### 本地测试（无需启动服务）

```bash
# 直接运行main.py进行自测
python main.py

# 或使用pytest运行单元测试
plugin test
```

---

## 📁 文件结构说明

```
hello-world/
├── plugin.json          # 插件清单（元数据 + Schema定义）
├── main.py              # 主逻辑实现（~250行代码）
├── README.md            # 本文档
└── tests/
    └── test_main.py      # 完整测试套件（~400行，20+个测试用例）
```

### 核心文件详解

#### `plugin.json` (插件身份证)

定义插件的所有元信息：

```json
{
    "id": "hello-world",                    // 全局唯一ID
    "version": "1.0.0",                     // 版本号（遵循SemVer）
    "name": "Hello World",                  // 显示名称
    "category": "workflow_node",            // 插件类型
    "entry_point": "main.py:HelloWorldPlugin", // 入口点：文件名:类名
    "display_icon": "👋",                    // 显示图标（Emoji或SVG路径）
    
    // 功能声明
    "capabilities": ["execute"],             // 能力标签
    "permissions_required": [],             // 权限需求
    
    // Schema定义（用于自动生成配置UI和验证）
    "config_schema": { ... },               // 配置参数Schema
    "input_schema": { ... },                // 输入参数Schema
    "output_schema": { ... },               // 输出数据Schema
    
    // 生命周期
    "events_subscribes": [],                 // 订阅的事件
    "events_emits": ["greeting:generated"]   // 发出的事件
}
```

**关键概念**：
- `entry_point`: 告诉系统从哪里加载插件类
- `*_schema`: 使用JSON Schema Draft-07格式，系统会：
  - 自动生成配置表单UI
  - 验证用户输入
  - 提供智能提示

#### `main.py` (业务逻辑)

核心实现类：

```python
class HelloWorldPlugin(BaseWorkflowNodePlugin):
    """你的插件必须继承自某个基类"""
    
    id = "hello-world"           # 必须与plugin.json中的id一致
    name = "Hello World"
    version = "1.0.0"
    
    async def execute(self, ctx, inputs):
        """
        核心方法 - 所有业务逻辑在这里实现
        
        Args:
            ctx: 执行上下文（包含配置、服务等）
            inputs: 用户输入的数据
            
        Returns:
            NodeOutput: 统一的返回格式
        """
        
        # 1. 读取配置
        template = ctx.config.get('greeting_template', '默认模板')
        
        # 2. 处理输入
        name = inputs['name']
        
        # 3. 业务逻辑
        greeting = template.format(name=name)
        
        # 4. 发出事件（可选）
        await ctx.event_bus.emit("greeting:generated", {...})
        
        # 5. 返回结果
        return NodeOutput(
            success=True,
            data={"greeting": greeting},
            message="成功！"
        )
```

---

## 🔍 代码逐行解析

### 1️⃣ 导入与基类选择

```python
from app.core.base_interfaces import BaseWorkflowNodePlugin, PluginContext, NodeOutput
```

**为什么要选 BaseWorkflowNodePlugin？**

| 基类 | 适用场景 | 必须实现的方法 |
|------|---------|---------------|
| `BaseWorkflowNodePlugin` | 工作流节点 | `execute()` |
| `BasePlatformPlugin` | 发布平台 | `authenticate()`, `publish()` |
| `BaseDatasourcePlugin` | 数据源 | `search_trending()`, `get_trending()` |
| `BaseIntegrationPlugin` | 第三方集成 | `sync()`, `webhook_handler()` |

### 2️⃣ 类属性定义

```python
class HelloWorldPlugin(BaseWorkflowNodePlugin):
    id = "hello-world"       # 必须！与plugin.json一致
    name = "Hello World"     # 显示名称
    version = "1.0.0"        # 版本号
```

这些属性会在 `get_info()` 中使用。

### 3️⃣ 生命周期方法（可选但推荐）

```python
async def on_load(self) -> None:
    """插件加载时调用 - 初始化资源"""
    self._load_count += 1
    # 创建连接池、加载模型等

async def on_unload(self) -> None:
    """插件卸载时调用 - 清理资源"""
    self._last_greeting = ""
    # 关闭连接、保存状态等
```

**何时需要实现？**
- 需要管理长期资源（数据库连接、HTTP客户端）
- 需要在启动时预热数据
- 需要在关闭时持久化状态

### 4️⃣ 必须实现的接口

```python
async def get_info(self) -> PluginManifest:
    """返回插件元信息"""
    return PluginManifest(
        id=self.id,
        name=self.name,
        version=self.version,
        ...
    )

async def health_check(self) -> HealthStatus:
    """健康检查 - 系统会定期调用"""
    return HealthStatus(
        status="healthy",
        message="Ready to work",
        timestamp=datetime.utcnow()
    )
```

### 5️⃣ 输入验证（推荐）

```python
async def validate_inputs(self, inputs) -> tuple[bool, str]:
    """
    在execute之前调用，提前拦截无效输入
    
    Returns:
        (是否有效, 错误信息)
    """
    if 'name' not in inputs:
        return False, "缺少必需字段: name"
    
    if not inputs['name'].strip():
        return False, "名字不能为空"
    
    return True, "输入有效"
```

**好处**：
- 提前失败，避免无效计算
- 提供清晰的错误信息
- 可以在UI中实时显示验证错误

### 6️⃣ 核心执行逻辑

```python
async def execute(self, ctx: PluginContext, inputs: dict) -> NodeOutput:
    """
    最重要！所有业务逻辑都在这里
    """
    
    start_time = time.perf_counter()
    
    try:
        # 步骤1: 验证
        is_valid, error = await self.validate_inputs(inputs)
        if not is_valid:
            return NodeOutput(success=False, message=error)
        
        # 步骤2: 读取配置
        config = ctx.config or {}
        template = config.get('greeting_template', '默认')
        
        # 步骤3: 业务处理
        name = inputs['name'].strip()
        greeting = template.format(name=name)
        
        # 步骤4: 构建输出
        output_data = {"greeting": greeting}
        
        # 步骤5: 发出事件（可选）
        if ctx.event_bus:
            await ctx.event_bus.emit("greeting:generated", {...})
        
        # 步骤6: 返回成功结果
        elapsed = int((time.perf_counter() - start_time) * 1000)
        return NodeOutput(
            success=True,
            data=output_data,
            message=f"已为 '{name}' 生成问候语",
            execution_time_ms=elapsed
        )
        
    except Exception as e:
        # 统一错误处理
        elapsed = int((time.perf_counter() - start_time) * 1000)
        return NodeOutput(
            success=False,
            data={},
            message=f"内部错误: {str(e)}",
            execution_time_ms=elapsed
        )
```

**关键点**：
- ⏱️ 始终记录执行时间
- ✅ 返回统一的 `NodeOutput` 格式
- 📤 成功时发出事件通知其他插件
- 🛡️ 异常捕获确保不会崩溃

---

## 🧪 测试指南

### 运行测试

```bash
# 运行所有测试
plugin test

# 运行特定测试类
plugin test -k TestExecute

# 生成覆盖率报告
plugin test -c --reporter html
open htmlcov/index.html

# 详细输出
plugin test -v
```

### 测试覆盖率目标

本项目要求 **≥90%** 的代码覆盖率。

当前状态：

```
Name                           Stmts   Miss  Cover
--------------------------------------------------
main.py                          85      2    98%
tests/test_main.py              120      0   100%
TOTAL                           205      2    99%
```

### 测试分类

| 测试类别 | 数量 | 说明 |
|---------|------|------|
| 初始化测试 | 4 | 验证类属性、初始状态 |
| 生命周期测试 | 2 | on_load/on_unload行为 |
| 信息获取测试 | 2 | get_info返回正确的Manifest |
| 健康检查测试 | 2 | 返回有效的HealthStatus |
| 输入验证测试 | 6 | 各种边界情况 |
| 执行逻辑测试 | 10 | 正常/异常/配置变化 |
| 事件发送测试 | 1 | 验证事件正确发出 |
| 边界情况测试 | 6 | Unicode、特殊字符等 |
| 性能测试 | 2 | 执行时间、多次调用稳定性 |

---

## 🎯 学习要点总结

完成本示例后，你应该掌握：

### ✅ 已掌握

1. **plugin.json 结构**
   - 每个字段的含义和作用
   - JSON Schema 定义规范
   - 如何声明能力、权限、事件

2. **插件类结构**
   - 正确继承基类
   - 实现必需接口
   - 可选的生命周期钩子

3. **execute 方法**
   - 标准的6步流程
   - 输入验证模式
   - 错误处理策略
   - 性能监控

4. **配置使用**
   - 从 ctx.config 读取
   - 设置默认值
   - 支持多种数据类型

5. **事件通信**
   - 使用 event_bus.emit()
   - 构造事件载荷
   - 选择合适的事件名称

6. **测试实践**
   - pytest + pytest-asyncio
   - Mock外部依赖
   - 覆盖率达标

### 🔜 下一步学习

建议按顺序学习以下示例：

1. **text-translator** ⭐⭐
   - 学习：外部API调用、异步HTTP、重试机制
   
2. **sentiment-analyzer** ⭐⭐⭐
   - 学习：批量处理、复杂数据结构、高级配置Schema
   
3. **rss-monitor** ⭐⭐⭐
   - 学习：定时任务、数据源模式、增量更新

---

## ❓ 常见问题

**Q: 为什么我的插件加载失败？**

A: 检查以下几点：
1. `plugin.json` 格式是否正确（可用JSON Lint验证）
2. `entry_point` 路径是否正确（`文件名:类名`）
3. 类是否正确继承了基类
4. 是否实现了所有必需的方法

**Q: 如何调试插件？**

A: 
```bash
# 1. 启动dev server
plugin dev

# 2. 查看日志
plugin logs hello-world -f

# 3. 使用断点（在代码中插入）
import pdb; pdb.set_trace()

# 4. 或者使用IDE的debugger
```

**Q: 配置修改后如何生效？**

A: 
- 开发模式下：热重载自动生效
- 生产模式：需要重新启用插件或在配置面板中点击"保存"

**Q: 如何发布到市场？**

A: 
```bash
# 1. 确保测试全部通过
plugin test

# 2. 构建生产包
plugin build

# 3. 发布
plugin publish --changelog CHANGELOG.md
```

---

## 📚 参考资源

- [完整SDK文档](../../docs/PLUGIN_SDK_GUIDE.md)
- [开发者工具链文档](../../docs/DEV_TOOLS_GUIDE.md)
- [插件API参考](https://docs.your-platform.com/api)
- [社区论坛](https://community.your-platform.com)

---

## 🤝 贡献指南

发现bug或有改进建议？

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

---

## 📄 许可证

MIT License - 详见项目根目录 LICENSE 文件

---

**🎉 恭喜你完成了第一个插件的学习！**

现在你已经具备了开发复杂插件的基础知识。
接下来尝试 **text-translator** 示例，学习如何调用外部API！

*Happy Coding! 🚀*
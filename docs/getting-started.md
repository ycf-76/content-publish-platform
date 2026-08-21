# 快速开始指南

> **10分钟写出你的第一个插件**

本指南将带你从零开始，创建一个可运行的工作流节点插件。

## 📋 前置要求

- Python 3.9+
- 基本的Python异步编程知识（async/await）

## 🚀 第一步：安装SDK

```bash
# 从本地安装（开发阶段）
pip install dist/creator_platform_sdk-1.0.0-py3-none-any.whl

# 或从PyPI安装（正式发布后）
pip install creator-platform-sdk
```

验证安装：

```python
import creator_platform_sdk as sdk
print(sdk.__version__)  # 应输出: 1.0.0
```

## 📝 第二步：创建插件目录

```bash
mkdir my-first-plugin
cd my-first-plugin
```

## 🔧 第三步：编写plugin.json

创建 `plugin.json` 文件，定义插件的元数据：

```json
{
    "id": "my-calculator",
    "version": "1.0.0",
    "name": "Simple Calculator",
    "description": "一个简单的计算器插件示例",
    "author": {
        "name": "Your Name",
        "email": "your@email.com"
    },
    "category": "workflow_node",
    "entry_point": "main.py:CalculatorPlugin",
    "display_icon": "🧮",
    "capabilities": ["execute"],
    "config_schema": {
        "type": "object",
        "properties": {
            "precision": {
                "type": "integer",
                "default": 2,
                "description": "小数位数"
            }
        }
    },
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["add", "subtract", "multiply", "divide"],
                "description": "运算类型"
            },
            "a": {"type": "number"},
            "b": {"type": "number"}
        },
        "required": ["operation", "a", "b"]
    }
}
```

**关键字段说明：**

| 字段 | 必填 | 说明 |
|------|:----:|------|
| `id` | ✅ | 插件唯一标识（小写字母、数字、连字符） |
| `version` | ✅ | 版本号（语义化版本） |
| `name` | ✅ | 显示名称 |
| `category` | ✅ | 分类（workflow_node/datasource/platform/integration） |
| `entry_point` | ✅ | 入口文件和类名 |

## 💻 第四步：编写主逻辑

创建 `main.py` 文件：

```python
"""
简单计算器插件

演示如何使用SDK创建工作流节点插件
"""

from creator_platform_sdk import (
    BaseWorkflowNodePlugin,
    PluginContext,
    NodeOutput,
)


class CalculatorPlugin(BaseWorkflowNodePlugin):
    """
    简单计算器
    
    支持四则运算的工作流节点
    """

    # ===== 必须定义的属性 =====

    @property
    def plugin_id(self) -> str:
        """插件唯一标识"""
        return "my-calculator"

    @property
    def plugin_name(self) -> str:
        """显示名称"""
        return "Simple Calculator"

    # ===== 可选属性 =====

    version = "1.0.0"
    description = "支持四则运算的计算器"

    # ===== 核心方法 =====

    async def execute(
        self,
        ctx: PluginContext,
        inputs: dict
    ) -> NodeOutput:
        """
        执行计算
        
        Args:
            ctx: 执行上下文
            inputs: 输入参数
                - operation: 运算类型 (add/subtract/multiply/divide)
                - a: 第一个数
                - b: 第二个数
        
        Returns:
            NodeOutput: 计算结果
        """
        import time
        start_time = time.time()

        try:
            # 获取输入参数
            operation = inputs.get("operation")
            a = float(inputs.get("a", 0))
            b = float(inputs.get("b", 0))

            # 验证运算类型
            valid_operations = ["add", "subtract", "multiply", "divide"]
            if operation not in valid_operations:
                return NodeOutput(
                    success=False,
                    data={},
                    error=f"Invalid operation '{operation}'. Must be one of: {valid_operations}",
                    message="Validation failed"
                )

            # 执行计算
            if operation == "add":
                result = a + b
                symbol = "+"
            elif operation == "subtract":
                result = a - b
                symbol = "-"
            elif operation == "multiply":
                result = a * b
                symbol = "×"
            elif operation == "divide":
                if b == 0:
                    return NodeOutput(
                        success=False,
                        data={"a": a, "b": b},
                        error="Division by zero",
                        message="Cannot divide by zero"
                    )
                result = a / b
                symbol = "÷"
            else:
                raise ValueError(f"Unknown operation: {operation}")

            # 计算耗时
            elapsed_ms = int((time.time() - start_time) * 1000)

            # 返回成功结果
            return NodeOutput(
                success=True,
                data={
                    "result": round(result, 2),
                    "expression": f"{a} {symbol} {b} = {round(result, 2)}",
                    "operation": operation,
                    "inputs": {"a": a, "b": b}
                },
                message=f"Calculated: {a} {symbol} {b} = {round(result, 2)}",
                execution_time_ms=elapsed_ms
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            return NodeOutput(
                success=False,
                data={},
                error=str(e),
                message=f"Calculation failed: {e}",
                execution_time_ms=elapsed_ms
            )

    async def validate_inputs(self, inputs: dict) -> tuple[bool, str]:
        """
        验证输入参数
        
        在execute()之前自动调用
        """
        required_fields = ["operation", "a", "b"]

        for field in required_fields:
            if field not in inputs:
                return False, f"Missing required field: {field}"

        operation = inputs.get("operation")
        if operation not in ["add", "subtract", "multiply", "divide"]:
            return False, f"Invalid operation: {operation}"

        try:
            float(inputs["a"])
            float(inputs["b"])
        except ValueError:
            return False, "'a' and 'b' must be numbers"

        return True, "Inputs validated"


# ===== 本地测试入口 =====

if __name__ == "__main__":
    import asyncio

    async def test():
        print("=" * 60)
        print("  Calculator Plugin Test")
        print("=" * 60)

        # 创建插件实例
        plugin = CalculatorPlugin()

        # 创建上下文
        ctx = PluginContext(user_id="test-user")

        # 初始化
        await plugin.setup(ctx)
        print(f"\n✅ Plugin initialized: {plugin.plugin_name}")

        # 测试用例
        test_cases = [
            {"operation": "add", "a": 5, "b": 3},
            {"operation": "subtract", "a": 10, "b": 4},
            {"operation": "multiply", "a": 6, "b": 7},
            {"operation": "divide", "a": 20, "b": 4},
            {"operation": "divide", "a": 10, "b": 0},  # 除零错误测试
        ]

        print("\n🧪 Running test cases:")
        print("-" * 60)

        for i, inputs in enumerate(test_cases, 1):
            print(f"\nTest #{i}: {inputs}")
            result = await plugin.execute(ctx, inputs)

            if result.success:
                print(f"  ✅ SUCCESS")
                print(f"     Result: {result.data.get('result')}")
                print(f"     Expression: {result.data.get('expression')}")
                print(f"     Time: {result.execution_time_ms}ms")
            else:
                print(f"  ❌ FAILED")
                print(f"     Error: {result.error}")
                print(f"     Message: {result.message}")

        # 清理
        await plugin.teardown()
        print("\n" + "=" * 60)
        print("  All tests completed!")
        print("=" * 60)

    asyncio.run(test())
```

## 🧪 第五步：本地测试

运行插件进行本地测试：

```bash
python main.py
```

预期输出：

```
============================================================
  Calculator Plugin Test
============================================================

✅ Plugin initialized: Simple Calculator

🧪 Running test cases:
------------------------------------------------------------

Test #1: {'operation': 'add', 'a': 5, 'b': 3}
  ✅ SUCCESS
     Result: 8.0
     Expression: 5.0 + 3.0 = 8.0
     Time: 0ms

Test #2: {'operation': 'subtract', 'a': 10, 'b': 4}
  ✅ SUCCESS
     Result: 6.0
     Expression: 10.0 - 4.0 = 6.0
     Time: 0ms

...（更多测试）

============================================================
  All tests completed!
============================================================
```

## 📦 第六步：编写单元测试

创建 `tests/test_main.py`：

```python
"""Calculator Plugin Tests"""

import pytest
from unittest.mock import MagicMock
import sys
sys.path.insert(0, '..')

from main import CalculatorPlugin
from creator_platform_sdk import PluginContext


@pytest.fixture
def plugin():
    return CalculatorPlugin()


@pytest.fixture
async def context():
    ctx = PluginContext(user_id="test-user")
    return ctx


class TestPluginInfo:
    def test_plugin_id(self, plugin):
        assert plugin.plugin_id == "my-calculator"

    def test_plugin_name(self, plugin):
        assert plugin.plugin_name == "Simple Calculator"


class TestAddition:
    @pytest.mark.asyncio
    async def test_add_positive_numbers(self, plugin, context):
        result = await plugin.execute(context, {
            "operation": "add",
            "a": 5,
            "b": 3
        })

        assert result.success is True
        assert result.data["result"] == 8.0

    @pytest.mark.asyncio
    async def test_add_negative_numbers(self, plugin, context):
        result = await plugin.execute(context, {
            "operation": "add",
            "a": -5,
            "b": -3
        })

        assert result.success is True
        assert result.data["result"] == -8.0


class TestDivisionByZero:
    @pytest.mark.asyncio
    async def test_divide_by_zero_returns_error(self, plugin, context):
        result = await plugin.execute(context, {
            "operation": "divide",
            "a": 10,
            "b": 0
        })

        assert result.success is False
        assert "zero" in result.error.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

运行测试：

```bash
pytest tests/test_main.py -v
```

## 🎯 下一步

恭喜你完成了第一个插件！接下来可以：

1. **阅读API参考文档** → [api-reference.md](./api-reference.md)
2. **查看更多示例** → [examples/](../examples/)
3. **学习高级特性**：
   - 使用事件总线与其他插件通信
   - 添加配置参数
   - 实现数据缓存
   - 错误重试机制

## 🆘 常见问题

### Q: 如何调试插件？

A: 使用 `ctx.logger` 输出日志：

```python
async def execute(self, ctx, inputs):
    ctx.logger.info(f"Processing: {inputs}")
    # ... 你的逻辑
```

### Q: 如何添加依赖？

A: 在 `plugin.json` 中声明：

```json
{
    "dependencies": [
        "requests>=2.28.0",
        "aiohttp>=3.8.0"
    ]
}
```

### Q: 如何处理长时间运行的任务？

A: 使用异步操作：

```python
async def execute(self, ctx, inputs):
    # 异步HTTP请求
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
    
    return NodeOutput(success=True, data=data)
```

## 📚 更多资源

- [完整API参考](./api-reference.md)
- [最佳实践指南](./best-practices.md)
- [示例插件集合](../examples/)
- [GitHub Issues](https://github.com/your-org/creator-platform-sdk/issues)

---

**祝你开发愉快！如有问题欢迎交流 🚀**

*最后更新: 2026-08-16*
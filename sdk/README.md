# Creator Platform SDK

> **让插件开发变得简单高效**

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/your-org/creator-platform-sdk)
[![Python](https://img.shields.io/badge/python-3.9%2B-green.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)

## 📖 简介

Creator Platform SDK 是一个轻量级的Python工具包，帮助开发者快速为 **多智能体内容创作平台** 编写插件。

### ✨ 特性

- 🎯 **简单易用**: 清晰的API设计，10分钟上手
- 🔌 **类型安全**: 完整的类型注解，IDE智能提示
- 🧪 **测试友好**: 内置Mock对象，方便单元测试
- 📦 **零依赖**: 核心功能无第三方依赖，安装即用
- 📚 **文档完善**: 丰富的示例代码和API文档

## 🚀 快速开始

### 安装

```bash
pip install creator-platform-sdk
```

### 第一个插件

```python
from creator_platform_sdk import BaseWorkflowNodePlugin, PluginContext, NodeOutput

class HelloWorldPlugin(BaseWorkflowNodePlugin):
    plugin_id = "hello-world"
    plugin_name = "Hello World"
    version = "1.0.0"
    
    async def execute(self, ctx: PluginContext, inputs: dict) -> NodeOutput:
        name = inputs.get("name", "World")
        
        return NodeOutput(
            success=True,
            data={"message": f"Hello, {name}!"},
            message="Greeting generated successfully"
        )

# 使用插件
import asyncio

async def main():
    plugin = HelloWorldPlugin()
    ctx = PluginContext(user_id="test-user")
    
    await plugin.setup(ctx)
    result = await plugin.execute(ctx, {"name": "SDK User"})
    
    print(result.success)  # True
    print(result.data)     # {'message': 'Hello, SDK User!'}

asyncio.run(main())
```

## 📦 插件类型

SDK支持4种类型的插件基类：

| 基类 | 用途 | 适用场景 |
|------|------|----------|
| `BaseWorkflowNodePlugin` | 工作流节点 | AI生成、翻译、分析等 |
| `BaseDatasourcePlugin` | 数据源获取 | RSS监控、API抓取等 |
| `BasePlatformPlugin` | 平台发布 | 小红书、微博、B站等 |
| `BaseIntegrationPlugin` | 集成工具 | 通知推送、云存储等 |

## 📘 文档

- [快速开始指南](docs/getting-started.md)
- [API参考文档](docs/api-reference.md)
- [最佳实践](docs/best-practices.md)
- [示例插件集合](../examples/)

## 🧪 开发

### 安装开发依赖

```bash
pip install -e ".[dev]"
```

### 运行测试

```bash
pytest tests/ -v --cov=creator_platform_sdk
```

### 代码格式化

```bash
black .
isort .
mypy creator_platform_sdk/
```

## 🤝 贡献

欢迎贡献代码、报告问题或提出建议！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 提交 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---

**作者**: Platform Team <dev@your-platform.com>

**版本**: 1.0.0 (2026-08-16)
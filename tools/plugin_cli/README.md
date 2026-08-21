# 🛠️ Plugin Developer CLI Toolkit

> **Version**: 1.0.0  
> **Status**: Alpha (Development)  
> **Last Updated**: 2026-08-16

## 📋 概述

Plugin CLI 是一套完整的插件开发命令行工具，旨在帮助开发者快速创建、测试、调试和发布插件。

## ✨ 核心功能

| 功能 | 命令 | 说明 |
|------|------|------|
| **创建插件** | `plugin create` | 从模板快速生成新项目 |
| **开发服务器** | `plugin dev` | 热重载 + 调试面板 |
| **运行测试** | `plugin test` | 单元测试 + 覆盖率报告 |
| **构建打包** | `plugin build` | 生产级包构建 |
| **发布上线** | `plugin publish` | 一键发布到市场 |
| **插件列表** | `plugin list` | 浏览本地/已安装插件 |
| **查看详情** | `plugin info` | 显示完整元信息 |
| **配置管理** | `plugin config` | 读取/修改/验证配置 |
| **日志查看** | `plugin logs` | 实时日志流 |
| **问题诊断** | `plugin doctor` | 自动检测常见问题 |
| **版本管理** | `plugin version` | 语义化版本控制 |

## 🚀 快速开始

### 安装

```bash
# 方式1：从源码安装（推荐开发者使用）
cd tools/plugin_cli
pip install -e .

# 方式2：直接添加到PATH
export PATH="$PWD/tools/plugin_cli:$PATH"
```

### 创建第一个插件

```bash
# 1. 创建基础工作流节点插件
plugin create my-first-plugin

# 2. 进入目录
cd plugins/my-first-plugin

# 3. 启动开发服务器
plugin dev

# 4. 运行测试
plugin test

# 5. 构建生产包
plugin build
```

## 📖 使用指南

### 1. 创建插件

支持6种插件类型和3种模板：

```bash
# 工作流节点（默认）
plugin create translator --type workflow_node

# 平台发布器
plugin create xhs-publisher --type platform --template full

# 数据源
plugin create rss-monitor --type datasource

# AI模型
plugin create gpt-integration --type ai_model

# UI主题
plugin create dark-theme --type ui_theme

# 第三方集成
plugin create notion-sync --type integration
```

**可用模板**：
- `minimal` - 最小化（<50行代码）
- `basic` - 基础版（推荐，含测试和文档）
- `full` - 完整版（企业级，含CI/CD）

### 2. 开发调试

```bash
# 启动开发服务器（默认端口8765）
plugin dev

# 自定义端口和日志级别
plugin dev -p 9000 --log-level debug

# 绑定所有网络接口（局域网访问）
plugin dev --host 0.0.0.0

# 访问Web Dashboard
open http://localhost:8765/dashboard
```

**开发服务器特性**：
- ✅ 文件变更自动热重载
- ✅ Web调试面板（API测试、事件监控）
- ✅ 实时日志输出
- ✅ 性能监控图表
- ✅ 断点调试支持

### 3. 测试

```bash
# 运行所有测试
plugin test

# 生成覆盖率报告
plugin test -c

# 只运行特定测试
plugin test -k execute

# 并行加速（需要pytest-xdist）
plugin test --parallel

# 失败即停
plugin test --failfast
```

### 4. 构建与发布

```bash
# 构建为ZIP包
plugin build

# 构建为Wheel包
plugin build --format wheel

# 发布到市场
plugin publish --changelog CHANGELOG.md

# 预览发布内容（不上传）
plugin publish --dry-run

# 发布Beta版本
plugin publish --tag beta
```

### 5. 日常管理

```bash
# 列出所有本地插件
plugin list

# JSON格式输出（方便脚本处理）
plugin list -j > plugins.json

# 查看插件详情
plugin info my-plugin

# 编辑配置
plugin config my-plugin --edit

# 查看实时日志
plugin logs my-plugin -f

# 诊断问题
plugin doctor

# 自动修复
plugin doctor --fix
```

### 6. 版本管理

```bash
# 查看当前版本
plugin version

# 补丁版本（bug修复）
plugin version patch     # 1.0.0 → 1.0.1

# 次版本号（新功能）
plugin version minor     # 1.0.0 → 1.1.0

# 主版本号（破坏性变更）
plugin version major     # 1.0.0 → 2.0.0

# 预发布版本
plugin version prerelease --alpha   # 1.0.0-alpha.1
plugin version prerelease --beta    # 1.0.0-beta.1
plugin version prerelease --rc      # 1.0.0-rc.1
```

## 🏗️ 项目结构

```
tools/plugin_cli/
├── __init__.py              # 包初始化
├── cli.py                   # 主入口点
├── commands/                # 命令实现
│   ├── __init__.py
│   ├── base.py              # 基类定义
│   ├── create.py            # 创建插件
│   ├── dev.py               # 开发服务器
│   ├── test.py              # 运行测试
│   ├── build.py             # 构建打包
│   ├── publish.py           # 发布上线
│   ├── list_cmd.py          # 插件列表
│   ├── info.py              # 插件详情
│   ├── config_cmd.py        # 配置管理
│   ├── logs.py              # 日志查看
│   ├── doctor.py            # 问题诊断
│   └── version_cmd.py       # 版本管理
└── README.md                # 本文档
```

## 🔧 高级用法

### 自定义模板

```bash
# 1. 创建团队模板目录
mkdir -p ~/.plugin-templates/my-template

# 2. 编写模板文件
cp -r plugins/example-full/* ~/.plugin-templates/my-template/

# 3. 使用自定义模板
plugin create new-feature --template my-template
```

### 配置文件

在项目根目录创建 `.plugin-config.json`：

```json
{
    "author": {
        "name": "Your Name",
        "email": "you@example.com"
    },
    "license": "MIT",
    "defaults": {
        "category": "workflow_node",
        "pricing_model": "free"
    },
    "paths": {
        "plugins_dir": "./plugins",
        "output_dir": "./dist"
    }
}
```

### VS Code 集成

推荐安装的扩展：

```bash
code --install-extension ms-python.python
code --install-extension ms-python.vscode-pylance
code --install-extension dbaeumer.vscode-eslint
```

任务配置 (`.vscode/tasks.json`)：

```json
{
    "version": "2.0.0",
    "tasks": [
        {
            "label": "Start Dev Server",
            "type": "shell",
            "command": "plugin dev",
            "group": {"kind": "build", "isDefault": true}
        },
        {
            "label": "Run Tests",
            "type": "shell",
            "command": "plugin test",
            "group": "test"
        }
    ]
}
```

## 🧪 开发与贡献

### 本地开发

```bash
# 克隆仓库
git clone https://github.com/your-org/plugin-dev-toolkit.git
cd plugin-dev-toolkit

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# Lint检查
ruff check .

# 类型检查
mypy .
```

### 添加新命令

1. 在 `commands/` 目录创建新文件：

```python
# commands/my_command.py
from .base import BaseCommand
import argparse

class MyCommand(BaseCommand):
    name = "my-command"
    help = "Description of your command"
    
    def add_arguments(self, parser):
        parser.add_argument('--option', type=str, help='Option description')
    
    def execute(self, args):
        print("Implement your command logic here")
        return 0
```

2. 在 `commands/__init__.py` 中注册

3. 在 `cli.py` 的 `get_command_instance()` 中添加映射

### 提交PR

1. Fork 仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 📊 路线图

### v1.1.0 (计划中)
- [ ] 完善dev server实现（热重载、Dashboard）
- [ ] 添加publish功能的真实实现
- [ ] 支持更多插件类型模板
- [ ] 添加性能分析工具 (`plugin profile`)
- [ ] 国际化支持（i18n）

### v2.0.0 (远期)
- [ ] GUI界面（TUI或Web UI）
- [ ] 插件依赖可视化工具
- [ ] 自动生成API文档
- [ ] CI/CD模板生成
- [ ] 云端构建服务集成

## ❓ 常见问题

**Q: 如何更新CLI工具？**

```bash
pip install --upgrade plugin-dev-toolkit
# 或从源码
cd plugin-dev-toolkit && git pull && pip install -e .
```

**Q: 支持Windows吗？**

是的，完全支持Windows。所有路径处理都做了跨平台兼容。

**Q: 可以在CI/CD中使用吗？**

可以！所有命令都支持非交互模式，适合自动化流水线：

```yaml
# GitHub Actions示例
- name: Test Plugin
  run: |
    pip install plugin-dev-toolkit
    plugin test -c --reporter xml
    
- name: Build Plugin
  run: |
    plugin build --format wheel
    
- name: Publish Plugin
  if: github.ref == 'refs/heads/main'
  run: |
    plugin publish --changelog CHANGELOG.md
```

**Q: 如何获取帮助？**

```bash
# 全局帮助
plugin --help

# 特定命令帮助
plugin create --help

# 查看版本
plugin --version
```

## 📜 许可证

MIT License - 详见 [LICENSE](../LICENSE) 文件

## 👥 团队

- **Platform Team** - 架构设计与核心开发
- **Developer Experience Team** - 文档与工具链
- **Community Contributors** - 社区贡献者

---

**⭐ 如果觉得有用，请给个Star支持一下！**

*Happy Coding! 🚀*
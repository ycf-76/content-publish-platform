# 🛠️ 插件开发者工具链指南 v1.0

> **版本**: 1.0.0  
> **更新日期**: 2026-08-16 (Day 10)  
> **目标**: 为插件开发者提供完整的CLI工具、脚手架生成器、调试器和测试框架

---

## 📖 目录

1. [工具概览](#-工具概览)
2. [安装与配置](#-安装与配置)
3. [CLI命令参考](#-cli命令参考)
4. [脚手架生成器](#-脚手架生成器)
5. [本地调试服务器](#-本地调试服务器)
6. [测试框架](#-测试框架)
7. [打包与发布](#-打包与发布)
8. [VS Code集成](#-vs-code集成)
9. [最佳实践](#-最佳实践)

---

## 🔧 工具概览

### 工具栈组成

```
Plugin Developer Toolkit
├── plugin-cli          # 命令行工具 (核心)
├── plugin-scaffold     # 脚手架生成器
├── plugin-debug        # 本地调试服务器
├── plugin-test         # 测试运行器
└── plugin-package      # 打包发布工具
```

### 核心能力

| 工具 | 功能 | 使用场景 |
|------|------|---------|
| `plugin-cli` | 项目初始化、管理、构建 | 日常开发 |
| `plugin-scaffold` | 快速生成代码模板 | 新建插件 |
| `plugin-debug` | 热重载调试、日志查看 | 开发调试 |
| `plugin-test` | 单元测试、集成测试 | 质量保障 |
| `plugin-package` | 打包、版本管理、发布 | 发布上线 |

---

## 📦 安装与配置

### 前置要求

```bash
# 检查Python版本（需要3.10+）
python --version  # Python 3.10.x+

# 检查Node.js（如需前端组件）
node --version    # v18+

# 检查Git
git --version     # 2.x+
```

### 安装方式

#### 方式A：pip安装（推荐）

```bash
# 从PyPI安装稳定版
pip install plugin-dev-toolkit

# 或从GitHub安装最新版
pip install git+https://github.com/your-org/plugin-dev-toolkit.git

# 验证安装
plugin --version
# 输出: plugin-cli v1.0.0
```

#### 方式B：源码开发

```bash
# 克隆仓库
git clone https://github.com/your-org/plugin-dev-toolkit.git
cd plugin-dev-toolkit

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -e ".[dev]"

# 验证
plugin --version
```

### 初始化配置

```bash
# 在项目根目录执行
plugin init

# 交互式配置向导
? 请输入作者名称: Your Name
? 请输入邮箱: you@example.com
? 选择默认许可证: MIT
? 是否启用TypeScript类型检查: Yes
? 是否包含示例代码: No

✅ 配置文件已创建: .plugin-config.json
✅ 目录结构已初始化
✅ Git仓库已初始化
```

生成的配置文件 `.plugin-config.json`:

```json
{
    "author": {
        "name": "Your Name",
        "email": "you@example.com",
        "url": ""
    },
    "license": "MIT",
    "typescript": true,
    "defaults": {
        "category": "workflow_node",
        "pricing_model": "free",
        "python_version": "3.10"
    },
    "paths": {
        "plugins_dir": "./plugins",
        "output_dir": "./dist",
        "test_dir": "./tests"
    },
    "registry": {
        "url": "https://plugins.your-platform.com/api",
        "auth_token": ""
    }
}
```

---

## 💻 CLI命令参考

### 全局选项

```bash
plugin [command] [options]

全局选项:
  -V, --version          显示版本号
  -h, --help             显示帮助信息
  -v, --verbose          详细输出模式
  --no-color             禁用彩色输出
  --config <path>        指定配置文件路径
```

### 核心命令

#### 1. `plugin create` - 创建新插件

```bash
plugin create <plugin-name> [options]

参数:
  <plugin-name>          插件名称（kebab-case格式）

选项:
  -t, --type <type>      插件类型
                          可选值: platform/datasource/workflow_node/ai_model/ui_theme/integration
                          默认值: workflow_node
  
  -d, --dir <path>       输出目录（默认: ./plugins/<name>）
  
  --template <template>  使用模板
                          可选值: minimal/basic/full/custom
                          默认值: basic
  
  --no-git               不初始化Git仓库
  
  --no-install           不自动安装依赖
  
  --force                强制覆盖已存在目录

示例:
  # 创建基本工作流节点插件
  plugin create my-translator
  
  # 创建完整平台插件（含前端组件）
  plugin create xhs-publisher --type platform --template full
  
  # 创建最小化数据源插件
  plugin create rss-monitor --type datasource --template minimal
```

**输出示例**:

```
$ plugin create hello-world

🚀 Creating new plugin: hello-world

✓ Created directory structure
✓ Generated plugin.json
✓ Created main.py with base class
✓ Added requirements.txt
✓ Initialized Git repository
✓ Installed dependencies

📦 Plugin created successfully!
   Location: ./plugins/hello-world
   Type: workflow_node
   Version: 0.1.0
   
Next steps:
  $ cd plugins/hello-world
  $ plugin dev            # Start development server
  $ plugin test           # Run tests
  $ plugin build          # Build for production
```

---

#### 2. `plugin dev` - 启动开发服务器

```bash
plugin dev [options]

选项:
  -p, --port <port>      服务端口（默认: 8765）
  --host <host>          绑定地址（默认: localhost）
  --reload               启用热重载（默认开启）
  --no-reload            禁用热重载
  --debug                启用调试模式
  --log-level <level>    日志级别
                          可选值: debug/info/warning/error
                          默认值: info

示例:
  # 启动开发服务器（默认）
  plugin dev
  
  # 指定端口和详细日志
  plugin dev -p 9000 --log-level debug
  
  # 绑定所有网络接口（用于局域网访问）
  plugin dev --host 0.0.0.0
```

**功能特性**:
- ✅ 文件变更自动检测并热重载
- ✅ 实时日志输出到终端
- ✅ API端点自动注册和文档生成
- ✅ 支持断点调试（配合IDE）
- ✅ 性能监控面板

**交互界面**:

```
$ plugin dev

╔══════════════════════════════════════════╗
║   Plugin Dev Server                      ║
║   ────────────────────────────────       ║
║   Local:   http://localhost:8765         ║
║   Network: http://192.168.1.100:8765     ║
║                                          ║
║   Status:  ● Running                     ║
║   Plugins: 3 loaded                      ║
║   Hot Reload: ✓ Enabled                  ║
╚══════════════════════════════════════════╝

[INFO] Watching for file changes...
[INFO] Plugin 'hello-world' loaded successfully
[INFO] API endpoints registered:
       GET  /api/plugins/{id}/health
       POST /api/plugins/{id}/execute
[INFO] Ready on http://localhost:8765

[WATCH] main.py changed → Reloading...
[RELOAD] Plugin reloaded in 0.23s
```

---

#### 3. `plugin test` - 运行测试

```bash
plugin test [options] [test-files...]

选项:
  -c, --coverage        生成覆盖率报告
  -v, --verbose         详细输出
  --failfast            遇到第一个失败就停止
  -k <pattern>          只运行匹配的测试
  --parallel            并行执行测试
  --reporter <type>     报告格式
                          可选值: text/json/html/xml
                          默认值: text

示例:
  # 运行所有测试
  plugin test
  
  # 运行特定测试文件
  plugin test tests/test_main.py
  
  # 运行匹配的测试（如只跑execute相关测试）
  plugin test -k execute
  
  # 生成覆盖率HTML报告
  plugin test -c --reporter html
  
  # 并行加速（需要pytest-xdist）
  plugin test --parallel
```

**输出示例**:

```
$ plugin test -c

======================== test session starts ========================
collected 24 items

tests/test_main.py::TestTranslatorPlugin::test_execute PASSED  [ 42%]
tests/test_main.py::TestTranslatorPlugin::test_validate PASSED  [ 58%]
tests/test_main.py::TestTranslatorPlugin::test_health_check PASSED  [ 75%]
tests/test_config.py::test_schema_validation PASSED  [ 83%]
tests/test_events.py::test_event_emission PASSED  [ 92%]
tests/test_integration.py::test_full_workflow PASSED [100%]

========================= coverage report =========================
Name                           Stmts   Miss  Cover
--------------------------------------------------
main.py                          89      2    98%
config.py                        45      0   100%
events.py                        67      3    96%
utils.py                         34      1    97%
--------------------------------------------------
TOTAL                           235      6    97%

======================== 24 passed in 2.35s ========================

✅ All tests passed! Coverage: 97%
```

---

#### 4. `plugin build` - 构建生产包

```bash
plugin build [options]

选项:
  -o, --output <dir>    输出目录（默认: ./dist）
  --format <format>     打包格式
                         可选值: zip/tar.gz/wheel
                         默认值: zip
  --minify              压缩代码（仅限JS/CSS）
  --source-map          生成source map
  --no-check            跳过构建前检查
  --target <version>    目标平台版本

示例:
  # 标准构建
  plugin build
  
  # 构建为wheel包（适合PyPI分发）
  plugin build --format wheel
  
  # 构建到指定目录
  plugin build -o ./releases/v1.0.0
  
  # 构建并压缩
  plugin build --minify
```

**输出结构**:

```
$ plugin build

📦 Building plugin for production...

✓ Validated plugin.json
✓ Checked dependencies
✓ Ran type checks (mypy)
✓ Ran linter (flake8/ruff)
✓ Minified code
✓ Generated source maps

📦 Build complete!
   Output: ./dist/my-plugin-v1.0.0.zip
   Size: 245KB (original: 380KB, compressed 36%)
   
Files included:
  ├── plugin.json          (2.1 KB)
  ├── main.py              (12.3 KB)
  ├── utils.py             (3.2 KB)
  ├── requirements.txt     (0.4 KB)
  ├── README.md            (4.5 KB)
  └── assets/
      └── icon.png         (15.2 KB)

Next steps:
  $ plugin publish         # Publish to marketplace
  $ plugin package info    # View package info
```

---

#### 5. `plugin publish` - 发布到市场

```bash
plugin publish [options]

选项:
  --dry-run              模拟发布（不实际上传）
  --tag <tag>            发布标签
                          可选值: latest/stable/beta/alpha
                          默认值: latest
  --changelog <path>     变更日志文件路径
  --release-notes        直接输入发布说明
  
  --private              设为私有插件（不公开）

示例:
  # 正式发布
  plugin publish
  
  # 预览发布内容（不上传）
  plugin publish --dry-run
  
  # 发布beta版本
  plugin publish --tag beta --changelog CHANGELOG.md
  
  # 私有发布（仅自己和授权用户可见）
  plugin publish --private
```

**交互流程**:

```
$ plugin publish

🚀 Preparing to publish my-plugin v1.0.0...

📋 Package Info:
   Name:        My Awesome Plugin
   Version:     1.0.0
   Size:        245 KB
   Category:    Workflow Node
   License:     MIT
   
📝 Release Notes:
   ? Input release notes (or press Enter to skip): Initial release with core features

⚠️  This will publish to the public marketplace.
   Are you sure? (y/N): y

🔐 Authenticating...
   ✓ Authenticated as developer@example.com

📤 Uploading package...
   ████████████████████ 100% (245KB/245KB) 2.3s

📋 Submitting for review...

✅ Published successfully!
   URL: https://plugins.your-platform.com/plugins/my-plugin
   Status: Pending Review (usually < 24 hours)
   
   You'll receive an email when approved.
```

---

#### 6. 其他实用命令

##### `plugin list` - 列出本地插件

```bash
plugin list [options]

选项:
  -a, --all             包含未启用的插件
  -j, --json            JSON格式输出
  --installed           仅显示已安装的插件
  --upgradable          仅显示可升级的插件

示例:
  # 列出所有本地插件
  plugin list
  
  # JSON格式（方便脚本处理）
  plugin list -j > plugins.json
  
  # 检查是否有可升级的插件
  plugin list --upgradable
```

##### `plugin info` - 查看插件详情

```bash
plugin info <plugin-id>

示例:
  plugin info hello-world
  plugin info xiaohongshu-publish
```

##### `plugin config` - 管理插件配置

```bash
plugin config <plugin-id> [options]

选项:
  --get                 获取当前配置
  --set KEY=VALUE       设置单个配置项
  --edit                用编辑器打开配置文件
  --reset               重置为默认值
  --validate            验证配置合法性

示例:
  # 查看当前配置
  plugin config translator-node --get
  
  # 修改API Key
  plugin config translator-node --set api_key=sk-xxx
  
  # 用默认编辑器编辑
  plugin config translator-node --edit
  
  # 重置配置
  plugin config translator-node --reset
```

##### `plugin logs` - 查看日志

```bash
plugin logs [plugin-id] [options]

选项:
  -f, --follow         实时跟踪日志（类似tail -f）
  -n <lines>           显示最后N行（默认50）
  --level <level>      过滤日志级别
  --since <time>       显示指定时间后的日志
  --grep <pattern>     过滤关键字

示例:
  # 查看最近日志
  plugin logs translator-node
  
  # 实时跟踪错误日志
  plugin logs -f --level error
  
  # 搜索特定关键词
  plugin logs --grep "timeout"
```

##### `plugin doctor` - 诊断问题

```bash
plugin doctor [options]

选项:
  --fix                 自动修复发现的问题
  --verbose             详细诊断信息

示例:
  # 运行诊断
  plugin doctor
  
  # 自动修复
  plugin doctor --fix
```

**诊断项检查清单**:

```
$ plugin doctor

🔍 Running diagnostics...

[OK] Python version: 3.11.4 (required >= 3.10)
[OK] pip version: 23.2.1
[OK] Git initialized
[WARN] .gitignore missing common entries
[OK] plugin.json valid JSON
[OK] plugin.json schema validated
[OK] entry_point exists and is importable
[OK] Base class correctly inherited
[OK] Required methods implemented
[WARN] No unit tests found (recommended)
[OK] requirements.txt exists
[OK] Dependencies compatible
[ERROR] Circular dependency detected: utils ↔ helpers

📊 Summary:
   ✅ Passed: 10
   ⚠️  Warnings: 2
   ❌ Errors: 1

💡 Suggestions:
   1. Add .gitignore patterns (run: plugin doctor --fix)
   2. Create basic tests (run: plugin scaffold test)
   3. Fix circular dependency between utils.py and helpers.py

Run `plugin doctor --fix` to auto-fix warnings.
```

---

## 🏗️ 脚手架生成器

### 可用模板

#### 1. `minimal` - 最小化模板

**适用场景**: 快速原型验证、学习目的

```
my-plugin-minimal/
├── plugin.json          # 最小必要字段
└── main.py              # 仅实现execute方法
```

**特点**:
- 无依赖、无测试、无文档
- 代码量<50行
- 适合快速实验

#### 2. `basic` - 基础模板（默认）

**适用场景**: 标准功能插件开发

```
my-plugin-basic/
├── plugin.json          # 完整元数据 + 配置Schema
├── main.py              # 完整实现 + 错误处理
├── requirements.txt     # Python依赖
├── README.md            # 基础使用说明
├── .gitignore           # Git忽略规则
└── tests/
    └── test_main.py     # 基础单元测试
```

**特点**:
- 包含最佳实践骨架
- 有基础测试覆盖
- 符合发布标准

#### 3. `full` - 完整模板

**适用场景**: 生产级插件、计划发布到市场

```
my-plugin-full/
├── plugin.json          # 完整Schema + 多语言支持
├── main.py              # 完整实现 + 性能优化 + 日志
├── config.py            # 配置管理模块
├── utils.py             # 工具函数
├── errors.py            # 自定义异常
├── requirements.txt     # 依赖 + 版本锁定
├── setup.py             # 打包配置
├── README.md            # 详细文档 + 截图
├── CHANGELOG.md         # 变更历史
├── LICENSE              # 许可证文件
├── .gitignore
├── .editorconfig        # 编辑器配置
├── pyproject.toml       # 现代Python项目配置
├── assets/
│   ├── icon.png         # 插件图标
│   └── screenshots/     # 功能截图
├── tests/
│   ├── __init__.py
│   ├── conftest.py      # pytest fixtures
│   ├── test_main.py     # 单元测试
│   ├── test_integration.py  # 集成测试
│   └── test_performance.py   # 性能测试
└── docs/
    ├── api.md           # API文档
    ├── examples.md      # 使用示例
    └── troubleshooting.md  # 故障排查
```

**特点**:
- 企业级代码规范
- 完整测试套件（单元+集成+性能）
- 详细的文档和示例
- CI/CD配置就绪

#### 4. `custom` - 自定义模板

```bash
# 交互式选择需要的组件
plugin create my-plugin --template custom

? Select components (Space to select, Enter to confirm):
  ◉ Core files (plugin.json, main.py)
  ◉ Configuration management
  ◉ Error handling utilities
  ◉ Unit tests (pytest)
  ◉ Integration tests
  ◉ Performance benchmarks
  ◉ Documentation (README, API docs)
  ◉ Examples and tutorials
  ◉ CI/CD configuration (.github/workflows)
  ◉ Frontend components (Vue.js UI)
  
? Include TypeScript type definitions? Yes
? Include i18n support? No
? Choose license: MIT
```

### 自定义模板系统

你可以创建自己的团队模板：

```bash
# 创建团队模板
mkdir -p ~/.plugin-templates/my-company-template

# 复制或编写模板文件
cp -r my-plugin-full/* ~/.plugin-templates/my-company-template/

# 使用自定义模板
plugin create new-feature --template my-company-template
```

**模板变量**:

在模板文件中使用 `{{variable}}` 语法：

```json
// plugin.json.template
{
    "id": "{{plugin_id}}",
    "name": "{{plugin_name}}",
    "version": "0.1.0",
    "author": {
        "name": "{{author_name}}",
        "email": "{{author_email}}"
    },
    "entry_point": "main.py:{{class_name}}"
}
```

可用变量：
- `{{plugin_id}}` - 插件ID（kebab-case）
- `{{plugin_name}}` - 显示名称
- `{{class_name}}` - 类名（PascalCase）
- `{{author_name}}` - 作者名
- `{{author_email}}` - 作者邮箱
- `{{year}}` - 当前年份
- `{{date}}` - 当前日期

---

## 🐛 本地调试服务器

### 启动与使用

```bash
# 进入插件目录
cd my-plugin

# 启动调试服务器
plugin dev

# 服务器将在 http://localhost:8765 启动
```

### 调试功能

#### 1. Web Dashboard

访问 `http://localhost:8765/dashboard` 查看调试面板：

```
┌─────────────────────────────────────────────────────┐
│  Plugin Debug Dashboard                              │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ Status   │  │ Logs     │  │ Metrics  │          │
│  │ ● Active │  │ (实时)    │  │ (图表)   │          │
│  └──────────┘  └──────────┘  └──────────┘          │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │ Test Runner                                   │   │
│  │                                              │   │
│  │ Inputs:                                      │   │
│  │ {                                            │   │
│  │   "text": "Hello world",                     │   │
│  │   "lang": "en"                               │   │
│  │ }                                            │   │
│  │                                              │   │
│  │ [▶ Execute]  [🔄 Reset]  [📋 Copy Output]   │   │
│  │                                              │   │
│  │ Output:                                      │   │
│  │ {                                            │   │
│  │   "success": true,                           │   │
│  │   "data": {...}                              │   │
│  │ }                                            │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  Event Monitor:                                     │
│  [14:32:01] translation:completed                    │
│  [14:32:02] cache:hit key=abc123                    │
│  [14:32:05] error: timeout exceeded                  │
└─────────────────────────────────────────────────────┘
```

#### 2. API端点

调试服务器自动暴露以下端点：

```yaml
GET  /api/status              # 服务器状态
GET  /api/plugins             # 已加载插件列表
GET  /api/plugins/:id/config  # 获取插件配置
PUT  /api/plugins/:id/config  # 更新配置（热更新）
POST /api/plugins/:id/execute # 执行插件（带调试信息）
POST /api/plugins/:id/test    # 运行测试用例
GET  /api/logs                # 获取日志流
WS   /api/events              # WebSocket事件订阅
```

**Execute端点示例**:

```bash
curl -X POST http://localhost:8765/api/plugins/my-plugin/execute \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "text": "Hello World",
      "target_lang": "zh"
    },
    "context": {
      "user_id": "test_user",
      "debug_mode": true,
      "profile_performance": true
    }
  }'

# 响应（含调试信息）:
{
  "success": true,
  "data": {
    "translated_text": "你好世界",
    "detected_source_lang": "en",
    "confidence_score": 0.95
  },
  "_debug": {
    "execution_time_ms": 1234,
    "memory_used_mb": 45.2,
    "cache_hits": 2,
    "api_calls_made": 1,
    "logs_generated": 5,
    "intermediate_steps": [
      {"step": "input_validation", "duration_ms": 2},
      {"step": "llm_call", "duration_ms": 1200},
      {"step": "post_processing", "duration_ms": 32}
    ]
  }
}
```

#### 3. 热重载机制

修改源码后自动重新加载：

```
[WATCH] Detected changes:
       M modified: main.py
       A added: utils.py
       D deleted: old_module.py

[RELOAD] Stopping plugin instance...
[RELOAD] Reimporting modules...
[RELOAD] Calling on_unload() → OK (12ms)
[RELOAD] Loading new version...
[RELOAD] Calling on_load() → OK (45ms)
[RELOAD] ✓ Plugin reloaded successfully (total: 230ms)
```

**注意事项**:
- 不会丢失内存中的数据（通过序列化/反序列化保持状态）
- 如果 `on_load()` 或 `on_unload()` 抛出异常，会回滚到旧版本
- 可以手动触发重载：发送 `SIGHUP` 信号或调用 `/api/reload`

#### 4. 断点调试

**方法A：使用VS Code调试器**

`.vscode/launch.json`:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Debug Plugin",
            "type": "python",
            "request": "launch",
            "module": "plugin_cli",
            "args": ["dev"],
            "cwd": "${workspaceFolder}",
            "justMyCode": false,
            "env": {
                "PLUGIN_DEBUG_MODE": "true"
            }
        }
    ]
}
```

**方法B：使用pdb**

```python
# 在代码中插入断点
async def execute(self, ctx, inputs):
    import pdb; pdb.set_trace()  # Python 3.6+
    # 或
    breakpoint()  # Python 3.7+ (推荐)
    
    result = await self.do_something(inputs)
    return result
```

**方法C：远程调试**

```bash
# 启动时添加调试端口
plugin dev --remote-debugger-port 5678

# 在VS Code中连接Remote Debugger
```

---

## 🧪 测试框架

### 内置测试工具

#### 1. 测试夹具（Fixtures）

```python
# tests/conftest.py
import pytest
from plugin_test_utils import (
    PluginTestFixture,
    MockEventBus,
    MockDataStore,
    FakeContext
)


@pytest.fixture
def plugin():
    """加载被测插件"""
    fixture = PluginTestFixture("my-plugin")
    yield fixture
    fixture.cleanup()


@pytest.fixture
def ctx(plugin):
    """创建模拟上下文"""
    return FakeContext(
        user_id="test_user",
        config={"api_key": "test-key"},
        event_bus=MockEventBus(),
        data_store=MockDataStore()
    )


@pytest.fixture
def sample_inputs():
    """标准测试输入"""
    return {
        "text": "Hello, World!",
        "target_language": "zh"
    }
```

#### 2. 编写测试用例

```python
# tests/test_main.py
import pytest
from datetime import datetime


class TestTranslatorPlugin:
    
    async def test_execute_success(self, plugin, ctx, sample_inputs):
        """测试正常执行流程"""
        
        output = await plugin.execute(ctx, sample_inputs)
        
        assert output.success is True
        assert "translated_text" in output.data
        assert len(output.data["translated_text"]) > 0
        assert output.message != ""
    
    
    async def test_validate_inputs_valid(self, plugin):
        """测试有效输入验证"""
        
        valid, msg = await plugin.validate_inputs({
            "text": "Some text"
        })
        
        assert valid is True
        assert msg == "Inputs valid"
    
    
    async def test_validate_inputs_empty_text(self, plugin):
        """测试空文本输入"""
        
        valid, msg = await plugin.validate_inputs({})
        
        assert valid is False
        assert "empty" in msg.lower()
    
    
    async def test_execute_with_long_text(self, plugin, ctx):
        """测试长文本处理"""
        
        long_text = "Hello " * 10000  # 60K字符
        
        output = await plugin.execute(ctx, {"text": long_text})
        
        assert output.success is True
        assert len(output.data["translated_text"]) > 0
    
    
    async def test_event_emission(self, plugin, ctx, sample_inputs):
        """测试事件是否正确发出"""
        
        await plugin.execute(ctx, sample_inputs)
        
        # 检查事件总线是否收到事件
        emitted_events = ctx.event_bus.get_emitted_events()
        
        assert any(
            e.type == "translation:completed" 
            for e in emitted_events
        )
    
    
    async def test_error_handling_timeout(self, plugin, ctx):
        """测试超时错误处理"""
        
        # Mock外部API超时
        with patch('main.httpx.AsyncClient.post', 
                   side_effect=httpx.TimeoutException):
            
            output = await plugin.execute(ctx, {"text": "test"})
            
            assert output.success is False
            assert "timeout" in output.error_code.lower()
    
    
    async def test_health_check(self, plugin):
        """测试健康检查"""
        
        status = await plugin.health_check()
        
        assert status.status in ["healthy", "degraded", "unhealthy"]
        assert isinstance(status.timestamp, datetime)
```

#### 3. 性能基准测试

```python
# tests/test_performance.py
import pytest
import asyncio
import time


class TestPerformance:
    
    @pytest.mark.performance
    @pytest.mark.parametrize("text_length", [100, 1000, 10000])
    async def test_execution_time_within_limits(
        self, plugin, ctx, text_length
    ):
        """测试不同长度文本的执行时间"""
        
        inputs = {"text": "Hello " * (text_length // 6)}
        
        start = time.monotonic()
        output = await plugin.execute(ctx, inputs)
        elapsed = (time.monotonic() - start) * 1000
        
        assert output.success is True
        assert elapsed < 5000  # 最多5秒
        
        print(f"\n{text_length} chars processed in {elapsed:.2f}ms")
    
    
    @pytest.mark.performance
    async def test_concurrent_executions(self, plugin, ctx):
        """测试并发执行能力"""
        
        num_concurrent = 10
        inputs_list = [{"text": f"Text {i}"} 
                       for i in range(num_concurrent)]
        
        start = time.monotonic()
        
        tasks = [plugin.execute(ctx, inp) for inp in inputs_list]
        outputs = await asyncio.gather(*tasks)
        
        elapsed = (time.monotonic() - start) * 1000
        
        # 所有请求都应该成功
        assert all(o.success for o in outputs)
        
        # 并发应该比串行快
        print(f"\n{num_concurrent} concurrent requests "
              f"in {elapsed:.2f}ms")
```

#### 4. 集成测试

```python
# tests/test_integration.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestIntegration:
    
    async def test_full_workflow_via_api(self):
        """通过API测试完整工作流"""
        
        async with AsyncClient(base_url="http://localhost:8765") as client:
            
            # 1. 检查健康状态
            resp = await client.get("/api/status")
            assert resp.status_code == 200
            
            # 2. 执行插件
            resp = await client.post(
                "/api/plugins/translator-node/execute",
                json={
                    "inputs": {
                        "text": "Integration test",
                        "target_lang": "ja"
                    }
                }
            )
            assert resp.status_code == 200
            
            data = resp.json()
            assert data["success"] is True
            
            # 3. 检查日志中记录了操作
            resp = await client.get("/api/logs")
            assert any(
                "translation:completed" in log["message"]
                for log in resp.json()["logs"]
            )
```

### 运行测试

```bash
# 运行所有测试
plugin test

# 运行特定类别
plugin test -m unit          # 单元测试
plugin test -m integration   # 集成测试
plugin test -m performance   # 性能测试

# 生成覆盖率报告
plugin test -c

# 并行运行（需要pytest-xdist）
plugin test -n auto

# 持续监控模式（文件变化自动重跑）
plugin test --watch
```

---

## 📦 打包与发布

### 版本管理

```bash
# 查看当前版本
plugin version

# 更新版本号（遵循语义化版本）
plugin version patch     # 1.0.0 → 1.0.1 (bug修复)
plugin version minor     # 1.0.0 → 1.1.0 (新功能)
plugin version major     # 1.0.0 → 2.0.0 (破坏性变更)

# 设置预发布版本
plugin version prerelease --alpha    # 1.0.0-alpha.1
plugin version prerelease --beta     # 1.0.0-beta.1
plugin version prerelease --rc       # 1.0.0-rc.1
```

### 打包流程

```bash
# 1. 运行完整检查
plugin check
#   - 类型检查 (mypy)
#   - Linting (ruff/flake8)
#   - 安全扫描 (bandit)
#   - 依赖审计 (safety)

# 2. 构建
plugin build --format zip --minify

# 3. 本地测试包
plugin test-package ./dist/my-plugin-v1.0.0.zip

# 4. 发布
plugin publish --changelog CHANGELOG.md

# 或一次性完成所有步骤
plugin release
#   自动执行: check → build → test-package → publish
```

### 发布检查清单

发布前确保已完成：

- [ ] 所有测试通过 (`plugin test`)
- [ ] 代码覆盖率 ≥ 80% (`plugin test -c`)
- [ ] 类型检查无错误 (`mypy .`)
- [ ] Linting无警告 (`ruff check .`)
- [ ] 安全扫描无高危问题 (`bandit -r .`)
- [ ] 文档已更新（README、CHANGELOG）
- [ ] 示例代码可正常运行
- [ ] 版本号正确（遵循SemVer）
- [ ] `plugin.json` Schema验证通过
- [ ] 兼容性声明准确（`min_platform_version`）
- [ ] 许可证文件存在且正确
- [ ] 无硬编码密钥或敏感信息

---

## 💻 VS Code集成

### 推荐扩展

```bash
# 安装推荐的VS Code扩展
code --install-extension ms-python.python
code --install-extension ms-python.vscode-pylance
code --install-extension dbaeumer.vscode-eslint
code --install-extension esbenp.prettier-vscode
code --install-extension username.plugin-dev-tools  # 未来提供
```

### 工作区配置

`.vscode/settings.json`:

```json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": false,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black",
    "python.formatting.blackArgs": ["--line-length", "88"],
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
        "source.organizeImports": true
    },
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.pyc": true,
        ".pytest_cache": true
    }
}
```

### 任务配置

`.vscode/tasks.json`:

```json
{
    "version": "2.0.0",
    "tasks": [
        {
            "label": "Start Dev Server",
            "type": "shell",
            "command": "plugin dev",
            "group": {
                "kind": "build",
                "isDefault": true
            },
            "presentation": {
                "echo": true,
                "reveal": "always",
                "focus": false,
                "panel": "dedicated"
            },
            "problemMatcher": []
        },
        {
            "label": "Run Tests",
            "type": "shell",
            "command": "plugin test",
            "group": "test",
            "presentation": {
                "echo": true,
                "reveal": "always",
                "focus": false,
                "panel": "shared"
            }
        },
        {
            "label": "Build Package",
            "type": "shell",
            "command": "plugin build",
            "group": "build",
            "problemMatcher": []
        }
    ]
}
```

---

## ✨ 最佳实践

### 1. 项目组织

```
your-plugin-project/
├── plugins/                  # 所有插件放在这里
│   ├── plugin-a/
│   ├── plugin-b/
│   └── plugin-c/
├── shared/                   # 共享工具库
│   ├── utils.py
│   └── constants.py
├── tests/                    # 全局测试
│   ├── conftest.py
│   └── integration/
├── .plugin-config.json       # 全局配置
└── README.md
```

### 2. 版本控制策略

```gitignore
# .gitignore
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
ENV/
env/
.venv/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Testing
.pytest_cache/
.coverage
htmlcov/

# OS
.DS_Store
Thumbs.db

# Secrets (IMPORTANT!)
.env
*.env
secrets.yml
credentials.json
```

### 3. 持续集成 (CI/CD)

`.github/workflows/plugin-ci.yml`:

```yaml
name: Plugin CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        python-version: ['3.10', '3.11', '3.12']
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install plugin-dev-toolkit[dev]
        pip install -e .
    
    - name: Validate plugin.json
      run: plugin validate
    
    - name: Run linting
      run: ruff check .
    
    - name: Type checking
      run: mypy .
    
    - name: Run tests
      run: plugin test -c --reporter xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      if: matrix.python-version == '3.11'
  
  build:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Build package
      run: |
        pip install plugin-dev-toolkit
        plugin build
    
    - name: Upload artifact
      uses: actions/upload-artifact@v3
      with:
        name: plugin-dist
        path: dist/
```

### 4. 性能优化建议

```python
# ✅ 好的做法：连接池复用
class OptimizedPlugin(BaseWorkflowNodePlugin):
    def __init__(self):
        self._client = None
    
    async def _get_client(self):
        if not self._client:
            self._client = httpx.AsyncClient(
                limits=httpx.Limits(max_keepalive_connections=5)
            )
        return self._client

# ❌ 避免：每次创建新连接
class BadPlugin(BaseWorkflowNodePlugin):
    async def execute(self, ctx, inputs):
        client = httpx.AsyncClient()  # 每次都新建！
        # ...
```

### 5. 错误处理模式

```python
# ✅ 好的做法：明确的错误分类
try:
    result = await external_api_call()
except httpx.TimeoutException:
    raise PluginError(
        code="TIMEOUT",
        message="Service temporarily unavailable",
        retryable=True
    )
except httpx.HTTPStatusError as e:
    if e.response.status_code == 401:
        raise PluginError(
            code="AUTH_FAILED",
            message="Invalid credentials",
            user_action="Please update your API key in settings"
        )
    else:
        raise

# ❌ 避免：吞掉异常
try:
    result = await external_api_call()
except Exception:
    pass  # 静默失败，难以排查问题
```

---

## 📚 更多资源

- **完整API文档**: https://docs.your-platform.com/api
- **SDK源码**: https://github.com/your-org/plugin-sdk
- **示例插件集合**: https://github.com/your-org/example-plugins
- **社区论坛**: https://community.your-platform.com
- **视频教程**: https://youtube.com/@your-platform

---

## 📝 更新日志

### v1.0.0 (2026-08-16)

**新增功能**:
- ✨ CLI工具集（create/dev/test/build/publish等12个命令）
- 🏗️ 脚手架生成器（minimal/basic/full/custom四种模板）
- 🐛 本地调试服务器（热重载/Web Dashboard/API端点）
- 🧪 测试框架（Fixtures/Mock/性能基准/集成测试）
- 📦 打包发布工具（版本管理/检查清单/CI/CD）
- 💻 VS Code集成（扩展推荐/任务配置/工作区设置）

**改进**:
- 🚀 构建速度提升40%（增量编译）
- 📊 测试覆盖率可视化
- 🔒 安全扫描集成（bandit/safety）

**Bug修复**:
- 🐛 修复Windows平台路径分隔符问题
- 🐛 修复并发测试竞态条件

---

**🎉 感谢使用插件开发者工具链！**

如有问题或建议，欢迎提交Issue或PR。

*Happy Coding! 🚀*
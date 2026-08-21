# Creator Platform v2.0 PRD
## 一切皆插件 - 架构重构详细规格说明书

**版本**: v2.0.0-draft  
**日期**: 2026-08-15  
**状态**: 待评审

---

## 目录

1. [项目背景与战略定位](#1-项目背景与战略定位)
2. [技术架构总览](#2-技术架构总览)
3. [插件系统核心设计](#3-插件系统核心设计)
4. [数据模型与数据库设计](#4-数据模型与数据库设计)
5. [API接口规范](#5-api接口规范)
6. [前端架构改造](#6-前端架构改造)
7. [插件市场系统](#7-插件市场系统)
8. [安全机制](#8-安全机制)
9. [项目目录结构](#9-项目目录结构)
10. [分阶段实施计划](#10-分阶段实施计划)
11. [工作量估算](#11-工作量估算)
12. [风险评估与应对](#12-风险评估与应对)

---

## 1. 项目背景与战略定位

### 1.1 当前状态评估

#### 现有资产盘点
```
已完成的核心能力：
├── 多智能体引擎 (12个工作流节点)
├── 8个数据源适配器
├── 完整的小红书发布流程
├── AI文案/图片生成
├── 实时监控+通知系统
└── 前端工作台UI（Vue3+TypeScript）

当前痛点：
├── 平台绑定严重（仅支持小红书）
├── 功能扩展需改核心代码
├── 无法接入第三方开发者
└── 缺乏商业化扩展点
```

### 1.2 战略目标

| 维度 | 当前状态 | v2.0 目标 | 衡量指标 |
|------|---------|----------|---------|
| 平台支持 | 仅小红书 | 10+主流平台 | 平台插件数 |
| 可扩展性 | 改代码 | 写插件即扩展 | 第三方插件数 |
| 开发者生态 | 无 | 开放SDK+市场 | 注册开发者数 |
| 商业模式 | 未定义 | 订阅制+市场抽成 | ARR收入 |

### 1.3 目标用户画像

```
核心用户：内容创作者团队
├── 个人创作者（抖音/B站/小红书多平台运营）
├── MCN机构（批量管理100+账号）
└── 品牌方（统一内容分发）

开发者用户：
├── 插件开发者（开发平台适配器/节点）
├── 集成商（为企业定制私有化部署）
└── 技术爱好者（开源贡献）
```

---

## 2. 技术架构总览

### 2.1 整体架构图

```
创作者平台 v2.0
│
├── 表现层 (Presentation)
│   ├── Web UI (Vue3)
│   ├── API Doc (Swagger)
│   ├── Admin Dashboard
│   └── Plugin Market (Plugin Store)
│
├── 接口层 (API Layer)
│   ├── REST API (FastAPI)
│   ├── SSE (实时通信)
│   ├── GraphQL (可选)
│   └── Plugin API (CRUD/审核)
│
├── 业务层 (Business Logic)
│   ├── 工作流引擎 (Workflow)
│   ├── 内容管理 (Content Mgr)
│   ├── 用户/权限管理 (Auth/RBAC)
│   │
│   └── 插件运行时 (Plugin Runtime)
│       ├── 加载器 (Loader)
│       ├── 沙箱 (Sandbox)
│       ├── 事件总线 (Event Bus)
│       ├── 权限控制 (Perm Ctrl)
│       ├── 版本管理 (Version)
│       └── 依赖解析器 (Dependency)
│
├── 插件层 (Plugins)
│   ├── 内置插件 (Built-in)
│   │   ├── platforms/xiaohongshu/
│   │   ├── sources/hackernews/
│   │   └── nodes/ai-copywrite/
│   │
│   └── 第三方插件 (Third-party)
│       ├── platforms/douyin/ (社区贡献)
│       ├── platforms/bilibili/ (社区贡献)
│       ├── sources/tiktok-trending/ (付费插件)
│       └── nodes/custom-ai-node/ (企业定制)
│
└── 基础设施层 (Infrastructure)
    ├── MySQL / Redis / MinIO
    ├── Celery / Nginx
    └── Docker Compose
```

### 2.2 技术栈选型

```yaml
后端:
  主框架: FastAPI 0.110+
  异步: asyncio + uvicorn
  数据库: MySQL 8.0 + Redis 7.0
  任务队列: asyncio内置 + Celery(重任务)
  ORM: SQLAlchemy 2.0 + Alembic

插件系统:
  核心: 自研 (~300行核心代码)
  序列化: Pydantic V2
  动态加载: importlib

安全:
  认证: JWT
  权限: RBAC + 插件权限声明
  沙箱: resource限制 + subprocess隔离

前端:
  框架: Vue 3.4+ Composition API
  语言: TypeScript 5.0+
  构建: Vite 5.0+
  状态: Pinia
```

---

## 3. 插件系统核心设计

### 3.1 插件分类体系

```python
class PluginCategory(str, Enum):
    PLATFORM = "platform"           # 平台发布器
    DATASOURCE = "datasource"       # 数据源
    WORKFLOW_NODE = "workflow_node" # 工作流节点
    AI_MODEL = "ai_model"           # AI模型适配器
    UI_THEME = "ui_theme"           # UI主题
    INTEGRATION = "integration"     # 第三方集成
```

### 3.2 插件清单规范（plugin.json Schema）

```json
{
  "$schema": "https://creator-platform.dev/schemas/plugin-v2.json",
  "type": "object",
  "required": ["id", "name", "version", "type", "entry_point"],
  "properties": {
    "id": {
      "type": "string",
      "pattern": "^[a-z][a-z0-9_-]*$",
      "description": "唯一标识符"
    },
    "name": {
      "type": "string",
      "minLength": 2,
      "maxLength": 64
    },
    "version": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+\\.\\d+$"
    },
    "author": {
      "type": "object",
      "properties": {
        "name": { "type": "string" },
        "email": { "type": "string" }
      }
    },
    "type": {
      "type": "string",
      "enum": ["platform", "datasource", "workflow_node", "ai_model"]
    },
    "entry_point": {
      "type": "string",
      "default": "main.py"
    },
    "capabilities": {
      "type": "array",
      "items": { "type": "string" }
    },
    "permissions": {
      "type": "array",
      "items": {
        "enum": ["network:http", "network:https", "filesystem:read", "filesystem:write"]
      }
    },
    "config_schema": {
      "type": "object",
      "description": "JSON Schema格式的配置表单定义"
    },
    "dependencies": {
      "type": "object",
      "additionalProperties": { "type": "string" }
    },
    "events": {
      "type": "object",
      "properties": {
        "publishes": { "type": "array", "items": { "type": "string" } },
        "subscribes": { "type": "array", "items": { "type": "string" } }
      }
    },
    "pricing": {
      "type": "object",
      "properties": {
        "model": { "enum": ["free", "freemium", "paid"] },
        "price_monthly": { "type": "number" }
      }
    }
  }
}
```

### 3.3 核心接口定义（SDK）

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging

@dataclass
class PluginContext:
    plugin_id: str
    plugin_dir: str
    config: Dict[str, Any]
    logger: logging.Logger
    user_id: Optional[str] = None
    api: Any = None

@dataclass
class ExecutionResult:
    success: bool
    data: Any = None
    error: Optional[str] = None
    execution_time_ms: int = 0

@dataclass
class PublishResult:
    success: bool
    platform_url: str = ""
    content_id: str = ""
    error: Optional[str] = None

@dataclass
class TrendingContent:
    platform: str
    content_id: str
    title: str
    summary: str
    author: str = ""
    url: str = ""
    likes: int = 0
    comments: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)

class BasePlugin(ABC):
    @property
    @abstractmethod
    def plugin_id(self) -> str: pass

    @property
    @abstractmethod
    def plugin_name(self) -> str: pass

    async def setup(self, ctx: PluginContext) -> None:
        self._ctx = ctx

    async def teardown(self) -> None: pass

class BasePlatformPlugin(BasePlugin):
    @abstractmethod
    async def authenticate(self, credentials: Dict, ctx: PluginContext) -> bool: pass

    @abstractmethod
    async def publish(self, content: Dict, config: Dict, ctx: PluginContext) -> PublishResult: pass

    async def get_analytics(self, content_id: str, ctx: PluginContext) -> Dict:
        raise NotImplementedError("暂不支持数据分析")

class BaseDatasourcePlugin(BasePlugin):
    @abstractmethod
    async def search_trending(self, keyword: str, limit: int = 20, ctx: PluginContext = None) -> List[TrendingContent]: pass

    @abstractmethod
    async def get_trending(self, limit: int = 20, ctx: PluginContext = None) -> List[TrendingContent]: pass

class BaseWorkflowNodePlugin(BasePlugin):
    @property
    @abstractmethod
    def node_type(self) -> str: pass

    @property
    @abstractmethod
    def display_name(self) -> str: pass

    @abstractmethod
    async def execute(self, inputs: Dict, node_config: Dict, ctx: PluginContext) -> Dict: pass

class PluginEventBus:
    async def publish(self, event_name: str, data: Any): pass
    async def subscribe(self, event_name: str, handler): pass
    async def unsubscribe(self, subscription_id: str): pass
```

### 3.4 PluginManager 核心实现（精简版）

```python
import asyncio
import json
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

@dataclass
class PluginInstance:
    manifest: dict
    instance: BasePlugin
    status: str = "active"
    execution_count: int = 0

class PluginManager:
    def __init__(self, plugin_dirs: List[str]):
        self.plugin_dirs = [Path(d) for d in plugin_dirs]
        self._registry: Dict[str, PluginInstance] = {}
        self._event_bus = PluginEventBus()

    async def discover_and_load_all(self) -> Dict:
        results = {}
        for plugin_dir in self.plugin_dirs:
            for manifest_path in plugin_dir.glob("*/plugin.json"):
                try:
                    with open(manifest_path) as f:
                        manifest = json.load(f)
                    
                    module = await self._load_module(manifest_path.parent, manifest.get('entry_point', 'main.py'))
                    plugin_class = getattr(module, 'Plugin', None)
                    
                    if plugin_class:
                        instance = plugin_class()
                        ctx = PluginContext(
                            plugin_id=manifest['id'],
                            plugin_dir=str(manifest_path.parent),
                            config={},
                            logger=logging.getLogger(f"plugin.{manifest['id']}")
                        )
                        await instance.setup(ctx)
                        
                        self._registry[manifest['id']] = PluginInstance(
                            manifest=manifest,
                            instance=instance
                        )
                        results[manifest['id']] = {"success": True}
                except Exception as e:
                    results[manifest_path.parent.name] = {"success": False, "error": str(e)}
        
        return results

    async def execute_method(self, plugin_id: str, method: str, *args, **kwargs) -> ExecutionResult:
        plugin = self._registry.get(plugin_id)
        if not plugin or not hasattr(plugin.instance, method):
            return ExecutionResult(success=False, error="Plugin or method not found")
        
        try:
            func = getattr(plugin.instance, method)
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=30.0)
            else:
                result = func(*args, **kwargs)
            
            plugin.execution_count += 1
            return ExecutionResult(success=True, data=result)
        except Exception as e:
            return ExecutionResult(success=False, error=str(e))

    async def _load_module(self, plugin_path: Path, entry_point: str):
        module_file = plugin_path / entry_point
        spec = importlib.util.spec_from_file_location(f"plugin_{plugin_path.name}", str(module_file))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def list_plugins(self) -> List[dict]:
        return [{
            "id": pid,
            "name": p.manifest.get('name'),
            "type": p.manifest.get('type'),
            "status": p.status,
            "executions": p.execution_count
        } for pid, p in self._registry.items()]
```

---

## 4. 数据模型与数据库设计

### 4.1 核心表结构

```sql
-- 插件主表
CREATE TABLE plugins (
    id VARCHAR(64) PRIMARY KEY COMMENT '插件ID',
    name VARCHAR(128) NOT NULL COMMENT '显示名称',
    type VARCHAR(32) NOT NULL COMMENT 'platform/datasource/workflow_node',
    author_id INT COMMENT '开发者用户ID',
    status VARCHAR(20) DEFAULT 'pending_review' COMMENT '状态',
    manifest_json JSON NOT NULL COMMENT '完整plugin.json',
    pricing_model VARCHAR(20) DEFAULT 'free' COMMENT 'free/freemium/paid',
    price_monthly DECIMAL(10,2) COMMENT '月费',
    download_count BIGINT DEFAULT 0 COMMENT '下载次数',
    avg_rating FLOAT DEFAULT 0 COMMENT '平均评分',
    is_official BOOLEAN DEFAULT FALSE COMMENT '是否官方',
    is_builtin BOOLEAN DEFAULT FALSE COMMENT '是否内置',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_type (type),
    INDEX idx_status (status)
);

-- 插件版本历史
CREATE TABLE plugin_versions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    plugin_id VARCHAR(64) NOT NULL,
    version_number VARCHAR(20) NOT NULL,
    changelog TEXT,
    download_url VARCHAR(1024),
    file_hash_sha256 VARCHAR(64),
    published_at DATETIME,
    FOREIGN KEY (plugin_id) REFERENCES plugins(id) ON DELETE CASCADE,
    UNIQUE KEY uk_version (plugin_id, version_number)
);

-- 用户插件配置
CREATE TABLE plugin_configs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    plugin_id VARCHAR(64) NOT NULL,
    user_id INT NOT NULL,
    config_json JSON NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    installed_version VARCHAR(20),
    FOREIGN KEY (plugin_id) REFERENCES plugins(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY uk_user_plugin (user_id, plugin_id)
);

-- 插件评论
CREATE TABLE plugin_reviews (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    plugin_id VARCHAR(64) NOT NULL,
    user_id INT NOT NULL,
    rating SMALLINT NOT NULL COMMENT '1-5分',
    review_text TEXT,
    is_verified_purchase BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (plugin_id) REFERENCES plugins(id) ON DELETE CASCADE
);

-- 插件审计日志
CREATE TABLE plugin_audit_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    action VARCHAR(50) NOT NULL COMMENT 'UPLOAD/APPROVE/INSTALL/EXECUTE',
    plugin_id VARCHAR(64),
    user_id INT,
    ip_address VARCHAR(45),
    details_json JSON,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_action (action),
    INDEX idx_created_at (created_at)
);

-- 每日统计
CREATE TABLE plugin_daily_stats (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    plugin_id VARCHAR(64) NOT NULL,
    stat_date DATE NOT NULL,
    downloads INT DEFAULT 0,
    installs INT DEFAULT 0,
    active_users INT DEFAULT 0,
    executions INT DEFAULT 0,
    errors INT DEFAULT 0,
    revenue_cny DECIMAL(14,2) DEFAULT 0,
    UNIQUE KEY uk_date_stat (plugin_id, stat_date)
);
```

---

## 5. API接口规范

### 5.1 RESTful API 设计

```yaml
paths:
  # 插件市场
  /plugins/marketplace:
    get:
      summary: 获取插件列表
      parameters:
        - name: type
          in: query
          schema:
            enum: [platform, datasource, workflow_node]
        - name: q
          in: query
          schema:
            type: string
        - name: sort
          in: query
          schema:
            enum: [popular, newest, rating]
            default: popular
        - name: page
          in: query
          schema:
            type: integer
            default: 1
      responses:
        200:
          description: 插件列表

  /plugins/marketplace/{plugin_id}:
    get:
      summary: 获取插件详情
      responses:
        200:
          description: 插件详情（含配置Schema、评价等）

  # 用户插件管理
  /plugins/my:
    get:
      summary: 已安装插件列表

  /plugins/my/{plugin_id}/install:
    post:
      summary: 安装插件
      responses:
        201: 安装成功
        402: 需付费

  /plugins/my/{plugin_id}/uninstall:
    delete:
      summary: 卸载插件

  /plugins/my/{plugin_id}/config:
    get: 获取配置
    put: 更新配置

  # 运行时执行
  /plugins/runtime/{plugin_id}/execute:
    post:
      summary: 执行插件方法
      requestBody:
        content:
          application/json:
            schema:
              type: object
              required: [method]
              properties:
                method:
                  type: string
                args:
                  type: array
                timeout:
                  type: number
      responses:
        200:
          description: 执行结果
```

### 5.2 SSE事件协议

```typescript
interface PluginEvents {
  // 生命周期事件
  'plugin:installed': { pluginId: string; userId: string; version: string };
  'plugin:uninstalled': { pluginId: string; userId: string };
  'plugin:updated': { pluginId: string; newVersion: string };

  // 执行状态事件
  'plugin:execution:start': { pluginId: string; method: string; requestId: string };
  'plugin:execution:complete': { pluginId: string; success: boolean; durationMs: number };
  'plugin:execution:error': { pluginId: string; error: string };

  // 插件间通信
  'plugin:event:published': { sourceId: string; eventName: string; payload: any };
}
```

---

## 6. 前端架构改造

### 6.1 新增组件结构

```
src/components/plugin-market/
├── PluginMarketplace.vue      # 市场主页
├── PluginCard.vue             # 插件卡片
├── PluginDetail.vue           # 详情页
├── PluginInstaller.vue        # 安装向导
├── PluginConfigurator.vue     # 配置编辑器
├── PluginReviews.vue          # 评论列表
└── PluginDeveloperPortal.vue  # 开发者后台

src/components/plugin-runtime/
├── PluginManager.vue          # 我的插件
├── PluginStatusBadge.vue      # 状态徽章
├── PluginExecutor.vue         # 执行面板
└── PluginLogsViewer.vue       # 日志查看器

src/composables/
├── usePluginMarket.ts         # 市场查询
├── usePluginManager.ts        # 安装卸载
└── usePluginRuntime.ts        # 执行监控

src/stores/
└── plugin.ts                  # Pinia Store
```

### 6.2 关键组件示例

```vue
<template>
  <div class="plugin-configurator">
    <h3>{{ pluginName }} 配置</h3>
    
    <DynamicFormRenderer
      :schema="configSchema"
      v-model="configData"
      @validate="handleValidate"
    />
    
    <button 
      @click="saveConfig" 
      :disabled="!hasChanges || saving"
    >
      {{ saving ? '保存中...' : '保存配置' }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { usePluginManager } from '@/composables/usePluginManager';

const props = defineProps<{
  pluginId: string;
  pluginName: string;
  configSchema: Record<string, any>;
}>();

const { savePluginConfig, validateConfig } = usePluginManager();
const configData = ref({});
const saving = ref(false);
const hasChanges = computed(() => true); // 实现变更检测

async function saveConfig() {
  saving.value = true;
  await savePluginConfig(props.pluginId, configData.value);
  saving.value = false;
}
</script>
```

---

## 7. 插件市场系统

### 7.1 功能矩阵

| 功能 | 用户角色 | 说明 |
|------|---------|------|
| 浏览搜索 | 所有用户 | 分类/标签/关键词/排序 |
| 免费安装 | 登录用户 | 一键安装，自动加载 |
| 付费购买 | 登录用户 | 支付宝/微信支付 |
| 配置使用 | 已安装用户 | 动态表单配置 |
| 评论评分 | 已安装用户 | 验证购买后可评论 |
| 上传插件 | 开发者 | 打包上传，等待审核 |
| 发布版本 | 开发者 | 版本管理，更新日志 |
| 查看统计 | 开发者 | 下载量/收入/活跃用户 |
| 审核插件 | 管理员 | 安全扫描+人工审核 |

### 7.2 审核流程

```
开发者上传 → 自动安全扫描 → 待审核队列 → 人工审核 → 已批准上线
                 ↓ (不通过)              ↓ (拒绝)
              返回原因               通知修改
```

**审核标准：**
- plugin.json格式正确且字段齐全
- 无硬编码密钥/Token
- 无危险依赖（subprocess/os.system）
- 权限申请合理（最小权限原则）
- 有完整README和使用文档
- 错误处理完善（不会导致主程序崩溃）

### 7.3 商业模式

```yaml
定价层级:
  免费(Free): 基础功能开放，社区支持
  
  专业版(Pro): ¥29/月 或 ¥299/年
    - 解锁高级插件
    - 优先技术支持
    - API调用额度提升
    
  企业版(Enterprise): 定价洽谈
    - 私有化部署
    - 自定义插件开发
    - SLA保障

插件分成:
  - 免费插件: 0%
  - 付费插件: 开发者70% + 平台30%
  - 企业定制: 开发者85% + 平台15%

结算: 月结，次月15日打款
最低提现: ¥100
```

---

## 8. 安全机制

### 8.1 多层防御体系

```
第1层: 上传前检查（客户端）
  ├─ 文件类型白名单 (.zip only)
  ├─ 文件大小限制 (Max 50MB)
  └─ 基本病毒扫描

第2层: 服务端静态分析
  ├─ 解压到隔离沙箱目录
  ├─ 文件结构检查
  ├─ 依赖审计 (requirements.txt)
  ├─ AST静态分析 (危险函数检测)
  └─ 敏感词匹配 (密钥/Token)

第3层: 运行时沙箱
  ├─ 进程资源限制 (CPU/内存/文件句柄)
  ├─ 网络访问控制 (白名单域名)
  ├─ 文件系统隔离 (只能读写插件目录)
  ├─ 子进程禁止 (默认)
  └─ 超时强制终止 (可配置30s)

第4层: 监控审计
  ├─ 全操作日志记录
  ├─ 异常行为检测
  ├─ 用户举报机制
  └─ 自动下架规则触发
```

### 8.2 权限控制实现

```python
class PermissionChecker:
    PERMISSION_MATRIX = {
        'network:http': {'allowed_domains': ['*']},
        'network:https': {'allowed_domains': ['*']},
        'filesystem:read': {'allow_paths': ['/tmp', '/var/tmp']},
        'filesystem:write': {'allow_paths': []},  # 默认禁止写
        'subprocess:spawn': {'allowed': False},
        'env:read': {'allowed_vars': ['PATH', 'HOME']},
    }

    def check_permission(self, permission: str, context: dict = None) -> tuple[bool, str]:
        """检查是否允许某权限"""
        rule = self.PERMISSION_MATRIX.get(permission)
        if not rule:
            return False, f"未知权限: {permission}"
        
        if permission == 'subprocess:spawn':
            return rule.get('allowed', False), "子进程执行被禁止"
        
        return True, "允许"

    def enforce_sandbox(self, plugin_instance):
        """应用沙箱限制"""
        import resource
        
        # 内存限制 256MB
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        
        # CPU时间限制 60秒
        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
        
        # 文件描述符限制
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
```

---

## 9. 项目目录结构

### 9.1 推荐目录布局

```
creator-platform-v2/
│
├── backend/
│   ├── app/
│   │   ├── core/                      # 🔌 插件系统核心（新增）
│   │   │   ├── __init__.py
│   │   │   ├── plugin_manager.py      # PluginManager主类
│   │   │   ├── plugin_types.py        # 类型定义
│   │   │   ├── base_interfaces.py     # SDK接口定义
│   │   │   ├── event_bus.py           # 事件总线
│   │   │   ├── sandbox.py             # 沙箱实现
│   │   │   ├── permissions.py         # 权限控制
│   │   │   └── dependency_resolver.py # 依赖解析
│   │   │
│   │   ├── api/routers/               # API路由（新增插件相关）
│   │   │   ├── plugins.py             # /api/v2/plugins/*
│   │   │   ├── marketplace.py         # /api/v2/plugins/marketplace/*
│   │   │   └── developer.py           # /api/v2/plugins/developer/*
│   │   │
│   │   ├── models/                    # 数据模型（新增）
│   │   │   ├── plugin.py              # Plugin ORM模型
│   │   │   ├── plugin_version.py
│   │   │   ├── plugin_config.py
│   │   │   ├── plugin_review.py
│   │   │   └── plugin_author.py
│   │   │
│   │   ├── services/                  # 业务服务（新增）
│   │   │   ├── plugin_market_service.py    # 市场服务
│   │   │   ├── plugin_upload_service.py    # 上传处理
│   │   │   ├── plugin_review_service.py    # 审核服务
│   │   │   └── plugin_billing_service.py   # 支付结算
│   │   │
│   │   └── plugins/                   # 📦 内置插件目录（新增）
│   │       ├── platforms/
│   │       │   └── xiaohongshu/
│   │       │       ├── plugin.json
│   │       │       └── main.py
│   │       │
│   │       ├── datasources/
│   │       │   ├── hackernews/
│   │       │   ├── reddit/
│   │       │   └── builtin/
│   │       │
│   │       └── workflow_nodes/
│   │           ├── ai_copywrite/
│   │           └── image_gen/
│   │
│   ├── plugins_third_party/           # 📦 第三方插件（运行时加载）
│   │   ├── douyin-publisher/
│   │   ├── bilibili-publisher/
│   │   └── tiktok-trending/
│   │
│   └── tests/
│       ├── test_plugin_manager.py
│       ├── test_sandbox.py
│       └── test_permissions.py
│
├── frontend/
│   └── src/
│       ├── views/
│       │   ├── PluginMarketView.vue   # 市场页面（新增）
│       │   ├── PluginDetailView.vue   # 插件详情页（新增）
│       │   └── DeveloperPortalView.vue # 开发者后台（新增）
│       │
│       ├── components/plugin-market/  # 组件（见6.1节）
│       │
│       ├── composables/              # 组合式函数（见6.1节）
│       │
│       └── types/
│           └── plugin.d.ts           # 类型定义
│
├── sdk/                              # 📚 开发者SDK（新增）
│   ├── creator_platform_sdk/
│   │   ├── __init__.py
│   │   ├── base_interfaces.py        # 导出所有基类
│   │   ├── types.py                  # 类型定义
│   │   ├── testing.py                # 测试工具
│   │   └── utils.py                  # 辅助函数
│   │
│   ├── examples/                     # 示例插件
│   │   ├── hello-world/
│   │   ├── douyin-publisher/
│   │   └── custom-datasource/
│   │
│   └── docs/
│       ├── getting-started.md
│       ├── api-reference.md
│       ├── best-practices.md
│       └── plugin-guidelines.md
│
├── scripts/                          # 工具脚本
│   ├── scan_plugin.py                # 安全扫描脚本
│   ├── package_plugin.py             # 打包工具
│   └── migrate_to_v2.py              # v1→v2迁移脚本
│
└── docker-compose.yml                # 编排配置（更新）
```

---

## 10. 分阶段实施计划

### Phase 1: MVP核心（Week 1-2）

**目标**: 实现基础插件系统，支持数据源和工作流节点插件化

**任务清单**:

| 天数 | 任务 | 负责人 | 产出物 | 工时(h) |
|------|------|--------|--------|---------|
| Day 1 | 创建core/目录结构和基类接口 | 后端 | base_interfaces.py | 8 |
| Day 2 | 实现PluginManager核心逻辑 | 后端 | plugin_manager.py | 8 |
| Day 3 | 实现事件总线和数据共享 | 后端 | event_bus.py | 6 |
| Day 4 | 数据库Migration和ORM模型 | 后端 | migration脚本 + models | 6 |
| Day 5 | REST API实现（CRUD） | 后端 | routers/plugins.py | 8 |
| Day 6 | 将现有8个数据源包装为插件 | 后端 | plugins/datasources/* | 8 |
| Day 7 | 将现有12个工作流节点包装为插件 | 后端 | plugins/workflow_nodes/* | 8 |
| Day 8 | 前端PluginManager组件 | 前端 | PluginManager.vue | 8 |
| Day 9 | 前端动态配置表单渲染器 | 前端 | DynamicFormRenderer.vue | 8 |
| Day 10 | 集成测试和Bug修复 | 全栈 | 测试报告 | 8 |

**里程碑**: 可以通过API安装/卸载/配置/执行插件

**验证标准**:
- ✅ 成功加载至少5个数据源插件
- ✅ 成功加载至少5个工作流节点插件
- ✅ 插件间可通过事件总线通信
- ✅ 前端可以查看已安装插件并配置参数
- ✅ 执行超时和错误隔离正常工作

---

### Phase 2: SDK文档+示例（Week 3）

**目标**: 让第三方开发者能基于SDK编写插件

**任务清单**:

| 天数 | 任务 | 产出物 | 工时(h) |
|------|------|--------|---------|
| Day 11 | SDK打包发布到PyPI | creator-platform-sdk 1.0.0 | 6 |
| Day 12 | 编写快速开始指南 | docs/getting-started.md | 4 |
| Day 13 | 编写API参考文档 | docs/api-reference.md | 8 |
| Day 14 | 创建3个示例插件 | examples/* | 8 |
| Day 15 | 录制视频教程 | YouTube/B站视频 | 4 |
| Day 16 | GitHub仓库搭建和Issue模板 | .github/ | 2 |
| Day 17 | 开发者社区Discord建立 | Discord服务器 | 2 |

**里程碑**: 第三方开发者可以在1小时内写出第一个Hello World插件

---

### Phase 3: 插件市场MVP（Week 4-5）

**目标**: 在线市场UI + 上传审核流程

**任务清单**:

| 周 | 任务 | 产出物 | 工时(h) |
|----|------|--------|---------|
| W4 D1-2 | 市场首页UI | PluginMarketplace.vue | 16 |
| W4 D3-4 | 插件详情页 | PluginDetail.vue | 16 |
| W5 D1-2 | 上传功能和自动扫描 | upload_service.py | 16 |
| W5 D3-4 | 审核后台UI + 流程 | AdminReviewPanel.vue | 16 |
| W5 D5 | 评论系统和评分 | PluginReviews.vue | 8 |

**里程碑**: 开发者可以上传插件，管理员可以审核，用户可以浏览安装

---

### Phase 4: 商业化准备（Week 6-8）

**目标**: 支付系统集成 + 收益分成

**任务清单**:

| 周 | 任务 | 工时(h) |
|----|------|---------|
| W6 | 支付宝/微信支付对接 | 24 |
| W7 | 订单系统和发票生成 | 24 |
| W8 | 开发者收益仪表盘 | 24 |

**里程碑**: 用户可以付费购买插件，开发者可以看到收入

---

## 11. 工作量估算

### 11.1 总工时汇总

| 阶段 | 后端(h) | 前端(h) | DevOps(h) | 文档(h) | 合计(h) | 人天 |
|------|---------|---------|-----------|---------|---------|------|
| Phase 1 MVP | 62 | 24 | 4 | 0 | 90 | 11.25 |
| Phase 2 SDK | 10 | 0 | 4 | 20 | 34 | 4.25 |
| Phase 3 市场 | 32 | 40 | 8 | 8 | 88 | 11 |
| Phase 4 商业化 | 40 | 24 | 8 | 8 | 80 | 10 |
| **总计** | **144** | **88** | **24** | **36** | **292** | **36.5** |

### 11.2 人力配置建议

**最小团队（3人）**:
- 后端工程师 x1（负责Phase 1-4的后端部分）
- 前端工程师 x1（负责Phase 1、3、4的前端部分）
- 全栈/产品 x1（负责SDK、文档、DevOps、项目管理）

**理想团队（5人）**:
- 后端工程师 x2
- 前端工程师 x1
- DevOps工程师 x1
- 产品经理/技术写作 x1

### 11.3 关键路径

```
Phase 1 (Week 1-2) ← 必须先完成
    ↓
Phase 2 SDK (Week 3) ← 可与Phase 3并行
    ↓
Phase 3 市场 (Week 4-5)
    ↓
Phase 4 商业化 (Week 6-8) ← 依赖Phase 3完成
```

**最短完成时间**: 8周（3人全职）  
**建议时间**: 10周（含缓冲）

---

## 12. 风险评估与应对

### 12.1 技术风险

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|---------|
| 动态导入导致性能问题 | 中 | 高 | 缓存已加载模块；懒加载非活跃插件 |
| 沙箱逃逸漏洞 | 低 | 极高 | 多层防御；定期安全审计；bug bounty |
| 插件间版本冲突 | 中 | 中 | 严格的SemVer校验；依赖隔离容器 |
| 向后兼容性破坏 | 中 | 高 | 版本适配层；废弃警告期；migration工具 |

### 12.2 业务风险

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|---------|
| 开发者生态冷启动 | 高 | 高 | 先做10个官方高质量插件；激励计划（前100个插件免费推广位） |
| 恶意插件上传 | 中 | 高 | 严格审核流程；用户举报机制；保险理赔 |
| 平台政策变化（如抖音封号） | 中 | 高 | 多平台分散风险；合规性审查；备用方案 |
| 竞品快速跟进 | 中 | 中 | 快速迭代；构建社区壁垒；专利保护 |

### 12.3 安全专项预案

**场景1: 发现恶意插件**
```
1. 自动检测（异常流量/报错率飙升）
2. 立即下架 + 通知已安装用户卸载
3. 发布安全公告
4. 分析攻击向量，修补防线
5. 追究开发者法律责任
```

**场景2: 插件导致主程序崩溃**
```
1. 沙箱隔离确保不影响其他插件
2. 自动重启崩溃的插件实例
3. 错误日志上报给开发者
4. 连续崩溃3次则自动禁用并通知用户
```

**场景3: 数据泄露（插件读取敏感信息）**
```
1. 权限声明强制（必须申请才能访问）
2. 运行时权限检查（每次访问都校验）
3. 审计日志记录所有敏感操作
4. 定期权限审计报告
```

---

## 附录A: 插件开发快速模板

```python
# my-awesome-plugin/main.py
from creator_platform_sdk import BaseDatasourcePlugin, TrendingContent

class Plugin(BaseDatasourcePlugin):
    """我的超棒数据源插件"""
    
    plugin_id = "my-awesome-source"
    plugin_name = "我的数据源"
    
    async def search_trending(self, keyword, limit=20, ctx=None):
        # 你的抓取/查询逻辑
        results = []
        # ... 
        return [
            TrendingContent(
                platform="my-platform",
                content_id=item['id'],
                title=item['title'],
                summary=item['summary'],
                likes=item['likes']
            )
            for item in results[:limit]
        ]
    
    async def get_trending(self, limit=20, ctx=None):
        return await self.search_trending("", limit, ctx=ctx)
```

```json
// my-awesome-plugin/plugin.json
{
  "id": "my-awesome-source",
  "name": "我的数据源",
  "version": "1.0.0",
  "type": "datasource",
  "entry_point": "main.py",
  "author": {
    "name": "Your Name",
    "email": "you@example.com"
  },
  "capabilities": ["search_trending", "get_trending"],
  "permissions": ["network:https"],
  "pricing": {
    "model": "freemium",
    "price_monthly": 9.9
  },
  "display": {
    "icon": "🚀",
    "color": "#FF6B35"
  }
}
```

---

## 附录B: Migration指南 (v1 → v2)

### 对于现有用户

**无需手动操作！** 系统会自动：

1. 检测旧版数据结构
2. 自动将现有的 `sources/` 和 `nodes/` 包装为内置插件
3. 保留所有配置和历史数据
4. 提供回滚按钮（30天内可回退到v1）

### 对于开发者

```bash
# 1. 安装v2 SDK
pip install creator-platform-sdk>=2.0.0

# 2. 更新代码中的import
# 旧: from app.agents.skills.sources.base import ContentSource
# 新: from creator_platform_sdk import BaseDatasourcePlugin

# 3. 更新类继承
# 旧: class MySource(ContentSource):
# 新: class Plugin(BaseDatasourcePlugin):

# 4. 添加plugin.json（新增文件）
# 见附录A模板

# 5. 测试兼容性
python -m creator_platform.test_compatibility my_plugin/

# 6. 打包上传
creator-platform package-upload ./my-plugin/
```

---

## 附录C: 性能基准目标

| 指标 | 目标值 | 测试方法 |
|------|--------|---------|
| 插件发现时间 (<100个插件) | <500ms | time python -c "await pm.discover()" |
| 单次插件方法执行 | <100ms (P99) | 基准测试套件 |
| 并发执行10个不同插件 | <200ms | 压力测试 |
| 内存占用/插件 | <10MB RSS | memory_profiler |
| 启动时间（含加载50个插件） | <5s | time uvicorn main:app |
| 事件总线延迟 | <1ms (P99) | 基准测试 |

---

## 结语

这份PRD详细规划了从单体应用到"一切皆插件"平台的完整转型路径。

**核心理念**：
- ✨ 最小化改动现有代码（渐进式演进）
- 🛡️ 安全第一（多层防御+审计）
- 🚀 开发者友好（简洁SDK+丰富文档）
- 💰 可持续商业（市场抽成+订阅制）

**下一步行动**：
1. 团队评审此PRD（预计2天）
2. 确认技术选型和资源分配（1天）
3. 开始Phase 1开发（立即启动）

---

**文档版本历史**:
- v1.0.0 (2026-08-15): 初稿完成
- 待补充: 详细UI设计稿、API Postman集合、性能测试报告

**联系方式**:
- 技术问题: [GitHub Issues]
- 商务合作: [邮箱]
- 开发者社区: [Discord链接]

---

*本文档采用 CC BY-SA 4.0 协议发布，欢迎 fork 和改进。*
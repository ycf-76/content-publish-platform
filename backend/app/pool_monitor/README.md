# 小红书选题池智能监控系统

独立子模块，负责多平台热点监控、SimHash 去重、LLM 三维分类、价值评分与池子水位管理（维持 200 条以内动态平衡）。

## 模块架构

```
MonitorAgent (每10分钟) ──抓取+去重+分类──▶ ScoringAgent ──评分──▶ ContentPool
                                                              │
PoolManager (每天凌晨2:00) ──清理+补抓─────────────────────────┘
API ──查询/详情/删除/手动触发/统计──────────────────────────────▶
```

### 模块间数据流

1. **MonitorAgent** 从数据源抓取 → 过滤当天发布 → SimHash 去重（命中则只更新互动数据）→ LLM 三维分类 → 交给 ScoringAgent
2. **ScoringAgent** 计算综合热度分（互动40 + 爆发力35 + 时效25）→ ≥60 入 `ContentPool`，<60 丢弃记日志
3. **PoolManager** 先删超 72h 且 <40 分 → 仍超 200 按分低删 → 低于 150 触发紧急补抓（回调 MonitorAgent）
4. **Scheduler** 注册上述两个定时任务；**main 启动** 时若池子 <50 立即抓取一次

## 文件结构

```
backend/app/pool_monitor/
├── __init__.py
├── models.py          # ContentPool + SystemLog 表定义（复用项目 Base）
├── config.py          # PoolSettings（继承全局 Settings）
├── simhash_utils.py   # 64位 SimHash 计算 + 汉明距离比较（自实现）
├── monitor_agent.py   # 监控智能体（Mock 源 + Playwright 预留接口）
├── scoring_agent.py   # 价值评分器
├── pool_manager.py    # 水位管理（清理 + 补抓）
├── api.py             # 5 个 FastAPI 路由
├── scheduler.py       # APScheduler 定时任务
├── main.py            # 入口（lifespan + router + 启动检查）
└── .env.example       # 环境变量模板
```

## 安装依赖

模块依赖以下包（项目可能已安装部分）：

```bash
cd backend
.venv\Scripts\pip install apscheduler httpx sqlalchemy aiomysql pydantic-settings fastapi uvicorn
```

> `apscheduler` 是新增依赖（定时调度），其余项目通常已有。

## 初始化数据库

模块复用项目现有数据库引擎（`app/db/session.py` 的 `engine` / `Base`）。启动时 `init_tables()` 会自动创建 `pool_content` 与 `pool_system_log` 两张表（`checkfirst=True`，不影响现有表），无需手动迁移。

## 配置

将需要的配置项追加到 `backend/.env`（参考 `.env.example`，不配则用默认值）。关键字段：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CRAWL_INTERVAL_MINUTES` | 10 | 抓取间隔（分钟） |
| `MAX_POOL_SIZE` | 200 | 池子最大容量 |
| `POOL_MIN_THRESHOLD` | 150 | 最低水位（触发补抓） |
| `HEAT_SCORE_THRESHOLD` | 60 | 入池热度分阈值 |
| `SIMHASH_HAMMING_THRESHOLD` | 8 | SimHash 汉明距离阈值 |
| `CLEANUP_HOUR` | 2 | 每日清理小时 |
| `LLM_API_KEY` | (空) | 分类用 Key，留空复用 `DEEPSEEK_API_KEY` |

## 启动方式

### 方式一：独立运行（端口 8010）

```bash
cd backend
.venv\Scripts\python.exe -m app.pool_monitor.main
```

访问 `http://localhost:8010/docs` 查看 API 文档。

### 方式二：集成到现有 app/main.py

在现有 `app/main.py` 的 lifespan 中接入：

```python
from app.pool_monitor.main import mount_pool_monitor, pool_startup, pool_shutdown

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... 现有启动逻辑 ...
    await pool_startup()          # 建表 + 注册调度器 + 启动检查
    mount_pool_monitor(app)       # 挂载 /api/pool 路由
    yield
    pool_shutdown()               # 关闭调度器
    # ... 现有关闭逻辑 ...

app = FastAPI(lifespan=lifespan)
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/pool` | 分页查询，`heat_score` 降序，支持 `platform/emotion/scene/visual` 筛选 |
| GET | `/api/pool/stats` | 统计：总数、情绪分布、状态分布、平台分布、平均热度分 |
| GET | `/api/pool/{id}` | 单条详情 |
| DELETE | `/api/pool/{id}` | 手动删除 |
| POST | `/api/pool/force_fetch` | 手动触发一次抓取（测试用） |

**查询示例：**

```
GET /api/pool?page=1&page_size=20&platform=小红书&emotion=知识科普
GET /api/pool/stats
POST /api/pool/force_fetch
```

## 核心设计说明

- **SimHash 去重**：标题 + 正文前 50 字计算 64 位指纹，汉明距离 ≤ 8 视为重复（相似度 > 85%），命中只更新互动数据不新增。
- **三维分类**：情绪 / 场景 / 视觉形式，LLM 不可用时降级为关键词匹配。
- **数据源**：第一阶段使用 `MockDataSource`（内置模拟数据），`PlaywrightDataSource` 为预留接口（调用抛 `NotImplementedError`），后续接入真实爬虫时实现 `fetch()` 即可。
- **异常容错**：单条解析失败不影响整体，捕获异常记日志后继续下一条。
- **平台分区**：同一张 `ContentPool` 表用 `source_platform` 字段区分平台（逻辑分区，便于跨平台排序统计）。

## 日志

所有抓取 / 评分 / 清理 / 补抓操作记录到 `pool_system_log` 表；运行日志输出到标准输出（建议配置 `logs/pool.log` 文件 handler）。

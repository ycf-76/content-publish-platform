# F-2026-09  平台账号管理与作品数据回收

> 版本：v2.0（适配现有代码）  
> 日期：2026-09-29  
> 状态：待实施  
> 依赖框架：[Scrapling](https://github.com/D4Vinci/Scrapling) v0.3+

---

## 1. 背景与目标

### 1.1 现状

项目已有完整的**智能体分析诊断**体系，但数据全靠**手动粘贴链接**或**CSV 导入**，智能体"有脑无眼"。

| 环节 | 现有模块 | 问题 |
|------|---------|------|
| 账号绑定 | 无 | 无法关联"我的小红书号""我的抖音号" |
| 单条采集 | `POST /api/my-works/collect` → `work_collector.collect_from_url()` → 降级链 | 一次只能采一条 |
| 批量爬取 | 无 | 无法一次性回收某账号全部作品数据 |
| 数据展示 | `SidebarNav.vue` 内容Tab → 已采集/已发布/未发布 | 数据靠手动采集，已采集列表经常是空的 |

### 1.2 目标

1. **账号管理**：设置页绑定各平台账号（扫码登录），存储登录态
2. **作品数据回收**：一键同步回收绑定账号下的全部已发布作品数据
3. **⭐ 数据映射到已采集列表**：Spider 爬取的数据写入 `PublishedContentPerformance`（`content_status='collected'`），前端 `workStore.fetchWorks()` 自动刷新，侧边栏"内容→已采集"实时展示
4. **降级兼容**：原有单条采集降级链保留，新增 Scrapling 采集方式作为增强

### 1.3 非目标

- 不做竞品爬取（只爬自己的账号数据）
- 不做内容发布（发布走现有 workflow）
- 不改智能体逻辑（智能体读表逻辑不变）
- 不改 `PublishedContentPerformance` 表结构
- 不改 `workStore` 的 `fetchWorks()` / `mapApiToWorkItem()` 逻辑（Spider 入库格式对齐现有即可）

---

## 2. 核心衔接点：数据如何流到"已采集"列表

这是最关键的数据流，**零前端改动**即可实现：

```
Spider 爬取作品数据
  → db_sink.save_scraped_item()
    → 写入 PublishedContentPerformance 表
      (content_status='collected', platform='xiaohongshu', ...)
    → 前端 workStore.fetchWorks()
      → GET /api/my-works?page_size=200
        → 查 PublishedContentPerformance WHERE user_id=... 
        → 返回 items（含 content_status='collected'）
      → mapApiToWorkItem() 映射
        → contentStatus: item.content_status  →  'collected'
      → worksByStatus computed
        → status === 'collected' → collected 数组
      → SidebarNav.vue
        → v-for="work in collectedWorks"  ← 自动展示！
```

**关键**：Spider 入库时必须设置 `content_status='collected'`，这样前端 `worksByStatus` 的 computed 逻辑会自动把它归到 `collected` 数组，侧边栏"已采集"分组自动展示。

**同步完成后**，前端只需调用 `workStore.fetchWorks()` 刷新一次，新爬取的所有作品就出现在"已采集"列表中。

---

## 3. 架构设计

### 3.1 整体架构

```
┌──────────────────────────────────────────────────────────┐
│                        前端                               │
│  设置页-平台账号(新)  │  侧边栏内容Tab(不动)               │
│  ├─ 绑定/解绑/同步    │  ├─ 已发布 ← worksByStatus.published│
│  └─ 同步进度(SSE)     │  ├─ 未发布 ← worksByStatus.draft   │
│                       │  └─ 已采集 ← worksByStatus.collected│
└───────┬───────────────┴──────────┬────────────────────────┘
        │                          │
┌───────▼──────────────────────────▼────────────────────────┐
│                      FastAPI 后端                          │
│                                                            │
│  accounts/ (新)            my-works/ (保留不动)            │
│  ├─ bind  扫码绑定         ├─ GET  列表(workStore调用)     │
│  ├─ list  账号列表         ├─ POST collect 单条采集        │
│  ├─ sync  同步作品数据     └─ POST csv-import CSV导入     │
│  ├─ sync-all 全平台同步                                    │
│  └─ unbind 解绑                                            │
│       │                         │                         │
│       ▼                         ▼                         │
│  PlatformAccount (新)      work_collector (改：降级链增强) │
│       │                         │                         │
│       ▼                         ▼                         │
│  platform_spider/ (新)                                    │
│  ├─ XhsSpider      StealthySession + Adaptive             │
│  ├─ DouyinSpider   StealthySession + Adaptive             │
│  ├─ BilibiliSpider FetcherSession                         │
│  ├─ db_sink        → PublishedContentPerformance 入库     │
│  └─ runner         → async桥接 + notification_bus推送     │
│       │                                                    │
│       ▼                                                    │
│  PublishedContentPerformance (DB，不动)                   │
│  content_status='collected' ← Spider写入                  │
│       │                                                    │
│       ▼                                                    │
│  workStore.fetchWorks() → GET /api/my-works → 已采集列表  │
│       │                                                    │
│       ▼                                                    │
│  智能体分析 (全不动)                                      │
│  account-diagnosis / publish-analytics / data-tracker /   │
│  self_attribution / ...                                   │
└────────────────────────────────────────────────────────────┘
```

### 3.2 核心设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 登录态获取 | StealthyFetcher 打开登录页 → 用户扫码 → 保存 cookies | 体验好，无需手动粘贴 |
| Spider 运行 | `asyncio.to_thread(spider.start)` | Spider.start() 同步阻塞，FastAPI 是 async |
| Session 类型 | StealthySession（小红书/抖音）+ FetcherSession（B站） | 小红书/抖音需反检测；B站 API 公开 |
| Adaptive | 默认开启 | 选择器自动容错改版，核心价值 |
| 入库格式 | 对齐 `my_works.py` 的 `collect_note_data` 入库逻辑 | 前端 `mapApiToWorkItem()` 零改动即可展示 |
| content_status | `'collected'` | 前端 `worksByStatus` 自动归到 collected 数组 |
| 降级链 | 保留原有，头部插入 scrapling_fetcher | 新旧并行，零风险 |
| 前端位置 | 设置页 sections 加 `{ key: 'accounts' }` | 用户要求 |
| 同步后刷新 | Spider完成 → notification_bus推送 → 前端调 `fetchWorks()` | 已采集列表实时更新 |

---

## 4. 数据模型

### 4.1 PlatformAccount（新增表）

文件：`backend/app/db/models.py` 末尾追加

```python
class PlatformAccount(Base):
    """用户绑定的各平台账号。"""
    __tablename__ = "platform_accounts"
    __table_args__ = (
        Index("ix_pa_user_id", "user_id"),
        Index("ix_pa_platform", "platform"),
        UniqueConstraint("user_id", "platform", name="uq_pa_user_platform"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_uid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    platform_nickname: Mapped[str | None] = mapped_column(String(128), nullable=True)
    platform_avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    platform_home_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    cookies_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(16), default="idle", nullable=False)
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    works_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fans_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

**platform 枚举值**：`xiaohongshu` / `douyin` / `bilibili`（与 `PublishedContentPerformance.platform` 对齐）

### 4.2 PublishedContentPerformance（不动）

Spider 入库时复用现有表，关键字段映射：

| Spider yield 字段 | PCP 表字段 | 说明 |
|-------------------|-----------|------|
| note_id | published_note_id | 平台内容ID |
| title | title | 标题（≤512） |
| content_text | content_text | 正文 |
| tags | tags | 标签列表（JSONB） |
| cover_img_url | cover_img_url | 封面图 |
| image_urls | images | 图片列表（JSONB） |
| likes | collected_likes | 点赞数 |
| collects | collected_collects | 收藏数 |
| comments | collected_comments | 评论数 |
| shares | collected_shares | 分享数 |
| platform | platform | 平台标识 |
| — | content_status | 固定 `'collected'` |
| — | workflow_id | 固定 `''`（非工作流发布） |
| — | user_id | 当前用户ID |

---

## 5. API 设计

### 5.1 路由注册

文件：`backend/app/api/routers/accounts.py`（新增）

```python
router = APIRouter(prefix="/api/accounts", tags=["accounts"])
```

在 `backend/app/main.py` 追加（与现有 include_router 对齐）：

```python
from app.api.routers import accounts
app.include_router(accounts.router)  # 平台账号管理 API
```

### 5.2 端点定义

#### GET /api/accounts — 列出绑定账号

返回所有支持平台的绑定状态，未绑定的也列出（`bound: false`）。

```json
{
  "success": true,
  "data": [
    {
      "id": "01J...",
      "platform": "xiaohongshu",
      "platform_nickname": "护肤测评小王",
      "platform_avatar_url": "https://...",
      "last_synced_at": "2026-09-28T18:30:00Z",
      "sync_status": "idle",
      "works_count": 42,
      "fans_count": 23000,
      "bound": true
    },
    { "id": null, "platform": "douyin", "bound": false },
    { "id": null, "platform": "bilibili", "bound": false }
  ]
}
```

#### POST /api/accounts/bind — 触发扫码绑定

```json
// 请求
{ "platform": "xiaohongshu" }

// 响应
{
  "success": true,
  "data": {
    "task_id": "bind_01J...",
    "platform": "xiaohongshu",
    "status": "pending",
    "message": "请在弹出的浏览器窗口中扫码登录"
  }
}
```

#### GET /api/accounts/qr-status/{task_id} — 轮询扫码状态

```json
{
  "success": true,
  "data": {
    "task_id": "bind_01J...",
    "status": "confirmed",  // pending / scanned / confirmed / failed / expired
    "platform": "xiaohongshu",
    "account": {            // status=confirmed 时才有
      "id": "01J...",
      "platform_nickname": "护肤测评小王",
      "fans_count": 23000
    }
  }
}
```

#### DELETE /api/accounts/{account_id} — 解绑

#### POST /api/accounts/{account_id}/sync — 同步作品数据

```json
// 请求
{ "force": false }  // true=全量，false=增量

// 响应
{
  "success": true,
  "data": {
    "account_id": "01J...",
    "platform": "xiaohongshu",
    "status": "started",
    "message": "同步已启动，通过通知总线推送进度"
  }
}
```

#### POST /api/accounts/sync-all — 同步所有已绑定账号

---

## 6. 扫码登录服务

文件：`backend/app/services/platform_login.py`（新增）

### 6.1 各平台登录页

| 平台 | 登录页 URL | 登录成功标志 |
|------|-----------|-------------|
| 小红书 | `https://www.xiaohongshu.com` | 页面有用户昵称元素 |
| 抖音 | `https://www.douyin.com` | 页面有用户昵称元素 |
| B站 | `https://passport.bilibili.com/login` | URL 变为 `https://www.bilibili.com` |

### 6.2 核心流程

```python
async def start_qr_login(platform: str, user_id: str) -> str:
    """启动扫码登录，返回 task_id。"""
    task_id = f"bind_{generate_ulid()}"
    _bind_tasks[task_id] = {"status": "pending", "platform": platform, "user_id": user_id}
    asyncio.create_task(_run_login_browser(task_id, platform, user_id))
    return task_id


async def _run_login_browser(task_id, platform, user_id):
    """后台线程运行浏览器，等待用户扫码。"""
    from scrapling.fetchers import StealthyFetcher

    login_urls = {
        "xiaohongshu": "https://www.xiaohongshu.com",
        "douyin": "https://www.douyin.com",
        "bilibili": "https://passport.bilibili.com/login",
    }

    # headless=False 让用户看到浏览器窗口扫码
    page = StealthyFetcher.fetch(
        login_urls[platform],
        headless=False,
        network_idle=True,
        timeout=300000,  # 5分钟
    )

    # 登录成功 → 提取 cookies + 用户信息
    cookies = page.cookies()
    user_info = _extract_user_info(page, platform)

    # 保存到 PlatformAccount
    await _save_account(user_id, platform, user_info, cookies)
    _bind_tasks[task_id]["status"] = "confirmed"
```

### 6.3 超时：5分钟，超时后关闭浏览器，task 状态置为 `expired`

---

## 7. Spider 采集层

### 7.1 目录结构（新增）

```
backend/app/platform_spider/
  __init__.py
  base.py              # BasePlatformSpider 基类
  xhs_spider.py        # 小红书Spider
  douyin_spider.py     # 抖音Spider
  bilibili_spider.py   # B站Spider
  db_sink.py           # Spider结果 → PublishedContentPerformance 入库
  runner.py            # async桥接 + notification_bus进度推送
```

### 7.2 BasePlatformSpider 基类

文件：`backend/app/platform_spider/base.py`

适配 Scrapling Spider ABC 的实际 API：

```python
from scrapling.spiders import Spider
from scrapling.spiders.request import Request
from scrapling.spiders.session import SessionManager

class BasePlatformSpider(Spider):
    """平台Spider基类。"""

    platform: str = ""
    user_id: str = ""
    platform_uid: str = ""
    cookies: dict | None = None

    # 通用配置（对齐 Scrapling Spider 属性名）
    adaptive = True
    autothrottle_enabled = True
    autothrottle_start_delay = 2.0
    autothrottle_max_delay = 10.0
    concurrent_requests = 2
    max_blocked_retries = 3

    async def on_scraped_item(self, item: dict) -> dict | None:
        """每条结果实时入库 + 推送进度。"""
        from app.platform_spider.db_sink import save_scraped_item
        saved = await save_scraped_item(item, self.platform, self.user_id)
        if saved:
            from app.services.notification_bus import notification_bus
            await notification_bus.publish("spider_item_scraped", {
                "platform": self.platform,
                "title": item.get("title", "")[:50],
                "spider_name": self.name,
            })
        return item

    async def on_close(self) -> None:
        """爬取完成后更新 PlatformAccount 同步状态。"""
        from app.platform_spider.db_sink import update_sync_status
        await update_sync_status(self.user_id, self.platform, "idle")

    @staticmethod
    def _parse_count(text: str) -> int:
        """解析 '1.2w' '3.5k' 等中文计数格式。"""
        text = text.strip().replace(",", "")
        if not text:
            return 0
        try:
            if "w" in text or "万" in text:
                return int(float(text.replace("w", "").replace("万", "")) * 10000)
            if "k" in text:
                return int(float(text.replace("k", "")) * 1000)
            return int(text)
        except ValueError:
            return 0
```

### 7.3 XhsSpider

文件：`backend/app/platform_spider/xhs_spider.py`

```python
class XhsSpider(BasePlatformSpider):
    name = "xhs_user_notes"
    platform = "xiaohongshu"
    allowed_domains = {"xiaohongshu.com", "www.xiaohongshu.com"}

    concurrent_requests = 2
    autothrottle_start_delay = 2.0
    autothrottle_max_delay = 10.0

    def configure_sessions(self, manager: SessionManager) -> None:
        from scrapling.fetchers import StealthySession
        kwargs = {"headless": True, "network_idle": True}
        if self.cookies:
            kwargs["cookies"] = self.cookies
        manager.add("stealthy", StealthySession(**kwargs), default=True)

    async def parse(self, response):
        notes = response.css(".note-item", auto_save=True)
        for note in notes:
            note_url = note.css("a::attr(href)").get("")
            if note_url:
                yield response.follow(note_url, callback=self.parse_note_detail)

    async def parse_note_detail(self, response):
        yield {
            "note_id": response.url.split("/")[-1].split("?")[0],
            "title": response.css(".note-content .title::text").get(""),
            "content_text": response.css(".note-content .desc::text").get(""),
            "likes": self._parse_count(response.css(".like-count::text").get("0")),
            "collects": self._parse_count(response.css(".collect-count::text").get("0")),
            "comments": self._parse_count(response.css(".comment-count::text").get("0")),
            "tags": [t.css("::text").get("") for t in response.css(".tag")],
            "cover_img_url": response.css(".note-image img::attr(src)").get(""),
            "image_urls": [img.css("::attr(src)").get("") for img in response.css(".note-image img")],
            "author_nickname": response.css(".author .name::text").get(""),
            "platform": "xiaohongshu",
        }
```

### 7.4 DouyinSpider / BilibiliSpider

结构同 XhsSpider，区别：
- DouyinSpider：`StealthySession`，`autothrottle_start_delay=3.0`
- BilibiliSpider：`FetcherSession`（B站API公开，无需浏览器），`concurrent_requests=4`

### 7.5 db_sink.py — 入库（⭐ 核心衔接）

文件：`backend/app/platform_spider/db_sink.py`

**入库逻辑严格对齐 `my_works.py` 的 `collect_note_data` 端点**，确保前端 `mapApiToWorkItem()` 零改动即可展示：

```python
async def save_scraped_item(item: dict, platform: str, user_id: str) -> bool:
    """Spider yield item → PublishedContentPerformance 入库。

    入库格式对齐 my_works.py:collect_note_data 的逻辑，
    确保前端 workStore.mapApiToWorkItem() 零改动即可展示到"已采集"列表。
    """
    from app.db.session import AsyncSessionLocal
    from app.db.models import PublishedContentPerformance
    from app.services.performance_collector import compute_performance_score
    from app.services.image_store import cache_cover_image, cache_detail_images
    from datetime import UTC, datetime
    from sqlalchemy import select, update as sa_update

    # 1. 计算表现分（对齐 my_works.py 的逻辑）
    score = compute_performance_score({
        "likes": item.get("likes", 0),
        "collects": item.get("collects", 0),
        "comments": item.get("comments", 0),
        "shares": item.get("shares", 0),
    })

    async with AsyncSessionLocal() as db:
        note_id = item.get("note_id", "")

        # 2. 去重：同用户+同平台+同note_id → 更新而非新增
        existing = await db.scalar(
            select(PublishedContentPerformance.id).where(
                PublishedContentPerformance.user_id == user_id,
                PublishedContentPerformance.platform == platform,
                PublishedContentPerformance.published_note_id == note_id,
            )
        )

        # 3. 图片缓存（对齐 my_works.py 的逻辑）
        cover_img_url = item.get("cover_img_url", "")
        image_urls = item.get("image_urls", [])
        try:
            cover_img_url = await cache_cover_image(note_id, cover_img_url)
        except Exception:
            pass
        try:
            image_urls = await cache_detail_images(note_id, image_urls) or image_urls
        except Exception:
            pass

        now = datetime.now(UTC)

        if existing:
            # 更新已有记录
            await db.execute(
                sa_update(PublishedContentPerformance)
                .where(PublishedContentPerformance.id == existing)
                .values(
                    title=(item.get("title", "") or "")[:512],
                    content_text=item.get("content_text"),
                    tags=item.get("tags"),
                    cover_img_url=cover_img_url,
                    images=image_urls,
                    collected_likes=item.get("likes", 0),
                    collected_collects=item.get("collects", 0),
                    collected_comments=item.get("comments", 0),
                    collected_shares=item.get("shares", 0),
                    performance_score=score,
                    collected_at=now,
                    content_status="collected",
                )
            )
            await db.commit()
            return True

        # 新增记录（对齐 my_works.py:collect_note_data 的字段赋值）
        record = PublishedContentPerformance(
            user_id=user_id,
            workflow_id="",                    # 非工作流发布
            published_note_id=note_id,
            title=(item.get("title", "") or "")[:512],
            content_text=item.get("content_text"),
            tags=item.get("tags"),
            cover_img_url=cover_img_url,
            images=image_urls,
            platform=platform,
            collected_likes=item.get("likes", 0),
            collected_collects=item.get("collects", 0),
            collected_comments=item.get("comments", 0),
            collected_shares=item.get("shares", 0),
            performance_score=score,
            collected_at=now,
            published_at=now,
            content_status="collected",        # ← 关键：前端 worksByStatus 归到 collected
        )
        db.add(record)
        await db.commit()

    return True


async def update_sync_status(user_id: str, platform: str, status: str, error: str | None = None):
    """更新 PlatformAccount 的同步状态。"""
    from app.db.session import AsyncSessionLocal
    from app.db.models import PlatformAccount
    from sqlalchemy import update as sa_update
    from datetime import UTC, datetime

    async with AsyncSessionLocal() as db:
        values = {"sync_status": status, "updated_at": datetime.now(UTC)}
        if status == "idle":
            values["last_synced_at"] = datetime.now(UTC)
        if error:
            values["sync_error"] = error
        await db.execute(
            sa_update(PlatformAccount)
            .where(PlatformAccount.user_id == user_id, PlatformAccount.platform == platform)
            .values(**values)
        )
        await db.commit()
```

### 7.6 runner.py — async桥接

文件：`backend/app/platform_spider/runner.py`

```python
import asyncio
import logging

logger = logging.getLogger(__name__)


async def run_spider(spider_cls, user_id: str, platform: str, **kwargs) -> dict:
    """后台线程运行 Spider，实时推送进度。"""
    from app.platform_spider.db_sink import update_sync_status

    spider = spider_cls(user_id=user_id, platform=platform, **kwargs)
    await update_sync_status(user_id, platform, "syncing")

    try:
        # Spider.start() 是同步阻塞（内部用 anyio.run），用 to_thread 桥接
        result = await asyncio.to_thread(spider.start)
    except Exception as e:
        logger.error(f"[runner] Spider {spider.name} failed: {e}")
        await update_sync_status(user_id, platform, "error", error=str(e))
        from app.services.notification_bus import notification_bus
        await notification_bus.publish("spider_failed", {
            "spider_name": spider.name, "platform": platform, "error": str(e),
        })
        return {"items": [], "stats": {}, "error": str(e)}

    # 推送完成通知
    from app.services.notification_bus import notification_bus
    await notification_bus.publish("spider_completed", {
        "spider_name": spider.name,
        "platform": platform,
        "items_scraped": result.stats.items_scraped,
        "elapsed_seconds": round(result.stats.elapsed_seconds, 2),
    })

    # 更新同步状态 + works_count
    await update_sync_status(user_id, platform, "idle")
    from app.db.session import AsyncSessionLocal
    from app.db.models import PlatformAccount
    from sqlalchemy import update as sa_update
    async with AsyncSessionLocal() as db:
        await db.execute(
            sa_update(PlatformAccount)
            .where(PlatformAccount.user_id == user_id, PlatformAccount.platform == platform)
            .values(works_count=result.stats.items_scraped)
        )
        await db.commit()

    return {"items": list(result.items), "stats": result.stats.to_dict()}
```

---

## 8. work_collector 降级链增强

### 8.1 改动点

文件：`backend/app/services/work_collector.py`

1. `COLLECTION_FALLBACK_CHAIN` 头部插入 `"scrapling_fetcher"`
2. 新增 `_collect_via_scrapling()` 函数
3. 在 `_collect_xhs()` / `_collect_douyin()` / `_collect_bilibili()` 降级链头部调用

### 8.2 降级链变更

```python
# 改前（现有代码 line 21）
COLLECTION_FALLBACK_CHAIN = [
    "page_ssr_parse",
    "link_grabber",
    "xhs_web_api",
    "mcp_note_detail",
    "creator_center_csv",
]

# 改后
COLLECTION_FALLBACK_CHAIN = [
    "scrapling_fetcher",    # ← 新增，最优先
    "page_ssr_parse",
    "link_grabber",
    "xhs_web_api",
    "mcp_note_detail",
    "creator_center_csv",
]
```

### 8.3 新增函数

```python
async def _collect_via_scrapling(content_id: str, note_url: str, platform: str) -> dict | None:
    """Scrapling 隐身抓取 + 自适应解析（降级链最优先）。"""
    try:
        from scrapling.fetchers import StealthyFetcher
        page = StealthyFetcher.fetch(
            note_url,
            headless=True,
            network_idle=True,
        )
        if platform == "xiaohongshu":
            return {
                "note_id": content_id,
                "title": page.css(".note-content .title::text").get(""),
                "content_text": page.css(".note-content .desc::text").get(""),
                "likes": _safe_int(page.css(".like-count::text").get("0")),
                "collects": _safe_int(page.css(".collect-count::text").get("0")),
                "comments": _safe_int(page.css(".comment-count::text").get("0")),
                "tags": [t.css("::text").get("") for t in page.css(".tag")],
                "cover_img_url": page.css(".note-image img::attr(src)").get(""),
                "author_nickname": page.css(".author .name::text").get(""),
                "platform": platform,
                "source": "scrapling_fetcher",
            }
        # douyin / bilibili 类似...
    except Exception as e:
        _collect_errors.append(f"Scrapling采集失败：{e}")
        return None
```

---

## 9. 前端改动

### 9.1 SettingsView.vue — sections 追加

文件：`frontend/src/views/SettingsView.vue`

**现有 sections（line 557）**：
```typescript
const sections = [
  { key: 'profile', label: '创作者画像', desc: '设置你的领域、调性和内容禁忌' },
  { key: 'agents', label: '智能体管理', desc: '创建、编辑和管理智能体' },
  { key: 'wechat', label: '自动化办公', desc: '连接通讯工具，智能办公助手' },
  { key: 'plugins', label: '插件管理', desc: '管理和配置您的插件' },
  { key: 'skills', label: 'Skills 技能', desc: '管理 Skill 技能配置' },
  { key: 'config', label: '模型配置', desc: '管理模型配置' },
  { key: 'display', label: '显示设置', desc: '流式输出速度与渲染参数' },
]
```

**改为**：
```typescript
const sections = [
  { key: 'profile', label: '创作者画像', desc: '设置你的领域、调性和内容禁忌' },
  { key: 'accounts', label: '平台账号', desc: '绑定各平台账号，同步作品数据' },  // ← 新增
  { key: 'agents', label: '智能体管理', desc: '创建、编辑和管理智能体' },
  // ... 其余不变
]
```

**渲染块追加**（在 `v-else-if="activeSection === 'agents'"` 之前）：
```html
<div v-else-if="activeSection === 'accounts'">
  <PlatformAccounts />
</div>
```

### 9.2 PlatformAccounts.vue（新增）

文件：`frontend/src/components/settings/PlatformAccounts.vue`

UI 布局：
```
┌─────────────────────────────────────────────────┐
│  🔴 小红书    已绑定：护肤测评小王                 │
│             粉丝 2.3w · 已同步 42 条作品          │
│             上次同步：2026-09-28 18:30            │
│  [同步]  [解绑]                                   │
├─────────────────────────────────────────────────┤
│  🎵 抖音     已绑定：护肤小王                     │
│             粉丝 5.1w · 已同步 28 条作品          │
│  [同步]  [解绑]                                   │
├─────────────────────────────────────────────────┤
│  📺 B站      未绑定                              │
│  [绑定]                                          │
├─────────────────────────────────────────────────┤
│  [一键同步所有平台]                                │
│                                                  │
│  同步进度（SSE实时）：                             │
│  小红书：正在同步第 15/42 条... ██████░░░ 36%     │
└─────────────────────────────────────────────────┘
```

**交互**：
- **绑定**：点击"绑定" → `POST /api/accounts/bind` → 提示扫码 → 轮询 `qr-status` → 成功刷新
- **同步**：点击"同步" → `POST /api/accounts/{id}/sync` → SSE监听 `spider_item_scraped` → 完成后调 `workStore.fetchWorks()` 刷新已采集列表
- **解绑**：确认弹窗 → `DELETE /api/accounts/{id}`
- **一键同步**：`POST /api/accounts/sync-all`

### 9.3 SidebarNav.vue — 不动

Spider 入库的数据走 `PublishedContentPerformance` → `workStore.fetchWorks()` → `worksByStatus.collected` → `collectedWorks`，侧边栏"已采集"分组自动展示，**零改动**。

### 9.4 workStore — 不动

`mapApiToWorkItem()` 已有完整的 `content_status → contentStatus` 映射，`worksByStatus` computed 已有 `collected` 分组逻辑，**零改动**。

---

## 10. 数据库迁移

文件：`backend/alembic/versions/013_add_platform_accounts.py`（新增）

```python
def upgrade():
    op.create_table(
        "platform_accounts",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("platform_uid", sa.String(128), nullable=True),
        sa.Column("platform_nickname", sa.String(128), nullable=True),
        sa.Column("platform_avatar_url", sa.String(1024), nullable=True),
        sa.Column("platform_home_url", sa.String(1024), nullable=True),
        sa.Column("cookies_json", sa.JSON, nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(16), server_default="idle", nullable=False),
        sa.Column("sync_error", sa.Text, nullable=True),
        sa.Column("works_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("fans_count", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "platform", name="uq_pa_user_platform"),
    )
    op.create_index("ix_pa_user_id", "platform_accounts", ["user_id"])
    op.create_index("ix_pa_platform", "platform_accounts", ["platform"])

def downgrade():
    op.drop_index("ix_pa_platform")
    op.drop_index("ix_pa_user_id")
    op.drop_table("platform_accounts")
```

---

## 11. 依赖变更

`backend/pyproject.toml` 追加：
```toml
dependencies = [
    ...,
    "scrapling[all]>=0.3",
]
```

安装后初始化：
```bash
pip install scrapling[all]
playwright install chromium
```

---

## 12. 改/加/删 总清单

### 🔵 新增（11项）

| # | 类型 | 路径 | 说明 |
|---|------|------|------|
| 1 | DB模型 | `backend/app/db/models.py` 末尾追加 | PlatformAccount 类 |
| 2 | 迁移 | `backend/alembic/versions/013_add_platform_accounts.py` | 建表 |
| 3 | API | `backend/app/api/routers/accounts.py` | 6个端点 |
| 4 | 服务 | `backend/app/services/platform_login.py` | 扫码登录 |
| 5 | Spider基类 | `backend/app/platform_spider/base.py` | BasePlatformSpider |
| 6 | Spider | `backend/app/platform_spider/xhs_spider.py` | XhsSpider |
| 7 | Spider | `backend/app/platform_spider/douyin_spider.py` | DouyinSpider |
| 8 | Spider | `backend/app/platform_spider/bilibili_spider.py` | BilibiliSpider |
| 9 | 入库 | `backend/app/platform_spider/db_sink.py` | save_scraped_item + update_sync_status |
| 10 | 运行器 | `backend/app/platform_spider/runner.py` | run_spider |
| 11 | 前端 | `frontend/src/components/settings/PlatformAccounts.vue` | 平台账号管理组件 |

### 🟡 修改（3项）

| # | 路径 | 改动 |
|---|------|------|
| 1 | `backend/app/main.py` | import accounts + include_router（1行） |
| 2 | `backend/app/services/work_collector.py` | 降级链头部插入 + 新增 `_collect_via_scrapling()` |
| 3 | `frontend/src/views/SettingsView.vue` | sections 加 accounts + 渲染块（3行） |

### ⚪ 不动

| 模块 | 路径 | 理由 |
|------|------|------|
| DB表结构 | `PublishedContentPerformance` | Spider 复用现有表 |
| API端点 | `my_works.py` | Spider 入库格式对齐即可 |
| 前端Store | `workStore.ts` | `fetchWorks()` + `mapApiToWorkItem()` + `worksByStatus` 逻辑不变 |
| 前端侧边栏 | `SidebarNav.vue` | `collectedWorks` 自动展示 |
| 前端API | `my_works.ts` | 不需要新端点 |
| 通知总线 | `notification_bus.py` | Spider 复用现有 publish/subscribe |
| 智能体 | account-diagnosis / publish-analytics / ... | 读表逻辑不变 |

---

## 13. 实施步骤

| 步骤 | 内容 | 产出 | 预估 |
|------|------|------|------|
| **1** | PlatformAccount 模型 + Alembic迁移 + accounts API + 扫码登录 | 后端账号管理跑通 | 1天 |
| **2** | BasePlatformSpider + db_sink + runner | Spider骨架 | 1天 |
| **3** | XhsSpider + DouyinSpider + BilibiliSpider | 三平台Spider | 1.5天 |
| **4** | PlatformAccounts.vue + SettingsView改造 | 前端账号管理 | 1天 |
| **5** | work_collector降级链增强 + 联调测试 | 端到端跑通 | 0.5天 |

**总计：5天**

---

## 14. 验收标准

1. 设置页"平台账号"板块正常展示
2. 扫码绑定小红书/抖音/B站账号成功，cookies 保存到 DB
3. 点击"同步"后，Spider 爬取作品数据写入 `PublishedContentPerformance`（`content_status='collected'`）
4. **⭐ 同步完成后，侧边栏"内容→已采集"列表自动展示新爬取的作品**（调 `workStore.fetchWorks()` 刷新）
5. 同步进度通过 SSE 实时推送到前端
6. 智能体（account-diagnosis / publish-analytics）能基于同步数据正常分析
7. 单条采集降级链中 `scrapling_fetcher` 正常工作
8. 解绑后数据保留（PCP 不删），但不再同步